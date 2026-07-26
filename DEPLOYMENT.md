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
