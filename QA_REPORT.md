# QA report — Samuga Media clean newsroom build

## Automated checks completed

- All 14 Python source files parsed and compiled successfully.
- All website JavaScript and Cloudflare Pages Function files passed `node --check`.
- All HTML pages were parsed for duplicate IDs and missing local file references.
- The CMS article SQL insert has 29 placeholders and 29 supplied values.
- No duplicate top-level Python function definitions were introduced.
- No hard-coded Telegram bot token, database URL or OpenAI-style secret was detected in either project.
- Every JavaScript `#id` selector used by the homepage and dashboard was checked against the matching HTML document.
- Claude's author-profile changes remain in the bot base and every new CMS article receives an author ID.

## Manual deployment tests still required

The final network integrations cannot be executed safely from this offline build environment. After deployment, test:

- PostgreSQL migrations on the real Railway database
- First Super Admin seed and login
- Railway volume persistence after restart
- Image and video upload through Railway's proxy
- Telegram, Facebook and X publishing with the real credentials
- Cloudflare Pages Function article social previews
- Mobile Safari and Android Chrome rendering

Follow the safe sequence in both deployment guides before replacing the current production deployment.
