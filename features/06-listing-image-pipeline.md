# Feature 06 — Listing Image Pipeline

**Status:** Not Started
**Priority:** Must-Have
**Milestone:** M2 Supply
**Effort:** 6h optimistic / 12h realistic / 19h pessimistic
*(raised from 4/8/14h after a scale review: server-side verification of direct
uploads, decompression-bomb limits, idempotent processing, the two-bucket layout,
takedown deletion and orphan sweeps are decided here, before image URLs spread into
emails, sitemaps and share previews. See "Scale review" at the end.)*
**Depends on:** 01, 05

## Description

Upload, process, order and serve listing photos. Photos are the most important
content on a car listing, and they dominate page weight. Report §3 lists "image
processing/optimization pipeline at scale (resize, CDN distribution, moderation)"
as an implied backend feature of the real platform. This is its MVP version: direct
uploads to object storage, background resizing into a few WebP variants, and
serving through Cloudflare's cache.

---

## Scope

### 1. Data model — `ListingImage`
`id` (UUIDv7), `listing_id` (FK, `ON DELETE CASCADE` per Feature 02 §9), `position`
(int), `status` (`uploading` / `processing` / `ready` / `failed` / `deleted`, CHECK),
`upload_key`, `variants` (JSONB `{thumb, card, full}` keys), `width`, `height`,
`bytes`, `content_sha256`, `error_code` (`unsupported_format` / `image_too_large` /
`corrupt` / `storage_error`), `alt_text`, `processed_at`, `is_seed` (bool), plus
`TimestampMixin`. Index `(listing_id, position)`. There is no unique constraint on `position`: a reorder
rewrites every position in one transaction, and ties (which shouldn't occur) break by
`created_at`. Image rows never touch `Listing.updated_at`.

### 2. Upload flow
1. **Client-side downscale** (where the browser can decode the file): resize to a 2,560 px long edge, JPEG quality 0.9, before upload. A 6 MB forecourt photo becomes ~1 MB on 4G. HEIC that the browser can't decode is uploaded as-is.
2. `POST /dealer/listings/{id}/images {filename, content_type, bytes}` validates the type (JPEG/PNG/HEIC/WebP), declared size (≤ 15 MB) and count (≤ 20 non-deleted per listing), creates an `uploading` row, and returns a **presigned PUT URL** valid for **10 minutes**. The URL signs `Content-Type` (and `Content-Length` where the provider supports signing it: to verify for R2). Rate limit: 300 per hour per dealer (Feature 04 §5).
3. The browser uploads directly to the **uploads bucket** (§3), with a progress bar and up to 4 files in parallel
4. `POST /dealer/listings/{id}/images/{image_id}/complete` **verifies the object with a HEAD request**: it exists, its size is ≤ 15 MB and matches the declared size, and its content type is allowed. On a mismatch it deletes the object and returns 422. Otherwise it marks the row `processing` and `dispatch()`es the task (Feature 01 §7).
- Presigned PUTs can't enforce limits by themselves, and Cloudflare R2 does not support S3 presigned POST policies (to verify), so the HEAD check plus the worker's own validation are the enforcement.

### 3. Buckets, keys and visibility
| Bucket (per environment) | Access | Contents | Lifecycle |
|---|---|---|---|
| `uploads` | **private**; presigned PUT only; CORS allows `PUT` from the site origin only | raw uploads at `u/{listing_id}/{image_id}` | objects deleted 7 days after creation (bucket rule) |
| `images` | **public read via `img.<domain>` only** (Feature 01 §3, §11) | processed variants at `l/{listing_id}/{image_id}/{variant}.webp`, logos at `d/{dealer_id}/{logo_id}/{size}.webp`, seed images at `seed/{name}/{variant}.webp`, sitemaps at `sitemaps/{run_id}/…` (Feature 13 §6) | kept until deleted by §7 |

- Raw uploads carry GPS EXIF, so they are never publicly readable, and they disappear after 7 days even if processing never ran.
- **Keys are immutable.** A replaced image gets a new id and therefore new URLs. That's what makes the year-long `immutable` cache header safe.
- **CSP knock-on:** the browser PUTs to the uploads bucket host and previews selected files from `blob:` URLs, so Feature 01 §11's CSP includes the uploads host in `connect-src` and `blob:` in `img-src`.

### 4. Processing task (`images` queue)
Runs on the isolated `images` queue (concurrency 1, 768 MB memory limit; Feature 01 §7, §16) with a soft time limit of 60 s and a hard one of 90 s:
1. Download the upload. **Identify the format by magic bytes**, not the filename or declared type. Anything else → `failed: unsupported_format`.
2. **Decompression-bomb guard:** read the dimensions from the header before decoding. Above **50 megapixels** → `failed: image_too_large`. Pillow's `MAX_IMAGE_PIXELS` is set to the same limit. HEIC is decoded via `pillow-heif`.
3. Auto-rotate from EXIF, convert to sRGB, then **strip all metadata** (EXIF, XMP, IPTC; removes GPS location from forecourt phone photos)
4. Resize to `thumb` 320w, `card` 640w and `full` 1600w WebP (quality ~80; never upscaled) and upload them to the `images` bucket
5. **Guarded completion:** `UPDATE listing_image SET status='ready', … WHERE id = :id AND status = 'processing'`. Variant keys are deterministic from the image id, so a redelivered task (`acks_late`, Feature 01 §7) overwrites the same objects and the second completion is a no-op. The first completion also recounts `ready` images into `Listing.photo_count` via `system_update()` (Feature 02 §5), so the lock token isn't bumped.
- **Retries:** transient storage errors are retried up to 3 times with backoff. Decode failures are permanent → `failed: corrupt`.
- Metrics (Feature 01 §12): processing duration, failures by `error_code`, `images` queue depth.

### 5. Status, ordering and deletion (dealer side)
- The dealer UI polls `GET /dealer/listings/{id}/images` every 2 s while any image is `processing`, stopping after 2 minutes. A `failed` image shows its reason and a retry action, which re-requests an upload.
- `PATCH /dealer/listings/{id}/images/order` takes the full ordered id list. If it isn't exactly the current set of non-deleted images, it returns 409 `image_set_changed` (someone else added or deleted a photo meanwhile). Position 0 is the cover image.
- `DELETE /dealer/listings/{id}/images/{image_id}` marks the row `deleted`, recounts `Listing.photo_count` (via `system_update()`), and dispatches deletion of its objects. On a live listing, a delete that would leave fewer than 3 `ready` images returns 422 (Feature 05 §3's live-listing rule).
- All image endpoints are dealer-scoped (`get_dealer_owned_or_404`, Feature 04 §9).

### 6. Serving
- Public URL: `https://img.<domain>/l/{listing_id}/{image_id}/{variant}.webp` with `Cache-Control: public, max-age=31536000, immutable`, served from the `images` bucket through Cloudflare's cache
- `<img srcset>` with all three variants and explicit `width`/`height` (no layout shift). Lazy-loaded except the first (LCP) image. No Next.js image optimisation (Feature 03 §7).
- `alt_text` is generated as "{title} — photo {n} of {total}" when the listing changes (Feature 08 uses it)
- Public pages render only `ready` images, in `position` order

### 7. Takedown and deletion
- **Admin takedown (`moderation_status = removed`, Feature 14):** deletes the listing's variant objects from the `images` bucket **and** purges their URLs from Cloudflare's cache (Cloudflare purge-by-URL API through Feature 01 §9's client; plan limits to verify). Deleting the object matters because a purge alone leaves the image reachable on the next cache miss. Browser caches may keep a copy for users who already saw it; that's accepted.
- **Admin hide (`hidden`)** is reversible, so the images are kept.
- Image-object deletion is an idempotent task (deleting a missing object is success)
- Seed images (`is_seed = true`) share keys across demo listings and are **never deleted** by listing deletion, takedown or the demo reset

### 8. Seed images (moved here from Feature 02)
- Feature 02 §8 ships ~40 bundled stock photos. A one-off `scripts.upload_seed_images` processes them through §4 into `seed/{name}/…` keys.
- `seed_demo` (Feature 02 §8) then attaches 4–12 `ListingImage` rows per demo listing, `status = ready`, `is_seed = true`, pointing at those shared keys, chosen by body type, and sets `photo_count` through the same recount as §4, so Feature 02's invariant check holds. No per-listing copies, so 50,000 perf listings cost no extra storage.

### 9. Dealer logos
- `DealerLogo(id, dealer_id FK cascade, status, upload_key, variants {s128, s256}, error_code)`, referenced by `Dealer.logo_image_id` (Feature 04 §1)
- Same flow and task with a different variant set (square, padded to 128 and 256 px, WebP). Owner only. Max 5 MB.

### 10. Orphans and sweeps (beat, `default` queue)
- Rows still `uploading` after 24 h → row deleted (the bucket lifecycle removes the object)
- Rows stuck in `processing` for more than 15 minutes → re-dispatched once, then `failed: storage_error`
- `deleted` rows whose objects are gone → hard-deleted after 7 days

### 11. Testing
- Fixtures: a JPEG with GPS EXIF, an iPhone HEIC with rotation, a PNG with a `.jpg` name, a text file sent as `image/jpeg`, a 60 MP image, a truncated JPEG
- Storage is MinIO in tests (Feature 01 §14). The Cloudflare purge client is stubbed.

---

## Key Decisions

**Presigned direct uploads, not uploads through the API.** Multi-MB phone photos
streamed through FastAPI would tie up workers on a shared 2-OCPU VM. Direct-to-storage
keeps the API thin. The price is that the API can't see the bytes on the way in, hence
the HEAD verification and magic-byte checks.

**Two buckets, not one bucket with path policies.** Rejected: a single bucket with a
public `l/` prefix. One policy mistake would expose the raw uploads, which carry GPS
coordinates. Separate buckets make "uploads are never public" a property of the
bucket, not of a policy rule. The layout is decided now because public image URLs end
up in emails, sitemaps and other sites' link previews, which can't be migrated.

**Strip EXIF unconditionally, and delete raw uploads within 7 days.** Dealers shoot on
the forecourt, and phone EXIF includes precise GPS plus device info. Stripping it is a
privacy measure, not just an optimisation. Keeping the originals forever would keep
that location data.

**A pixel limit before decoding.** A 20 KB PNG can declare 100,000 × 100,000 pixels and
decompress to tens of gigabytes. On a 768 MB worker that's an OOM kill that retries
forever. The header check costs nothing.

**HEIC is accepted.** iPhones default to it, and rejecting it would block the main
mobile-listing workflow (Feature 05).

**Three variants, WebP only.** AVIF and more breakpoints are marginal gains with real
CPU cost on a small VM. WebP is universally supported now.

**Takedown deletes the objects, not just the cache entry.** "Removed" must mean
removed, especially for offensive images.

**Processing failures are visible.** A `failed` image shows its reason and a retry
action in the dealer UI. Publishing counts only `ready` images toward the 3-photo
minimum.

## Acceptance Criteria

**Upload & validation**
- 12 photos uploaded from a phone in parallel all reach `ready`, each within 10 s under normal load
- Requesting a 21st image, a declared 16 MB file, or a PDF is rejected before any URL is issued
- An uploaded object larger than declared, or of a disallowed type, makes `complete` return 422 and the object is deleted
- A presigned URL stops working after 10 minutes. A presigned URL for dealer A's listing cannot be requested by dealer B (404).
- A PNG renamed `.jpg` is processed correctly. A text file uploaded as `image/jpeg` ends `failed: unsupported_format`.
- A 60-megapixel image ends `failed: image_too_large` without the worker exceeding its memory limit

**Processing**
- Processed variants contain no EXIF GPS data, and a HEIC upload produces correctly oriented WebP variants
- Running the processing task twice for the same image produces the same keys, one `ready` transition and no extra objects
- A worker killed mid-task has the task redelivered, and the image reaches `ready`
- A transient storage error is retried 3 times, then ends `failed: storage_error` with a retry action in the UI

**Serving**
- Public image responses carry `Cache-Control: public, max-age=31536000, immutable`
- The detail page's LCP image is not lazy-loaded, and every `<img>` has `srcset` with three widths plus `width`/`height`
- An object in the `uploads` bucket is not readable without a signature (403)
- The upload flow runs end-to-end in Playwright with no CSP violation (bucket host and `blob:` previews allowed)

**Ordering & deletion**
- Reordering changes the cover image shown on the public card. A reorder with a stale id set returns 409 `image_set_changed`.
- Deleting an image from a live listing that would leave fewer than 3 `ready` images returns 422
- A takedown (`removed`) deletes the variant objects and calls the CDN purge for each URL. A `hidden` listing keeps its images.

**Housekeeping**
- `uploading` rows older than 24 hours are removed by the sweeper. Rows stuck in `processing` are re-dispatched once, then failed.
- Demo listings get `ListingImage` rows pointing at shared `seed/` keys. Feature 02's demo reset leaves the seed objects in place.
- An owner can upload a dealer logo that produces 128 and 256 px WebP variants. A staff member gets 403.
- `images` queue depth, processing duration and failures by `error_code` are exposed on `/metrics`

---

## Scale review — what was added, and what was deliberately deferred

**Added (P0/P1), with their sections:**
- P0: HEAD verification of uploaded objects (§2)
- P0: magic-byte format detection and a 50 MP decompression-bomb limit (§4)
- P0: idempotent, guarded processing under redelivery (§4)
- P0: two-bucket layout with immutable keys and a 7-day lifecycle on raw uploads (§3)
- P0: CSP allowance for direct uploads (§3; knock-on to Feature 01 §11)
- P0: takedown deletes objects and purges the CDN (§7)
- P1: client-side downscale before upload (§2)
- P1: 10-minute presigned URLs and upload rate limits (§2)
- P1: reorder conflict detection (§5)
- P1: 3-photo minimum enforced on live deletes (§5)
- P1: orphan and stuck-job sweeps (§10)
- P1: seed images as shared keys (§8)
- P1: dealer logos on the same pipeline (§9)
- P1: processing metrics (§4)

**Ownership moves:** attaching seed images to demo listings moves here from Feature 02
(§8). Dealer logo processing (Feature 04 §1) is provided here (§9).

**Deferred (P2):**
| Item | Trigger to revisit |
|---|---|
| Automated image moderation (nudity/offensive/irrelevant detection) | First offensive-image report, or private sellers (Phase 2) |
| AVIF variants / more breakpoints | Image bytes dominate LCP on the detail page after Feature 13's budgets are met |
| Number-plate blurring | Dealer requests, or private sellers |
| Deleting images of listings archived for more than 12 months | Image storage exceeds ~50 GB or the storage bill becomes material |
| Weekly bucket ↔ table reconciliation (objects with no row) | Storage grows faster than ready-image count would explain |
| Perceptual-hash duplicate detection across dealers (stolen photos) | Scam reports involving reused photos (Feature 14) |
| Hotlink protection on `img.<domain>` | Bandwidth from third-party referrers becomes material |
| libvips instead of Pillow | Image processing p95 exceeds 10 s, or memory headroom on the `images` worker gets tight |

**Scale traps to avoid:** an on-the-fly image resizing service on the VM; storing
images in Postgres; a separate media microservice.
