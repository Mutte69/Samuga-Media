# Samuga Media Build 16.2.0 — Full Audit Fix

Build 16.2.0 is based on **Build 16.1.0 Website Settings** and focuses on restoring a stable public experience across the homepage, information pages, server-rendered articles, the navigation drawer and Samuga AI.

## Critical fixes

### 1. `ERR_TOO_MANY_REDIRECTS` on Ask Samuga AI

The old `_redirects` file rewrote `/ask-samuga-ai` to `/ask-samuga-ai.html`. Cloudflare's clean/pretty URL handling could then return the `.html` address to the clean address, creating a loop.

Build 16.2.0 removes that rewrite completely. Every public link and canonical now uses:

`/ask-samuga-ai`

### 2. Real standalone Samuga AI page

The old AI page was not a separate chatbot. It depended on the floating homepage widget being injected, opened and restyled after load.

Build 16.2.0 provides a proper dedicated chat page with:

- its own chat form and message area;
- its own session history;
- clear-chat control;
- prompt suggestions;
- Enter to send and Shift+Enter for a new line;
- responsive desktop and mobile layout;
- English/Dhivehi interface updates;
- clean API fallback through the Cloudflare proxy and Railway backend.

The sidebar **Ask Samuga AI** control now opens this dedicated page.

### 3. Floating AI is actually floating

The public floating button and panel are moved directly under `<body>` and forced into a top-level fixed layer. This prevents a footer, grid, transformed ancestor or stacking context from trapping the button at the bottom of the page.

The floating widget now includes:

- fixed bottom-left or bottom-right positioning;
- mobile safe-area spacing;
- top-level z-index;
- mobile full-screen panel behavior;
- independent chat history;
- idempotent event binding to prevent duplicate sends.

### 4. Server-rendered article pages brought onto Build 16.2.0

Cloudflare Functions at `/article` and `/story` were still generating the older 16.0.1 shell even when the static website used a newer build.

They now load:

- Build 16.2.0 drawer shell;
- Build 16.2.0 website-settings runtime;
- Build 16.2.0 fixed/sticky header behavior;
- clean extensionless footer links;
- current build metadata.

### 5. Cache mismatch prevention

The `_headers` policy now explicitly prevents public HTML, clean routes, articles, the AI page and the admin dashboard from being frozen in Cloudflare cache. Versioned JavaScript and CSS assets remain immutable for performance.

This reduces mixed-build failures where new HTML loads an older JavaScript or CSS bundle.

## Additional reliability improvements

- Sidebar and floating AI visibility follow Website Settings independently.
- String settings such as `"false"` are parsed correctly instead of being treated as enabled.
- AI button position is restricted to supported values.
- Floating chat closes safely when disabled in settings.
- Local/session storage access is guarded for privacy or restricted-browser contexts.
- Homepage, shell and AI bindings are idempotent.
- Same-origin API failure can still fall through to the Railway endpoint.
- All public pages use the active settings runtime and sticky-header class.
- Admin Website Settings assets were versioned to 16.2.0 without changing the saved schema.

## Files added

- `samuga-v3-shell-16-2-0.js`
- `site-build16-2-0.js`
- `website-settings-runtime-16-2-0.js`
- `website-settings-runtime-16-2-0.css`
- `ask-samuga-ai-16-2-0.js`
- `ask-samuga-ai-16-2-0.css`
- `admin-website-settings-16-2-0.js`
- `admin-website-settings-16-2-0.css`
- `build16_2_0_full_audit_tests.py`
- `build16_2_0_function_contract_tests.mjs`

## Scope note

This package contains the complete Cloudflare Pages website and its included Functions. It does not contain or replace the separate Railway News Bot backend. The public chat proxy and frontend/backend contract were tested, but a live production deployment was not performed from this build environment.
