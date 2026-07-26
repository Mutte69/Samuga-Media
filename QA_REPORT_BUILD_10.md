# Build 10 QA Report

Passed checks:

- All backend Python files compile.
- All public, admin, analytics, article, and Cloudflare Function JavaScript files pass `node --check`.
- Cloudflare article renderer test confirms the cover is before the article copy and headline.
- Cloudflare article renderer test confirms English related stories do not appear in a Dhivehi article.
- Backend language-isolation test confirms a contaminated English Dhivehi body is replaced with Thaana and the English generator is not called.
- HTML duplicate IDs and local asset references pass.
- Public and admin CSS brace balance passes.
- No deployable page references Build 9 assets or the obsolete `/styles.css` path.

Production-only checks still required after deployment:

- Open one existing Dhivehi article whose body was previously wrong.
- Open one English article.
- Confirm the cover appears first on desktop and mobile.
- Confirm the Users table spacing with real email addresses.
