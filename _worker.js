const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const DEFAULT_IMG = "https://samugamedia.com/assets/SamugaNewsBot_Profile.png";

const CRAWLERS = [
  "facebookexternalhit", "facebot", "twitterbot", "linkedinbot",
  "slackbot", "telegrambot", "whatsapp", "discordbot",
  "googlebot", "applebot", "bingbot", "iframely", "meta-externalagent",
];

function isCrawler(ua) {
  return CRAWLERS.some(bot => (ua || "").toLowerCase().includes(bot));
}

function esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;").slice(0,400);
}

async function getArticleMeta(id) {
  try {
    const r = await fetch(`${RAILWAY_API}/api/article?id=${encodeURIComponent(id)}`, {
      headers: { "User-Agent": "Cloudflare-Worker/1.0", "Accept": "application/json" },
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
    const path = url.pathname;
    const id = url.searchParams.get("id");

    // Intercept ALL article requests — both /article.html and /article
    const isArticle = path === "/article.html" || path === "/article";
    if (!isArticle || !id) return env.ASSETS.fetch(request);

    const ua = request.headers.get("user-agent") || "";

    // For crawlers: fetch article.html directly (bypassing the 308)
    // and inject real meta tags
    if (isCrawler(ua)) {
      const [meta, pageRes] = await Promise.all([
        getArticleMeta(id),
        // Always fetch the canonical article.html content — bypass redirect
        env.ASSETS.fetch(new Request(
          `${url.origin}/article.html`,
          { headers: request.headers }
        )),
      ]);

      if (!pageRes.ok) return pageRes;

      const title = meta?.title || "Samuga Media";
      const desc  = meta?.desc  || "Live Maldives news powered by Samuga AI.";
      const img   = meta?.image || DEFAULT_IMG;
      const canon = `https://samugamedia.com/article.html?id=${encodeURIComponent(id)}`;

      const tags = `
  <title>${esc(title)} | Samuga Media</title>
  <meta name="description" content="${esc(desc)}">
  <link rel="canonical" href="${canon}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Samuga Media">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(desc)}">
  <meta property="og:image" content="${esc(img)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="${canon}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(desc)}">
  <meta name="twitter:image" content="${esc(img)}">`;

      // Return 200 directly — no redirect
      const transformed = new HTMLRewriter()
        .on("head", { element(el) { el.prepend(tags, { html: true }); } })
        .on("title", { element(el) { el.setInnerContent(`${title} | Samuga Media`); } })
        .transform(pageRes);

      return new Response(transformed.body, {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=300",
        }
      });
    }

    // Real users: pass through normally
    return env.ASSETS.fetch(request);
  },
};
