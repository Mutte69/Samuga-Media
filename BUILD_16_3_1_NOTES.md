# Samuga Media Web Build 16.3.1

## Correctness, runtime parity and security hardening

Build 16.3.1 is the matching website/admin release for Samuga News Bot 18.3.1.

## Newsroom source controls

- Source-mode saves now require the backend to return PostgreSQL verification.
- The dashboard does not show a success toast when persistence is unverified.
- The source panel displays pending, processing, retryable, deferred and failed ARGUS work plus the oldest active age.
- The save indicator displays the persistence revision returned by the backend.

## Generation recovery

- Added the AI generation recovery panel.
- Editors can inspect failed/retryable jobs and trigger audited retry or verified source-copy recovery.
- Recovery actions do not auto-publish.

## Publishing

- Instagram is available as a first-class manual publishing target alongside Telegram, Facebook and X.
- The existing durable backend publishing queue remains authoritative.

## Cloudflare runtime

- Public and SSR functions share `functions/_lib/runtime.js`.
- Backend routing uses `SAMUGA_API_BASE` with one centralized safe fallback.
- All audited upstream requests use explicit timeouts.
- Invalid chat JSON returns HTTP 400 rather than a false provider-outage response.
- Edge requests can forward a signed hashed client identity using `SAMUGA_EDGE_PROXY_SECRET`.
- Dynamic article/story functions load the current 16.2.1 shell/settings assets and identify the release as 16.3.1.

## Browser security

Site-wide headers now include:

- HSTS.
- X-Content-Type-Options.
- X-Frame-Options: DENY.
- Referrer-Policy.
- Permissions-Policy.
- Cross-Origin-Opener-Policy.
- Content-Security-Policy-Report-Only for staged rollout.

## Reproducibility

- Added `package-lock.json`.
- Added one current test runner and release manifest.
- Historical test files remain preserved but are not mixed into the current pass/fail release gate.

## Cloudflare environment

```text
SAMUGA_API_BASE=https://samuga-news-bot-production.up.railway.app
SAMUGA_EDGE_PROXY_SECRET=<same long random value used in Railway>
```
