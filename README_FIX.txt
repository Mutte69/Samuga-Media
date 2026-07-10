Samuga Media fixed Cloudflare Pages files

What was fixed:
1. Removed the redirect-loop setup.
2. Replaced the duplicate worker approach with one Cloudflare Pages _worker.js.
3. /article?id=ARTICLE_ID now works for real users without redirecting.
4. Facebook, WhatsApp, Telegram, X, LinkedIn and Discord crawlers receive real Open Graph meta tags.
5. Home page article links now use /article?id=... instead of article.html?id=...
6. _redirects is intentionally empty because article routing is handled by _worker.js.

Upload these files to the root of the GitHub repo:
- index.html
- article.html
- styles.css
- script.js
- _worker.js
- _routes.json
- _redirects
- CNAME

Important:
- Delete old cloudflare-worker.js from the repo.
- Delete old files with names like "_worker (1).js", "article (5).html", "script (4).js" etc.
- Make sure the deployed files have the clean exact names above.
- Do not add any extra Cloudflare Dashboard Worker route for samugamedia.com/article*.
- Cloudflare Pages will automatically use _worker.js from the repo.

After deploy:
1. Open https://samugamedia.com/article?id=YOUR_ARTICLE_ID
2. If it still loops, clear Cloudflare cache and browser cache.
3. Test preview in Facebook Sharing Debugger or by sending the link on WhatsApp/Telegram.
