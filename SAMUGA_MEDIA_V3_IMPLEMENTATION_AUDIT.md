# Samuga Media V3 — Implementation and Research Audit

## Build identity

- **Build:** 16.0.0
- **Product:** Samuga Media public website
- **Source repository:** `Mutte69/Samuga-Media`
- **Source commit:** `7963440ca265ee3d2752d91065e7207ceda72635`
- **Approved public statement:** **Maldives, as it happens.** / *From every island to every screen.*

## What was preserved

This build does not replace the existing news product. It preserves the existing:

- story and article API contracts;
- homepage article-preview cards;
- EN/DV filtering and Thaana article direction;
- article rendering, bylines, covers, related stories and share controls;
- Ask Samuga AI endpoint and floating experience;
- site settings, dynamic advertisements and banner fallback;
- analytics scripts and tracking proxy;
- author data and article links;
- Cloudflare Pages static deployment and Pages Functions;
- complete admin dashboard and every admin asset byte-for-byte.

## User-approved public experience

### Header

- Thin sticky bar using Samuga blue `#29B8FE`.
- Hamburger sits at the outer left edge before the logo.
- Supplied white Samuga Media logo is used in the header.
- EN/DV and light/dark controls stay on the right.
- Old public category strip is retained privately as the existing category-control source, but hidden visually so the new drawer can trigger the same filters without rebuilding category logic.

### Drawer

- One continuous matte powder-blue panel; no separate logo block.
- 280 ms left-slide animation with a soft page overlay.
- White Samuga Media logo directly on the powder-blue background.
- Ask Samuga AI opens the existing chat experience.
- Official social icon row; unconfigured URLs are disabled instead of guessed.
- Existing categories trigger the same homepage filter buttons.
- Free email subscription includes email validation, consent, status feedback and a bot honeypot.
- About, advertising, contact and policy links remain available.

### Feed, advertising and article preview

- Existing card markup and visual language are intentionally retained.
- Dynamic ads from the current backend remain first priority.
- Ad insertion changes from every six visible stories to every three visible stories.
- Sponsor fallback behavior remains intact when the backend has no live campaign.
- Ask Samuga AI remains visible.

### Footer

- Clean dark-navy footer shared by homepage, article and policy pages.
- White Samuga logo.
- Approved statement and supporting line.
- Social and essential newsroom links only.
- Samuga Creative ownership remains visible without crowding the design.

## Newsletter architecture

### Browser endpoint

`POST /api/newsletter/subscribe`

Accepted browser payload:

```json
{
  "email": "reader@example.com",
  "terms": true,
  "company": "",
  "language": "en",
  "referrer": "https://samugamedia.com/"
}
```

### Server-side behavior

- Cloudflare Pages Function only; the provider key never reaches browser JavaScript.
- Requires `BUTTONDOWN_API_KEY` in Cloudflare Pages environment variables.
- 8 KB request limit.
- Email length and format validation.
- Explicit Terms/Privacy consent.
- Quiet honeypot response for simple bots.
- Safe duplicate handling.
- Provider errors are not exposed to readers.
- Temporary provider failure returns HTTP 503.
- The provider's confirmation state is not overridden, preserving double opt-in.

### Every-post email delivery

`GET /feed.xml` produces a 50-item RSS feed from the existing public story API. Buttondown RSS automation can use this feed to send each newly published story to confirmed subscribers. No News Bot publishing path or article database was changed.

## Research decisions applied

- **Accessible drawer:** implemented as a modal dialog with focus containment, Escape close, focus restoration and background inert state, following W3C/WAI dialog guidance.
- **Motion:** smooth but short animation with a `prefers-reduced-motion` override.
- **Theme:** existing manual preference is preserved and still falls back to the operating-system preference.
- **Layout stability:** explicit logo dimensions, fixed header height and reserved ad media height reduce avoidable layout movement.
- **Newsletter safety:** subscription is performed server-side and keeps confirmation-based consent instead of creating active subscribers directly.
- **RSS delivery:** a separate public feed allows email automation without coupling the frontend to the News Bot publishing code.

## Files added

- `site-v3.css`
- `samuga-v3-shell.js`
- `site-social-links.json`
- `assets/Samuga_Media_Logo_White.png`
- `assets/Samuga_Media_Mark_White.png`
- `functions/api/newsletter/subscribe.js`
- `functions/feed.xml.js`
- `BUILD_16_0_0_NOTES.md`
- `BUILD_16_0_0_DEPLOYMENT.txt`
- `BUILD_16_0_0_NEWSLETTER_VARS.txt`
- `SAMUGA_MEDIA_V3_IMPLEMENTATION_AUDIT.md`

## Files updated

- `index.html`
- `article.html`
- `about.html`
- `advertising.html`
- `contact.html`
- `editorial-policy.html`
- `corrections-policy.html`
- `privacy-policy.html`
- `terms.html`
- `site-build15-9-8.js`
- `article-build15-9-8.js`
- `functions/article.js`
- `functions/story.js`
- `_headers`

## Regression and package verification

Passed:

- JavaScript syntax checks for all changed browser and Pages Function files.
- Public-page structure tests for header order, white logo, V3 CSS and V3 shell.
- Homepage and policy-footer statement tests.
- Seven-story rendered feed test with exactly two ads after stories 3 and 6.
- Responsive drawer geometry, open state, Escape close, AI button and newsletter presence.
- Newsletter Function tests: missing key 503, valid request 202 and invalid email 400.
- RSS Function XML generation and escaping test.
- Server-rendered article Function test for V3 header, footer, CSS and shell.
- Existing admin HTML, JavaScript and CSS hashes remained unchanged.
- ZIP integrity and secret-pattern scan.

## Honest limitations before production activation

1. Telegram is the only social destination already known with certainty. Facebook, Instagram, X, TikTok, YouTube and WhatsApp are intentionally blank in `site-social-links.json`; add the exact official URLs before launch or let `/api/site-settings` provide them.
2. Subscription delivery is implemented but cannot send real email until `BUTTONDOWN_API_KEY` is set and the `/feed.xml` RSS automation is enabled in Buttondown.
3. No live production deployment, real subscription, real email delivery, public advertisement click or live Samuga AI request was performed during offline QA.
