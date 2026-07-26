# Build 6 QA Report

Validated before packaging:

- Public pages contain no Newsroom login link.
- Oversized homepage lead section is hidden without removing the existing rendering code.
- Breaking strip, category controls and full mobile Ask Samuga AI button are present.
- Content Lab dashboard view, live badge, card preview and all five actions are wired.
- Every website JavaScript file passed Node syntax validation.
- All HTML pages passed duplicate-ID and local-resource checks.
- No generated cache files are included.

Live production credentials and external Telegram, Facebook, Instagram, X, Railway and Cloudflare services were not invoked in the build environment. Use one disposable Content Lab card for the first production test.
