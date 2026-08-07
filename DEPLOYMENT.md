# Deployment — Samuga Media website

## 1. Deploy the bot first

The matching bot ZIP creates the newsroom database tables and serves the new APIs. Wait until Railway reports a healthy deployment before publishing this site.

## 2. Deploy this folder to Cloudflare Pages

Use the repository root as the Pages output directory. No build command is required because this is a static site with Pages Functions.

Required files at the deployed root include:

- `index.html`
- `styles.css`
- `script.js`
- `admin.html`
- `admin.css`
- `admin.js`
- `functions/article.js`
- `functions/story.js`
- `_redirects`


## API address

This website currently points to:

```text
https://samuga-news-bot-production.up.railway.app
```

If the Railway service domain changes, update the `API` constant in `script.js`, `admin.js`, `article-client.js`, `functions/article.js`, and `functions/story.js` before deploying Cloudflare Pages.

## 3. Test in this order

1. Open the homepage and switch light/dark mode.
2. Open an existing article and verify its social preview and cover.
3. Open `/admin.html` and sign in.
4. Save a draft.
5. Upload a small image.
6. Publish a test article without social sharing.
7. Open the public article.
8. Test Telegram, then Facebook, then X one at a time.
9. Upload a short test video and confirm it remains available after a Railway restart.

## Rollback

Keep the previous Cloudflare Pages deployment available. If the bot APIs are not ready, roll back the Pages deployment before changing the database manually.

## Build 2 browser checks

After Cloudflare Pages deploys:

1. Hard refresh the homepage and verify both light and dark themes.
2. Check one desktop sponsor banner and one mobile banner; full artwork should remain visible when fit mode is **Show full artwork**.
3. Open an article and verify the order is headline → subheadline → byline → cover → body.
4. Open `/admin.html`, save a draft, refresh the page and test browser recovery.
5. Test Preview, History, Media library and one scheduled article before using the workflow for live breaking news.

## Build 3 + 4 checks

1. Open the Dhivehi homepage and confirm headlines use thin, regular Thaana letters with comfortable spacing.
2. Open **Newsroom → Publishing** and run **Check connections**. This does not create a social post.
3. Publish one private test article to Telegram only. Confirm the job changes from queued/processing to succeeded.
4. Retry or cancel a test queue job from the Publishing Centre.
5. Upload a short `.mov` phone video. Keep the page open until the cover picker reports **Ready**.
6. Confirm a poster appears in the Media Library and the public feed does not preload the full video.
7. Reply to a test video in the Telegram Core Team group with `/webmedia`; verify it appears in Newsroom → Media.
8. Restart Railway and confirm previously uploaded media is still available.

## Build 16.3.1 production hardening

Cloudflare Pages Functions now read the backend address from the `SAMUGA_API_BASE` environment binding. The production Railway URL remains only as the shared runtime fallback, so a backend-domain change no longer requires editing every function.

Set these Cloudflare Pages environment values:

```text
SAMUGA_API_BASE=https://samuga-news-bot-production.up.railway.app
SAMUGA_EDGE_PROXY_SECRET=<same long random secret used in Railway>
```

`SAMUGA_EDGE_PROXY_SECRET` signs a hashed edge client identifier before forwarding public requests to Railway. Set exactly the same value in both deployments.

After deployment:

1. Open **Admin → Newsroom Sources** and confirm the current mode and PostgreSQL save revision load correctly.
2. Test a mode change and confirm the UI reports **Saved in PostgreSQL** before reloading.
3. Open **AI Usage & Diagnostics → Generation recovery** and confirm failed/retryable jobs load.
4. Test manual publishing to Instagram with a non-public test article.
5. Send malformed JSON to `/api/chat`; it should return HTTP 400, while an upstream timeout should return a provider/timeout error instead.
6. Confirm the browser receives HSTS, frame protection, referrer, permissions and report-only CSP headers.

Current release gate:

```text
python3 run_current_tests.py
```
