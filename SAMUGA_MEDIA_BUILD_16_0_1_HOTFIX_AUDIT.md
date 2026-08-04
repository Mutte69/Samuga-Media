# Samuga Media Build 16.0.1 — Hotfix Audit

## Scope

This hotfix repairs the V3 public experience reported on iPhone and desktop. It preserves the existing news API contract, article previews, article pages, admin dashboard, analytics, ad model, language switch, theme switch and Samuga AI backend.

## Files changed

### Public runtime

- `index.html`
- `article.html`
- `about.html`
- `advertising.html`
- `contact.html`
- `corrections-policy.html`
- `editorial-policy.html`
- `privacy-policy.html`
- `terms.html`
- `site-build16-0-1.js`
- `site-v3-16-0-1.css`
- `samuga-v3-shell-16-0-1.js`
- `site-common-build16-0-1.js`
- `article-build16-0-1.js`

### Pages Functions

- `functions/api/stories.js`
- `functions/api/site-settings.js`
- `functions/api/ads.js`
- `functions/api/banner.js`
- `functions/api/article.js`
- `functions/api/chat.js`
- `functions/api/newsletter/subscribe.js`
- `functions/article.js`
- `functions/story.js`

### Documentation and regression test

- `BUILD_16_0_1_NOTES.md`
- `BUILD_16_0_1_DEPLOYMENT.txt`
- `QA_REPORT_BUILD_16_0_1.md`
- `build16_0_1_mobile_stability_tests.py`

## Confirmed production defects and repairs

### Mobile homepage remained on skeletons

The homepage read `safeStorage.get(...)` before the `const safeStorage` declaration. JavaScript throws before `DOMContentLoaded` registration in that state. The storage wrapper is now declared before first use, and startup tasks are isolated with `Promise.allSettled`.

### Cross-origin fragility

Stories, settings, ads, banner, articles and chat now try same-origin `/api/...` routes first, then fall back to the current Railway API. This reduces mobile/in-app browser failures without replacing the backend.

### Dhivehi drawer geometry

The fixed drawer and overall shell stay LTR. Dhivehi text blocks, category labels, consent text and story content receive RTL direction locally. The drawer no longer moves to the wrong edge or clips horizontally.

### Incomplete drawer

The drawer is independently scrollable with dynamic viewport height, opens at `scrollTop = 0`, prevents horizontal overflow, and keeps the logo/close area sticky.

### Social controls

Configured social URLs open in a new tab. Unconfigured icons are still interactive and show an honest configuration message instead of silently doing nothing. Exact official URLs remain external configuration and were not guessed.

### Oversized mobile AI panel

Ask Samuga AI remains present. Its mobile panel is capped to a compact portion of the visual viewport and expands only when the keyboard requires it.

### Newsletter status

The secure API-key implementation remains server-side. It works only where the `/functions` directory is executed as Pages Functions. The observed static GitHub Pages deployment cannot execute that endpoint; the code does not expose the Buttondown key in the browser.

## Preserved contracts

- Existing `GET /api/stories` response and normalizer
- Existing article preview structure
- Existing ad placement after every three visible stories
- Existing article URLs and rendering
- Existing Ask Samuga AI request contract
- Existing admin/dashboard files, verified byte-for-byte unchanged
- Existing analytics and page-transition scripts
