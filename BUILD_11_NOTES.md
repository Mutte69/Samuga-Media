# Build 11

Build 11 fixes the first-party web analytics delivery pipeline while retaining all Build 10 article reader, dashboard, Content Lab, social card, video, author and publishing features.

Changes:

- Same-origin Cloudflare Pages analytics proxy at `/api/track`.
- New `analytics-build11.js` with credential-free fetch and beacon fallback.
- Analytics added to Cloudflare-rendered article and story pages.
- Dashboard analytics refresh button and 15-second live refresh.
- Cache-busting Build 11 tracker and admin JavaScript asset names.

Deploy the backend first, followed by the website.
