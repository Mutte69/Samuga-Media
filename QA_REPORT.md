# QA report — Samuga Media Platform Build 2

## Automated checks completed

- All 14 Python source files parsed and compiled successfully with Python 3.13.
- All 7 website JavaScript and Cloudflare Pages Function files passed `node --check`.
- All HTML pages passed duplicate-ID and local-resource checks.
- Literal JavaScript ID selectors matched their HTML: 114 dashboard selectors and 32 homepage selectors, with no missing elements.
- `styles.css` and `admin.css` parsed with no CSS syntax errors.
- 110 literal SQL calls were checked for `%s` placeholder/value mismatches; none were found.
- The CMS article upsert has 31 placeholders and 31 supplied values and now confirms the database returned the saved article ID before reporting success.
- The bot exposes 34 Flask API routes, including 20 authenticated newsroom routes, with no duplicate method/path registrations.
- No duplicate top-level Python function definitions were introduced.
- Both Cloudflare article route files passed a mocked render test confirming headline → subheadline → byline → cover → body order, cover captions, and updated timestamps.
- The article and legacy story renderers are synchronized so old `/story` links do not receive the previous layout.
- No hard-coded Telegram bot token, PostgreSQL URL, GitHub token, or OpenAI-style API key was detected in source files.
- Claude's author-profile patch and the earlier editorial consistency protections remain included.

## Runtime tests still required after deployment

The real PostgreSQL database, Railway volume, Telegram, Facebook, X, and Cloudflare credentials are not available in this build environment. Test these on a private draft before replacing production:

1. Railway startup migrations and Super Admin seed.
2. Draft save, revision history, and browser recovery.
3. Scheduled publishing five minutes ahead.
4. Image and short-video upload, followed by a Railway restart to confirm `/data` persistence.
5. Telegram, Facebook, and X separately, including a failed-share retry.
6. Cloudflare article social previews and both `/article` and legacy `/story` routes.
7. Desktop and mobile layouts in light and dark mode.
8. Advertisement start/end windows and full-artwork banner fit.
