# Network Proxy Runbook

The production ingress is Cloudflare HTTPS to Nginx on origin port 443. Nginx
allows only the published Cloudflare IPv4/IPv6 ranges, proxies `/` to Next.js and
`/api/*` to FastAPI, and listens only on loopback for the application upstreams.
The origin certificate must be valid for the production hostname and Cloudflare
SSL/TLS mode must be **Full (strict)**.

## Install

1. Set the `server_name` and certificate paths in `ops/nginx/autotrader.conf` for
   the production hostname. Do not add Nginx real-IP rewriting directives: the
   proxy's `X-Verified-Cloudflare-Peer` value must remain the actual TCP peer.
2. Create `/etc/nginx/autotrader`, copy `autotrader.conf` into the Nginx
   `sites-available` directory, and install `cloudflare-allowlist.conf` and
   `maintenance.html` under `/etc/nginx/autotrader/`. Enable the site using the
   host's normal Nginx site-link convention.
3. Install `refresh-cloudflare-allowlist.py` at
   `/usr/local/sbin/refresh-cloudflare-allowlist.py`, and install the service and
   timer units from `ops/nginx/` into `/etc/systemd/system/`.
4. Run `nginx -t`, then reload Nginx. Enable the weekly updater with
   `systemctl daemon-reload && systemctl enable --now autotrader-cloudflare-refresh.timer`.
5. Restrict the origin firewall/security group to Cloudflare's published ranges
   on TCP 443 as well. Keep the API and web upstream ports bound to `127.0.0.1`.

## Refresh and recovery

The systemd timer downloads both official Cloudflare feeds weekly, rejects
malformed, overlapping, non-global, oversized, or unexpectedly broad ranges,
and atomically installs the resulting Nginx directives. It runs `nginx -t`
before reloading; on validation failure the previous allow-list is restored. A
fetch/validation failure leaves the last-known-good file in place.

Run a refresh immediately with:

```sh
systemctl start autotrader-cloudflare-refresh.service
systemctl status autotrader-cloudflare-refresh.service
journalctl -u autotrader-cloudflare-refresh.service
```

The backend independently refreshes the CIDRs into Redis weekly. That cache has
an eight-day TTL; absent, malformed, or unavailable cache data uses the bundled
Cloudflare CIDRs in `backend/app/core/client_ip.py`. The Nginx updater is a
separate host-level mechanism because Nginx cannot read the backend Redis cache.

Nginx serves the static `maintenance.html` page with HTTP 503 and `Retry-After:
60` when either application upstream returns 502, 503, or 504. `/metrics` is
always blocked at the public virtual host.
