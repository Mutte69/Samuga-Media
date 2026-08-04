# QA Report — Samuga Media Build 16.1.0

## Automated validation

Result: **63/63 checks passed**.

Validated:

- JavaScript syntax for all new active runtime files.
- New public shell, runtime JavaScript and runtime CSS loaded by every public page.
- Dedicated `/ask-samuga-ai` page and Cloudflare redirect.
- Sidebar Ask Samuga AI navigation separated from the homepage feed chat.
- Floating chat forced to `position: fixed` with safe-area spacing and a high stacking layer.
- Chat controls moved directly under `document.body` at runtime.
- Sticky public headers on desktop and mobile.
- Session-preserved Samuga AI conversation history.
- Complete ten-category Website Settings interface.
- Social add, edit, order, enable/disable, new-tab and deletion controls.
- Upload integration and image previews.
- URL validation and JSON validation for organization schema.
- Loading, saving, error and unsaved-change states.
- Backward-compatible legacy settings fields and full `website_settings_v2` payload.
- Public integration for branding, header, footer, social links, homepage controls, AI, SEO and business/contact information.
- Immediate public settings refresh through no-store cache headers.
- No duplicate HTML IDs in the expanded admin page.

## Regression safeguards

The existing Build 16.0.1 article feed, publishing dashboard, content lab, social-card tools, analytics, AI API, media library, advertisements, authors, users and activity views remain in place. Changes are isolated to new Build 16.1.0 assets and updated HTML references.

## Runtime limitation

The supplied ZIP contains the public Cloudflare website and dashboard frontend, but not the Railway backend source. The expanded dashboard posts all fields to the existing authenticated `POST /api/admin/site-settings` endpoint using both legacy flat fields and the new `website_settings_v2` JSON object. Full persistence depends on that endpoint retaining the additional keys. A reference PostgreSQL migration is included as `BACKEND_WEBSITE_SETTINGS_REFERENCE.sql` if the current backend schema is restrictive.
