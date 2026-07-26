# Samuga Media Build 9

## Added
- Article editor resets to a clean new article after a successful Publish now action.
- Super Admin author deletion with safe reassignment of existing articles and linked logins.
- Social Card Creation dashboard using the existing cards.py renderer and Telegram/social publishing functions.
- First-party web analytics dashboard: pageviews, visitors, daily trend, top pages, devices, referrers and languages.
- Privacy design: no raw reader IP addresses are stored; session identifiers are irreversibly hashed.

## Deployment
1. Deploy the Build 9 backend to Railway first.
2. Wait for database migrations to finish.
3. Deploy the Build 9 website to Cloudflare Pages.
4. Test one disposable social card and one duplicate-author deletion/merge.
