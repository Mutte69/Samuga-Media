# QA Report — Samuga Media Build 16.0.0

## Result

**PASS for offline deployment package QA.**

## Automated checks

- All JavaScript files in the complete website tree passed `node --check`.
- All static public pages contain Build 16.0.0, V3 CSS, V3 shell, hamburger-before-logo order and the white Samuga logo.
- Static page IDs are unique.
- Homepage, article and policy footers use the approved Samuga statement.
- Existing admin HTML/CSS/JS SHA-256 hashes are unchanged from the uploaded source ZIP.
- Feed rendering with seven mock stories produced seven cards and two advertisements, after story 3 and story 6.
- Responsive drawer opened at mobile width, exposed AI and newsletter controls, and closed with Escape.
- Newsletter Function returned 503 without its secret, 202 for a valid mocked provider request, and 400 for invalid email.
- RSS Function returned valid escaped RSS markup in the mocked API test.
- Server-rendered article Function included the V3 header, supplied white logo, V3 stylesheet, approved footer and V3 shell.
- Secret-pattern scan passed.
- Complete and updated-only ZIP integrity tests passed.

## Not live-tested

- Cloudflare Pages deployment.
- Real Buttondown subscription and confirmation email.
- Buttondown RSS automation delivery.
- Production social links other than Telegram.
- Live public API, advertisement, analytics and Samuga AI calls.
