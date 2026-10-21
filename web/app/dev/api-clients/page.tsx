import { galleryEnabled } from "@/lib/dev/gallery";
import { getPublicApi } from "@/lib/api/public";
import { getSessionApi } from "@/lib/api/session";
import type { ApiPath } from "@/lib/api/types";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

// A dev-only API route (backend app/api/v1/endpoints/dev.py), left out of the production
// contract, so it is not an `ApiPath`. The cast is confined to this probe page.
const ECHO = "/api/v1/dev/echo-headers" as ApiPath;
type Echo = Record<string, boolean>;

/**
 * Shows which headers each server client delivered to the real API (Feature 03 slice 3.4).
 * e2e/api-clients.spec.ts visits it with a session cookie set and asserts the public
 * client sent none.
 */
export default async function ApiClientsProbePage() {
  if (!galleryEnabled()) notFound();

  const [publicEcho, sessionEcho] = (await Promise.all([
    getPublicApi(ECHO),
    getSessionApi(ECHO),
  ])) as unknown as [Echo, Echo];

  return (
    <main className="shell py-12">
      <h1 className="text-2xl font-semibold">API client probe</h1>
      {(
        [
          ["public", publicEcho],
          ["session", sessionEcho],
        ] as const
      ).map(([client, echo]) => (
        <section key={client} className="mt-6">
          <h2 className="font-semibold">{client} client</h2>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 font-mono text-sm">
            {Object.entries(echo).map(([header, received]) => (
              <div key={header} className="contents">
                <dt>{header}</dt>
                <dd data-testid={`${client}-${header}`}>
                  {received ? "received" : "absent"}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </main>
  );
}
