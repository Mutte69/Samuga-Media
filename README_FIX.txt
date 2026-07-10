SAMUGA MEDIA — NUCLEAR REDIRECT LOOP FIX

This version fixes ERR_TOO_MANY_REDIRECTS by making /article?id=... fully server-rendered inside _worker.js.

Why this fixes it:
Cloudflare Pages can redirect article.html -> /article because of clean URLs.
The old worker fetched article.html from assets, so Cloudflare redirected back to /article, causing a loop.
This new worker never fetches article.html for article pages. It fetches article data from Railway and returns the full HTML directly.

Upload these files to the ROOT of your GitHub repo:
- index.html
- article.html
- styles.css
- script.js
- _worker.js
- _routes.json
- _redirects
- CNAME

Very important:
1. Delete old cloudflare-worker.js from GitHub.
2. Delete any old _redirects content that says /article /article.html 200.
3. Make sure the file is named exactly _redirects, not _redirects.txt.
4. Make sure the file is named exactly _worker.js, not _worker (1).js.
5. Redeploy Cloudflare Pages.
6. Test in private/incognito window:
   https://samugamedia.com/article?id=manual_46a74b9aafbc

Social preview:
The preview image comes from cover_image in the Railway /api/article response.
If cover_image is missing, it uses Samuga default image.
