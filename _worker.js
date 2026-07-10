const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const DEFAULT_IMG = "https://samugamedia.com/assets/SamugaNewsBot_Profile.png";

const CRAWLERS = [
  "facebookexternalhit", "facebot", "twitterbot", "linkedinbot",
  "slackbot", "telegrambot", "whatsapp", "discordbot",
  "googlebot", "applebot", "bingbot", "iframely", "meta-externalagent",
];

function isCrawler(ua) {
  const lower = (ua || "").toLowerCase();
  return CRAWLERS.some(bot => lower.includes(bot));
}

function esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;").slice(0,400);
}

async function getArticleMeta(articleId) {
  try {
    const res = await fetch(
      `${RAILWAY_API}/api/article?id=${encodeURIComponent(articleId)}`,
      { headers: { "User-Agent": "Cloudflare-Worker/1.0", "Accept": "application/json" },
        cf: { cacheTtl: 300, cacheEverything: true } }
    );
    if (!res.ok) return null;
    const d = await res.json();
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
    const path = url.pathname;
    const articleId = url.searchParams.get("id");

    // Intercept both /article.html and /article (Cloudflare Pages strips .html)
    const isArticle = path === "/article.html" || path === "/article" || path.endsWith("/article.html") || path.endsWith("/article");

    if (!isArticle || !articleId) {
      return env.ASSETS.fetch(request);
    }

    const ua = request.headers.get("user-agent") || "";
    if (!isCrawler(ua)) {
      return env.ASSETS.fetch(request);
    }

    const [pageRes, meta] = await Promise.all([
      env.ASSETS.fetch(new Request(`${url.origin}/article.html?id=${encodeURIComponent(articleId)}`, request)),
      getArticleMeta(articleId),
    ]);

    if (!pageRes.ok) return pageRes;

    const title    = meta?.title || "Samuga Media";
    const desc     = meta?.desc  || "Live Maldives news powered by Samuga AI.";
    const image    = meta?.image || DEFAULT_IMG;
    const canonical = `https://samugamedia.com/article.html?id=${encodeURIComponent(articleId)}`;

    const tags = `
  <title>${esc(title)} | Samuga Media</title>
  <meta name="description" content="${esc(desc)}">
  <link rel="canonical" href="${canonical}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Samuga Media">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(desc)}">
  <meta property="og:image" content="${esc(image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="${canonical}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(desc)}">
  <meta name="twitter:image" content="${esc(image)}">`;

    return new HTMLRewriter()
      .on("head", { element(el) { el.prepend(tags, { html: true }); } })
      .on("title", { element(el) { el.setInnerContent(`${title} | Samuga Media`); } })
      .on('meta[id="ogTitle"]',  { element(el) { el.setAttribute("content", title); } })
      .on('meta[id="ogDesc"]',   { element(el) { el.setAttribute("content", desc);  } })
      .on('meta[id="ogImage"]',  { element(el) { el.setAttribute("content", image); } })
      .on('meta[id="twTitle"]',  { element(el) { el.setAttribute("content", title); } })
      .on('meta[id="twDesc"]',   { element(el) { el.setAttribute("content", desc);  } })
      .on('meta[id="twImage"]',  { element(el) { el.setAttribute("content", image); } })
      .transform(pageRes);
  },
};
