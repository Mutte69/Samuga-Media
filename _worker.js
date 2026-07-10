/**
 * Samuga Media — Cloudflare Pages Worker
 *
 * ONLY intercepts /article requests from social crawlers.
 * Returns a lightweight HTML page with real OG meta tags.
 * Does NOT touch /article.html or any other URL — those pass through to assets.
 * Real users hitting /article get redirected to article.html by browser normally.
 */

const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const DEFAULT_IMG = "https://samugamedia.com/assets/SamugaNewsBot_Profile.png";

const CRAWLERS = [
  "facebookexternalhit", "facebot", "twitterbot", "linkedinbot",
  "slackbot", "telegrambot", "whatsapp", "discordbot",
  "googlebot", "applebot", "bingbot", "iframely", "meta-externalagent",
];

function isCrawler(ua) {
  return CRAWLERS.some(b => (ua||"").toLowerCase().includes(b));
}

function esc(s) {
  return String(s||"").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;").slice(0,500);
}

async function getArticleMeta(id) {
  try {
    const r = await fetch(`${RAILWAY_API}/api/article?id=${encodeURIComponent(id)}`, {
      headers: { "User-Agent": "Mozilla/5.0 Cloudflare-Worker", "Accept": "application/json" },
      cf: { cacheTtl: 300, cacheEverything: true }
    });
    if (!r.ok) return null;
    const d = await r.json();
    if (d.error) return null;
    return {
      title: (d.title || "Samuga Media").trim(),
      desc:  (d.seo?.description || d.excerpt || d.summary || "Live Maldives news.").trim(),
      image: d.cover_image || DEFAULT_IMG,
    };
  } catch { return null; }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const id = url.searchParams.get("id");
    const ua = request.headers.get("user-agent") || "";

    // ONLY intercept /article (extensionless) requests from social crawlers
    // Everything else — pass through to static assets untouched
    if (url.pathname !== "/article" || !id || !isCrawler(ua)) {
      return env.ASSETS.fetch(request);
    }

    // Crawler hit /article?id=... — serve a real HTML page with OG tags
    const meta = await getArticleMeta(id);
    const title = meta?.title || "Samuga Media";
    const desc  = meta?.desc  || "Live Maldives news powered by Samuga AI.";
    const img   = meta?.image || DEFAULT_IMG;
    const articleUrl = `https://samugamedia.com/article.html?id=${encodeURIComponent(id)}`;

    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>${esc(title)} | Samuga Media</title>
  <meta name="description" content="${esc(desc)}">
  <link rel="canonical" href="${articleUrl}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Samuga Media">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(desc)}">
  <meta property="og:image" content="${esc(img)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="${articleUrl}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(desc)}">
  <meta name="twitter:image" content="${esc(img)}">
  <meta http-equiv="refresh" content="0;url=${articleUrl}">
</head>
<body>
  <p><a href="${articleUrl}">${esc(title)}</a></p>
  <script>window.location.replace("${articleUrl}")</script>
</body>
</html>`;

    return new Response(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=300",
      }
    });
  }
};
