/**
 * Samuga Media — Cloudflare Worker
 * 
 * PURPOSE:
 * Facebook, X (Twitter), Telegram, WhatsApp bots don't run JavaScript.
 * GitHub Pages serves article.html with blank meta tags that JS fills in later.
 * Crawlers see the blank tags → no preview.
 *
 * This Worker sits in front of samugamedia.com and intercepts /article.html requests.
 * For social media crawlers it fetches real article data from the Railway API and 
 * injects proper OG meta tags into the HTML before sending it.
 * For real users it passes through unchanged (JS handles everything as before).
 *
 * DEPLOY:
 * 1. Go to Cloudflare dashboard → Workers & Pages → Create Worker
 * 2. Paste this file
 * 3. Add a Route: samugamedia.com/article.html* → this worker
 * 4. Done. No other changes needed.
 *
 * OR if using Cloudflare Pages to host the site:
 * 1. Create a /functions directory in your GitHub repo
 * 2. Save this file as /functions/article.html.js  (or _middleware.js for all routes)
 * 3. Push — Cloudflare Pages deploys automatically
 */

const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const SITE_URL    = "https://samugamedia.com";
const DEFAULT_IMG = `${SITE_URL}/assets/SamugaNewsBot_Profile.png`;
const GITHUB_PAGES_ORIGIN = "https://mutte69.github.io"; // your GitHub Pages URL

// Social media crawler user agents
const CRAWLER_UA = [
  "facebookexternalhit",
  "Twitterbot",
  "LinkedInBot",
  "Slackbot",
  "TelegramBot",
  "WhatsApp",
  "Discordbot",
  "Pinterest",
  "Googlebot",
  "bingbot",
  "Applebot",
];

function isCrawler(userAgent) {
  if (!userAgent) return false;
  const ua = userAgent.toLowerCase();
  return CRAWLER_UA.some(bot => ua.includes(bot.toLowerCase()));
}

function esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .slice(0, 300);
}

async function fetchArticleMeta(articleId) {
  try {
    const resp = await fetch(
      `${RAILWAY_API}/api/article?id=${encodeURIComponent(articleId)}`,
      { cf: { cacheTtl: 300, cacheEverything: true } }
    );
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data.error) return null;
    return {
      title:       data.title || "Samuga Media",
      description: data.seo?.description || data.excerpt || data.summary || "Live Maldives news.",
      image:       data.cover_image || DEFAULT_IMG,
      url:         `${SITE_URL}/article.html?id=${encodeURIComponent(articleId)}`,
      category:    data.category || "LOCAL",
      author:      data.author?.name || "Samuga AI",
      publishedAt: data.published_at || "",
    };
  } catch {
    return null;
  }
}

function buildMetaTags(meta, articleId) {
  const canonicalUrl = `${SITE_URL}/article.html?id=${encodeURIComponent(articleId)}`;
  return `
  <!-- Samuga Media — injected by Cloudflare Worker for social crawlers -->
  <title>${esc(meta.title)} | Samuga Media</title>
  <meta name="description" content="${esc(meta.description)}" />
  <link rel="canonical" href="${canonicalUrl}" />
  <meta property="og:type"         content="article" />
  <meta property="og:site_name"    content="Samuga Media" />
  <meta property="og:title"        content="${esc(meta.title)}" />
  <meta property="og:description"  content="${esc(meta.description)}" />
  <meta property="og:image"        content="${esc(meta.image)}" />
  <meta property="og:image:width"  content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:url"          content="${canonicalUrl}" />
  <meta name="twitter:card"        content="summary_large_image" />
  <meta name="twitter:title"       content="${esc(meta.title)}" />
  <meta name="twitter:description" content="${esc(meta.description)}" />
  <meta name="twitter:image"       content="${esc(meta.image)}" />
  <meta name="twitter:site"        content="@SamugaMedia" />`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const userAgent = request.headers.get("user-agent") || "";

    // Only intercept /article.html requests that have an id param
    if (!url.pathname.includes("article.html")) {
      return fetch(request);
    }

    const articleId = url.searchParams.get("id");
    if (!articleId) return fetch(request);

    // For real users: pass through to GitHub Pages unchanged
    // JS will populate meta tags as before
    if (!isCrawler(userAgent)) {
      return fetch(request);
    }

    // For crawlers: fetch real article data and inject meta tags
    const [pageResp, meta] = await Promise.all([
      fetch(request),
      fetchArticleMeta(articleId),
    ]);

    if (!meta || !pageResp.ok) {
      return pageResp; // fallback: serve page as-is
    }

    // Use HTMLRewriter to inject meta tags into <head>
    const metaHTML = buildMetaTags(meta, articleId);

    return new HTMLRewriter()
      .on("head", {
        element(el) {
          el.prepend(metaHTML, { html: true });
        },
      })
      .on("title", {
        element(el) {
          el.setInnerContent(`${meta.title} | Samuga Media`);
        },
      })
      .on('meta[id="ogTitle"]',       { element(el) { el.setAttribute("content", meta.title); } })
      .on('meta[id="ogDesc"]',        { element(el) { el.setAttribute("content", meta.description); } })
      .on('meta[id="ogImage"]',       { element(el) { el.setAttribute("content", meta.image); } })
      .on('meta[id="twTitle"]',       { element(el) { el.setAttribute("content", meta.title); } })
      .on('meta[id="twDesc"]',        { element(el) { el.setAttribute("content", meta.description); } })
      .on('meta[id="twImage"]',       { element(el) { el.setAttribute("content", meta.image); } })
      .transform(pageResp);
  },
};
