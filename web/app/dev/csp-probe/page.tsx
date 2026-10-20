import { galleryEnabled } from "@/lib/dev/gallery";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Proves the e2e CSP guard can fail (Feature 03 slice 3.2). It renders one thing the
 * policy must block (a `<style>` element without the nonce) and one it must allow (a
 * server-rendered style attribute, A2). e2e/csp.spec.ts asserts exactly that split.
 */
export default function CspProbePage() {
  if (!galleryEnabled()) notFound();

  return (
    <main className="shell py-12">
      <style>{".csp-probe-unnonced { text-decoration: underline; }"}</style>
      <h1 className="text-2xl font-semibold">CSP probe</h1>
      <p className="csp-probe-unnonced" data-testid="blocked-element">
        Underlined only if an un-nonced style element was allowed.
      </p>
      <p data-testid="allowed-attribute" style={{ fontWeight: 700 }}>
        Bold from a server-rendered style attribute.
      </p>
    </main>
  );
}
