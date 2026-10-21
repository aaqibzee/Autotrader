import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Resolve paths from this file, not the CWD, and load TypeScript from web/node_modules:
// ops/ has no package.json, so a bare `import "typescript"` cannot resolve from here.
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const webRoot = path.join(repoRoot, "web");
const ts = createRequire(path.join(webRoot, "package.json"))("typescript");
const apiRoot = path.join(webRoot, "lib", "api");
const sourceExtensions = new Set([".js", ".jsx", ".ts", ".tsx"]);
const violations = [];

function collectSourceFiles(directory) {
	for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
		if (entry.isDirectory()) {
			if (["node_modules", ".next", "coverage", "e2e"].includes(entry.name)) continue;
			collectSourceFiles(path.join(directory, entry.name));
			continue;
		}

		const filePath = path.join(directory, entry.name);
		if (!sourceExtensions.has(path.extname(filePath))) continue;
		if (path.resolve(filePath).startsWith(apiRoot)) continue;

		const source = ts.createSourceFile(
			filePath,
			fs.readFileSync(filePath, "utf8"),
			ts.ScriptTarget.Latest,
			true,
		);
		ts.forEachChild(source, function visit(node) {
			if (
				ts.isCallExpression(node) &&
				((ts.isIdentifier(node.expression) && node.expression.text === "fetch") ||
					(ts.isPropertyAccessExpression(node.expression) &&
						node.expression.name.text === "fetch"))
			) {
				const location = source.getLineAndCharacterOfPosition(node.getStart(source));
				violations.push(`${path.relative(repoRoot, filePath)}:${location.line + 1}`);
			}
			ts.forEachChild(node, visit);
		});
	}
}

collectSourceFiles(webRoot);
if (violations.length > 0) {
	console.error(`Raw fetch calls are only allowed in web/lib/api:\n${violations.join("\n")}`);
	process.exit(1);
}

console.log("All web network calls use the typed API boundary.");
