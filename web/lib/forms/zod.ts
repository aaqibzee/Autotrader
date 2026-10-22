import { z } from "zod";

/**
 * The only way to import zod in this app (enforced by .oxlintrc.json).
 *
 * zod 4 compiles object parsers with `new Function` when it can. To find out, it tries
 * one, and under our CSP (no 'unsafe-eval', Feature 01 §11) the browser blocks it and
 * reports a violation on every page with a schema (found in slice 3.10). `jitless` turns
 * that off. It must run before any schema is built, which importing `z` from here
 * guarantees.
 */
z.config({ jitless: true });

export { z };
