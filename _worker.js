/**
 * Samuga Media — Cloudflare Pages Worker (_worker.js)
 *
 * Intercepts /article.html?id=... requests.
 * For social crawlers: fetches real article data from Railway API,
 * injects OG meta tags so Facebook/X/Telegram show a proper preview.
 * For real users: serves the static file unchanged (JS runs as normal).
 *
 * Place this file in the ROOT of the Samuga-Media GitHub repo.
 * Cloudflare Pages picks it up automatically on next deploy.
 */

const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const DEFAULT_IMG = "https://samugamedia.com/assets/SamugaNewsBot_Profile.png";

const CRAWLERS = [
  "facebookexternalhit",
  "twitterbot",
  "linkedinbot",
  "slackbot",
  "telegrambot",
  "whatsapp",
  "discordbot",
  "googlebot",
  "applebot",
  "bingbot",
  "pinterestbot",
  "iframely",
];

function isCrawler(ua) {
  if (!ua) return false;
  const lower = ua.toLowerCase();
  return CRAWLERS.some(bot => lower.includes(bot));
}

function esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .slice(0, 400);
}

async function getArticleMeta(articleId) {
  try {
    const res = await fetch(
      `${RAILWAY_API}/api/article?id=${encodeURIComponent(articleId)}`,
      { cf: { cacheTtl: 300, cacheEverything: true } }
    );
    if (!res.ok) return null;
    const d = await res.json();
    if (d.error) return null;
    return {
      title:  d.title || "Samuga Media",
      desc:   d.seo?.description || d.excerpt || d.summary || "Live Maldives news.",
      image:  d.cover_image || DEFAULT_IMG,
    };
  } catch {
    return null;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Only intercept article.html with an id param
    const isArticle = url.pathname === "/article.html" || url.pathname.endsWith("/article.html");
    const articleId = url.searchParams.get("id");

    if (!isArticle || !articleId) {
      // All other requests → serve static asset normally
      return env.ASSETS.fetch(request);
    }

    const ua = request.headers.get("user-agent") || "";

    if (!isCrawler(ua)) {
      // Real user → serve article.html unchanged, JS handles meta tags
      return env.ASSETS.fetch(request);
    }

    // Social crawler → inject real meta tags
    const [pageRes, meta] = await Promise.all([
      env.ASSETS.fetch(request),
      getArticleMeta(articleId),
    ]);

    if (!meta || !pageRes.ok) {
      return pageRes;
    }

    const canonical = `https://samugamedia.com/article.html?id=${encodeURIComponent(articleId)}`;

    const injected = `
  <title>${esc(meta.title)} | Samuga Media</title>
  <meta name="description"        content="${esc(meta.desc)}">
  <link rel="canonical"           href="${canonical}">
  <meta property="og:type"        content="article">
  <meta property="og:site_name"   content="Samuga Media">
  <meta property="og:title"       content="${esc(meta.title)}">
  <meta property="og:description" content="${esc(meta.desc)}">
  <meta property="og:image"       content="${esc(meta.image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url"         content="${canonical}">
  <meta name="twitter:card"        content="summary_large_image">
  <meta name="twitter:title"       content="${esc(meta.title)}">
  <meta name="twitter:description" content="${esc(meta.desc)}">
  <meta name="twitter:image"       content="${esc(meta.image)}">`;

    // Inject into <head> using HTMLRewriter
    return new HTMLRewriter()
      .on("head", { element(el) { el.prepend(injected, { html: true }); } })
      .on("title", { element(el) { el.setInnerContent(`${meta.title} | Samuga Media`); } })
      .on('meta[id="ogTitle"]',  { element(el) { el.setAttribute("content", meta.title); } })
      .on('meta[id="ogDesc"]',   { element(el) { el.setAttribute("content", meta.desc);  } })
      .on('meta[id="ogImage"]',  { element(el) { el.setAttribute("content", meta.image); } })
      .on('meta[id="twTitle"]',  { element(el) { el.setAttribute("content", meta.title); } })
      .on('meta[id="twDesc"]',   { element(el) { el.setAttribute("content", meta.desc);  } })
      .on('meta[id="twImage"]',  { element(el) { el.setAttribute("content", meta.image); } })
      .transform(pageRes);
  },
};
