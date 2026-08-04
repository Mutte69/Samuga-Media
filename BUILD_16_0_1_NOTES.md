# Samuga Media Build 16.0.1 — Mobile Stability Hotfix

Build 16.0.1 fixes the production regressions observed after the V3 public-shell release. It does not redesign the article cards, admin dashboard, publishing API, article model, analytics, or Samuga AI workflow.

## Fixed

- Fixed a fatal homepage initialization error where `safeStorage` was referenced before it was initialized. On affected mobile browsers this left the three loading skeleton cards on screen forever.
- Guarded all active public `localStorage` reads/writes for Safari, Facebook in-app browser, private browsing, and restricted-storage contexts.
- Added same-origin public API proxy routes with the existing Railway API retained as a fallback.
- Kept the application shell left-to-right in both languages; only Dhivehi text blocks use right-to-left direction.
- Fixed the Dhivehi drawer clipping/reversal on iPhone.
- Made the drawer use `100dvh`, vertical scrolling, hidden horizontal overflow, and a sticky top/close area.
- Reset drawer scroll position whenever it opens, so English and Dhivehi menus always begin at the logo.
- Removed dead social controls. Configured links open normally; unconfigured icons are tappable and clearly report that the link is awaiting configuration.
- Reduced the mobile Ask Samuga AI panel from a full-screen takeover to a compact bottom sheet while retaining keyboard-aware resizing.
- Kept the existing article-preview markup and advertisement insertion after every three visible stories.
- Preserved the existing floating Ask Samuga AI button.

## Deployment note

The public stories now work on a static host through the direct Railway fallback. The optional `/functions` proxies and `/api/newsletter/subscribe` endpoint require a host that executes Cloudflare Pages Functions. A static GitHub Pages deployment will serve the frontend but will not execute those server-side files.

## Social URLs

`site-social-links.json` remains the safe place for exact official URLs. Telegram is configured. Other networks are not guessed by the build.
