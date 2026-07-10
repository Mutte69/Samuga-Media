SAMUGA MEDIA SOCIAL PREVIEW FIX - /story URL VERSION

Why this version exists:
Cloudflare Pages can create a 308 clean-url redirect conflict around /article because article.html also exists.
Facebook Sharing Debugger shows this as: Could Not Follow Redirect, Response Code 308.

This version avoids that conflict by using /story?id=ARTICLE_ID for all new article links.
/story does not conflict with article.html, so Facebook/WhatsApp/Telegram should receive a direct 200 HTML response with OG tags.

Upload these exact files to the root of your GitHub repo:
- index.html
- article.html
- styles.css
- script.js
- _worker.js
- _routes.json
- _redirects
- CNAME

Also delete old duplicate files from GitHub root if present:
- cloudflare-worker.js
- _worker (1).js
- _redirects.txt
- index (11).html
- article (5).html
- script (4).js
- styles (4).css
- CNAME (4).txt

After Cloudflare Pages redeploys, test this style of URL:
https://samugamedia.com/story?id=manual_46a74b9aafbc

Then paste that /story URL into Facebook Sharing Debugger and click Scrape Again.
Expected result:
- Response Code: 200
- No Could Not Follow Redirect warning
- Link preview uses article title, description and cover image if the API has cover_image.

Important:
Facebook caches old previews. Always click Scrape Again after deployment.
If the preview image is still Samuga profile image, the article API probably has no cover_image or the cover_image is not a public HTTPS image.
