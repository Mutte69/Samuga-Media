# Samuga Media Build 16.1.0 — Website Settings and UI Reliability

## Delivered
- Forced the Ask Samuga AI control into a true fixed body-level floating layer.
- Added a dedicated `/ask-samuga-ai` page and changed the sidebar menu button to navigate there.
- Preserved the floating drawer on the current page and session chat history.
- Made public headers sticky on desktop and mobile with safe stacking and no content overlap.
- Replaced the small Site form with a complete Website Settings control centre covering general information, branding, social links, header, footer, homepage, Samuga AI, SEO, business contact and legal links.
- Added upload previews, URL validation, unsaved-change protection, loading/saving/error states, social ordering, enable/disable and deletion.
- Connected public header/footer/social/AI/SEO/contact presentation to the existing `/api/site-settings` response with backward-compatible legacy fields and a `website_settings_v2` object.
- Disabled stale caching on the Cloudflare Pages site-settings proxy so saved public changes can appear immediately.

## Persistence contract
The dashboard continues to use the existing authenticated Railway endpoint: `GET/POST /api/admin/site-settings`. The POST now includes both legacy flat fields and a full `website_settings_v2` JSON object. The public site accepts either form.

## Deployment
Deploy this directory to the existing Cloudflare Pages project. No new public secret is required. The Railway site-settings endpoint must retain unknown/new settings keys (especially `website_settings_v2`) for every expanded control to persist.
