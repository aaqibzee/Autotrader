// Public HTML must be identical for every visitor (Feature 03 §6, A4): nothing reachable
// from a public route may use the cookie-forwarding session client. This walks the import
// graph *transitively* from every file under web/app/(public)/: a direct-import rule would
// pass the moment a shared component imported the session client.
//
// Usage: node ops/ci/check_web_boundaries.mjs   (exit 1 on any violation, with the chain)
// The checker itself is tested by web/lib/api/boundaries.test.ts against fixture trees.
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const defaultWebRoot = path.join(repoRoot, "web");
const sourceExtensions = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs"]);

/** Rules: files under `from` (relative to the web root) must never reach `forbidden`. */
export const RULES = [
	{
		name: "public routes never reach the session API client",
		from: path.join("app", "(public)"),
		forbidden: [path.join("lib", "api", "session.ts")],
	},
];

function listSources(directory) {
	if (!fs.existsSync(directory)) return [];
	return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
		const full = path.join(directory, entry.name);
		if (entry.isDirectory()) return entry.name === "node_modules" ? [] : listSources(full);
		return sourceExtensions.has(path.extname(entry.name)) ? [full] : [];
	});
}

/** Every module specifier a file imports: static, re-exports, dynamic `import("…")`, `require`. */
function importedSpecifiers(ts, file) {
	const source = ts.createSourceFile(file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true);
	const specifiers = [];
	ts.forEachChild(source, function visit(node) {
		if (
			(ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
			node.moduleSpecifier &&
			ts.isStringLiteral(node.moduleSpecifier)
		) {
			specifiers.push(node.moduleSpecifier.text);
		} else if (
			ts.isCallExpression(node) &&
			(node.expression.kind === ts.SyntaxKind.ImportKeyword ||
				(ts.isIdentifier(node.expression) && node.expression.text === "require")) &&
			node.arguments[0] &&
			ts.isStringLiteralLike(node.arguments[0])
		) {
			specifiers.push(node.arguments[0].text);
		}
		ts.forEachChild(node, visit);
	});
	return specifiers;
}

/**
 * Returns one violation per (public entry file, forbidden target) that is reachable, each
 * with the import chain that reaches it. `webRoot` must contain node_modules/typescript
 * unless `typescriptFrom` points at a directory that does.
 */
export function findBoundaryViolations(webRoot = defaultWebRoot, { rules = RULES, typescriptFrom = defaultWebRoot } = {}) {
	const ts = createRequire(path.join(typescriptFrom, "package.json"))("typescript");
	const compilerOptions = {
		baseUrl: webRoot,
		paths: { "@/*": ["./*"] },
		moduleResolution: ts.ModuleResolutionKind.Bundler,
		module: ts.ModuleKind.ESNext,
		allowJs: true,
		jsx: ts.JsxEmit.Preserve,
	};
	const resolvedCache = new Map();
	function dependencies(file) {
		if (!resolvedCache.has(file)) {
			const local = importedSpecifiers(ts, file).flatMap((specifier) => {
				const resolved = ts.resolveModuleName(specifier, file, compilerOptions, ts.sys).resolvedModule;
				if (!resolved || resolved.isExternalLibraryImport) return [];
				const target = path.resolve(resolved.resolvedFileName);
				return target.startsWith(webRoot + path.sep) && !target.includes(`${path.sep}node_modules${path.sep}`)
					? [target]
					: [];
			});
			resolvedCache.set(file, local);
		}
		return resolvedCache.get(file);
	}

	const violations = [];
	for (const rule of rules) {
		const forbidden = new Set(rule.forbidden.map((target) => path.resolve(webRoot, target)));
		for (const entry of listSources(path.join(webRoot, rule.from))) {
			// Breadth-first, so the reported chain is the shortest one.
			const parent = new Map([[entry, null]]);
			const queue = [entry];
			while (queue.length > 0) {
				const file = queue.shift();
				for (const next of dependencies(file)) {
					if (parent.has(next)) continue;
					parent.set(next, file);
					if (forbidden.has(next)) {
						const chain = [next];
						for (let step = file; step; step = parent.get(step)) chain.unshift(step);
						violations.push({
							rule: rule.name,
							chain: chain.map((step) => path.relative(webRoot, step).split(path.sep).join("/")),
						});
					} else {
						queue.push(next);
					}
				}
			}
		}
	}
	return violations;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
	const violations = findBoundaryViolations();
	if (violations.length > 0) {
		console.error("Web module boundary violations:");
		for (const { rule, chain } of violations) console.error(`- ${rule}:\n    ${chain.join("\n    -> ")}`);
		process.exit(1);
	}
	console.log("Public routes do not reach the session API client.");
}
