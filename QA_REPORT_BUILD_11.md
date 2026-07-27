# Build 11 QA

- Backend analytics AST logic tests passed.
- OPTIONS returned 204 with exact production origin, credentials support, `Content-Type`, and `POST, OPTIONS`.
- Homepage event stored successfully.
- Article event stored successfully.
- Dashboard aggregation returned 2 views and 1 visitor in the controlled test.
- Duplicate same-session/same-path/same-hour event was deduplicated.
- Database failure returned 503 with analytics CORS headers.
- Existing public API wildcard CORS behavior remained unchanged.
- Browser tracker used same-origin `/api/track` with `credentials: omit`.
- Cloudflare proxy forwarded JSON to Railway.
- Cloudflare-rendered article and story pages included `analytics-build12.js`.
- Full Python compilation, JavaScript syntax checks, HTML reference checks and archive integrity checks passed.
