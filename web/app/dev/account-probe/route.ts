import { galleryEnabled } from "@/lib/dev/gallery";

// Dev only (A3): a stand-in for `GET /users/me` that answers late, so e2e can measure
// the account island's layout shift (Feature 03 slice 3.11). `?delay=` in ms, max 5 s.
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!galleryEnabled()) return new Response(null, { status: 404 });
  const delay = Math.min(
    Number(new URL(request.url).searchParams.get("delay")) || 0,
    5_000,
  );
  await new Promise((resolve) => setTimeout(resolve, delay));
  return Response.json({ displayName: "Sam Patel" });
}
