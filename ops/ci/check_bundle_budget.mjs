// First-load JS budget for the public shell (Feature 03 §7, A1). Run after `next build`.
//
// For every public route it sums the gzipped size of the JS chunks a first visit loads
// (from .next/app-build-manifest.json) and fails if any route is over budget. Sizes are
// gzip level 9 in kB of 1,000 bytes, the units `next build` prints, so the numbers here
// and in the build log agree.
//
// The budget is the measured framework floor plus our own allowance:
//   floor  = 103 kB: `next build` of the Feature 01 placeholder with the Sentry client
//            stubbed out (2026-10-20, Next 15.5.28, React 19.1.0): Next runtime 46.8,
//            react-dom 54.2, other shared 2.3.
//   + 30 kB for shell code (layouts, islands, toast region).
// The eager Sentry SDK alone was +59 kB; it now loads after idle (slice 3.3).
// A deliberate raise needs a reason in the commit and a new measurement here.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

const FRAMEWORK_FLOOR_KB = 103;
const SHELL_ALLOWANCE_KB = 30;
const budgetKb = Number(process.env.BUNDLE_BUDGET_KB ?? FRAMEWORK_FLOOR_KB + SHELL_ALLOWANCE_KB);

// Signed-in surfaces and dev-only tools are not part of the public shell. Their bundles
// are still printed, but only public routes are held to the budget.
const NOT_PUBLIC = /^\/(?:dev|dealer|account|admin)(?:\/|$)/;

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const nextDir = path.join(repoRoot, "web", ".next");
const manifestPath = path.join(nextDir, "app-build-manifest.json");

if (!fs.existsSync(manifestPath)) {
	console.error(`No ${path.relative(repoRoot, manifestPath)}: run "next build" first.`);
	process.exit(2);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const buildManifest = JSON.parse(fs.readFileSync(path.join(nextDir, "build-manifest.json"), "utf8"));
// `nomodule` polyfills never load in the browsers we support; Next excludes them too.
const polyfills = new Set(buildManifest.polyfillFiles ?? []);

const gzipCache = new Map();
function gzipKb(file) {
	if (!gzipCache.has(file)) {
		const bytes = fs.readFileSync(path.join(nextDir, file));
		gzipCache.set(file, zlib.gzipSync(bytes, { level: 9 }).length / 1000);
	}
	return gzipCache.get(file);
}

/** "/(public)/cars/[id]/page" -> "/cars/[id]"; route groups do not appear in URLs. */
function routeOf(entry) {
	const route = entry
		.replace(/\/page$/, "")
		.split("/")
		.filter((segment) => !/^\(.*\)$/.test(segment))
		.join("/");
	return route === "" ? "/" : route;
}

const routes = Object.entries(manifest.pages)
	.filter(([entry]) => entry.endsWith("/page"))
	.map(([entry, files]) => {
		const chunks = [...new Set(files)].filter((file) => file.endsWith(".js") && !polyfills.has(file));
		const totalKb = chunks.reduce((sum, file) => sum + gzipKb(file), 0);
		return { route: routeOf(entry), chunks, totalKb, public: !NOT_PUBLIC.test(routeOf(entry)) };
	})
	.sort((a, b) => b.totalKb - a.totalKb);

if (!routes.some((route) => route.public)) {
	// A manifest with no public routes would pass vacuously (playbook §2).
	console.error("No public routes found in the build manifest; refusing to pass.");
	process.exit(2);
}

const over = routes.filter((route) => route.public && route.totalKb > budgetKb);
const lines = [
	`First-load JS (gzip): budget ${budgetKb} kB for public routes`,
	"",
	"| Route | First load (kB) | Public | Status |",
	"|---|---:|---|---|",
	...routes.map(
		(r) =>
			`| \`${r.route}\` | ${r.totalKb.toFixed(1)} | ${r.public ? "yes" : "no"} | ${
				!r.public ? "not gated" : r.totalKb > budgetKb ? "**over**" : "ok"
			} |`,
	),
];
const heaviest = routes.find((route) => route.public);
lines.push(
	"",
	`Chunks of the heaviest public route (\`${heaviest.route}\`):`,
	"",
	"| Chunk | kB |",
	"|---|---:|",
	...heaviest.chunks
		.map((file) => [file, gzipKb(file)])
		.sort((a, b) => b[1] - a[1])
		.map(([file, kb]) => `| \`${file}\` | ${kb.toFixed(1)} |`),
);

const report = lines.join("\n");
console.log(report);
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${report}\n`);

if (over.length > 0) {
	console.error(
		`\n${over.length} public route(s) over the ${budgetKb} kB first-load budget: ${over
			.map((r) => `${r.route} (${r.totalKb.toFixed(1)} kB)`)
			.join(", ")}`,
	);
	process.exit(1);
}
