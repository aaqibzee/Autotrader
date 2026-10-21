// Completes a `next build` with `output: "standalone"` into a self-contained server
// directory: Next leaves the static chunks and `public/` out of `.next/standalone`, and
// `server.js` serves them only from inside it. Production (ops/deploy/deploy.sh) and the
// e2e job (Feature 03 A3) both run this, so they serve exactly the same tree.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const standalone = path.join(webRoot, ".next", "standalone");

if (!fs.existsSync(path.join(standalone, "server.js"))) {
  console.error(
    `No standalone build at ${standalone}: run "next build" first.`,
  );
  process.exit(1);
}

const copies = [
  [
    path.join(webRoot, ".next", "static"),
    path.join(standalone, ".next", "static"),
  ],
  [path.join(webRoot, "public"), path.join(standalone, "public")],
];
for (const [from, to] of copies) {
  if (!fs.existsSync(from)) continue;
  fs.rmSync(to, { recursive: true, force: true });
  fs.cpSync(from, to, { recursive: true });
  console.log(
    `copied ${path.relative(webRoot, from)} -> ${path.relative(webRoot, to)}`,
  );
}
