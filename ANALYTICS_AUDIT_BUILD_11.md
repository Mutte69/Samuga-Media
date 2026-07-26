# Samuga Media Build 11 — Analytics Pipeline Audit

## Root cause

Build 9 sent analytics directly from `samugamedia.com` to the Railway domain with `navigator.sendBeacon()` and an `application/json` Blob. A cross-origin beacon uses credentialed CORS semantics. The backend answered public APIs with `Access-Control-Allow-Origin: *` and did not return `Access-Control-Allow-Credentials: true`. Wildcard origins are invalid for credentialed CORS, so the browser rejected the analytics request.

The tracker treated `sendBeacon()` returning `true` as delivery success. That value only means the browser accepted the request into its queue. When CORS later rejected it, the fallback `fetch()` was never attempted.

The audit also found two independent reliability gaps:

1. Cloudflare-rendered `/article` and `/story` pages did not include the analytics script, even though the static `article.html` shell did.
2. `/api/track` returned `{ok:true}` after calling `db_execute()` without checking whether PostgreSQL actually stored the event. `db_execute()` returns `None` both for non-fetch writes and for database failures.

## Production fix

- Browser tracking now posts to same-origin `/api/track`.
- A Cloudflare Pages Function forwards the event server-to-server to Railway.
- The browser sends no cookies or credentials.
- `fetch()` is the primary transport; same-origin `sendBeacon()` is only a fallback.
- The Railway route has an explicit `OPTIONS` response.
- Direct cross-origin requests from old cached builds receive an exact allowed origin plus credentials support, never a wildcard.
- Storage uses `RETURNING id` and verifies duplicate events before reporting success.
- Dynamic Cloudflare article and story pages now load the tracker.
- The dashboard refreshes analytics every 15 seconds while the page is open.

## CORS audit

- Backend framework: Flask, not Starlette/FastAPI `CORSMiddleware`.
- Global CORS behavior: one `after_request` handler.
- Custom OPTIONS handlers: `/api/chat` and now `/api/track`; the chat handler does not affect analytics.
- Exception handlers: no custom global exception handler was stripping headers.
- Analytics failures return a normal Flask JSON response, so the route-specific `after_request` CORS policy is applied.
- Existing public APIs retain wildcard read access.
- Existing authenticated `/api/admin/*` endpoints retain the configured CMS origin allow-list.

## Event behavior

One pageview per browser session, path and hour is retained. Therefore:

- Opening `/` records one event.
- Opening `/article?id=...` records another event because the path differs.
- Repeatedly refreshing the same path during the same hour is intentionally deduplicated.
- No raw IP address is stored.
