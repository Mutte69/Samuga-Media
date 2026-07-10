SAMUGA MEDIA FINAL ARTICLE FIX

WHAT CHANGED
- This version removes static article.html completely.
- /article?id=ARTICLE_ID is now handled only by Cloudflare Pages Function: functions/article.js
- This stops Cloudflare clean-url conflicts and gives Facebook/WhatsApp/Telegram real server-side OG tags.
- Homepage links are now /article?id=...

VERY IMPORTANT GITHUB CLEANUP
Delete these old files if they exist in the repo:
- article.html
- article (anything).html
- _worker.js
- _worker (1).js
- _routes.json
- cloudflare-worker.js
- _redirects.txt

Upload this exact structure:
index.html
styles.css
script.js
CNAME
_redirects
functions/article.js
functions/story.js

TEST AFTER CLOUDFLARE DEPLOY
1. Open https://samugamedia.com/article?id=manual_46a74b9aafbc
2. In Meta Sharing Debugger, paste the same URL and press Scrape Again.
3. Expected: Response Code 200, og:url present, article cover image.

If Facebook still shows old preview, press Scrape Again 2-3 times because Facebook caches.
