/**
 * Samuga Media — Cloudflare Pages Worker (fixed)
 *
 * Fixes ERR_TOO_MANY_REDIRECTS by using ONE routing system only.
 *
 * What it does:
 * - /article?id=... for humans: internally serves /article.html?id=... with no browser redirect.
 * - /article?id=... for Facebook/WhatsApp/Telegram/X crawlers: returns real OG meta tags.
 * - /article.html?id=... also works for both humans and crawlers.
 * - Everything else passes through to Cloudflare Pages static assets.
 *
 * Important:
 * - Do NOT add a separate Cloudflare Dashboard Worker route for article pages.
 * - Do NOT use _redirects for /article.
 * - Keep this file as the only Worker in the repo.
 */

const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const SITE_URL = "https://samugamedia.com";
const DEFAULT_IMG = `${SITE_URL}/assets/SamugaNewsBot_Profile.png`;

const CRAWLERS = [
  "facebookexternalhit",
  "facebot",
  "meta-externalagent",
  "twitterbot",
  "xbot",
  "linkedinbot",
  "slackbot",
  "telegrambot",
  "whatsapp",
  "discordbot",
  "pinterest",
  "iframely",
  "googlebot",
  "bingbot",
  "applebot",
];

function isCrawler(userAgent = "") {
  const ua = userAgent.toLowerCase();
  return CRAWLERS.some(bot => ua.includes(bot));
}

function esc(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .slice(0, 700);
}

function absoluteUrl(raw) {
  const value = String(raw || "").trim();
  if (!value) return DEFAULT_IMG;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("//")) return `https:${value}`;
  if (value.startsWith("/")) return `${SITE_URL}${value}`;
  return `${SITE_URL}/${value.replace(/^\.\//, "")}`;
}

async function fetchArticleMeta(id) {
  try {
    const response = await fetch(`${RAILWAY_API}/api/article?id=${encodeURIComponent(id)}`, {
      headers: {
        "Accept": "application/json",
        "User-Agent": "SamugaMedia-CloudflarePagesWorker/1.0",
      },
      cf: {
        cacheTtl: 300,
        cacheEverything: true,
      },
    });

    if (!response.ok) return null;
    const data = await response.json();
    if (!data || data.error) return null;

    return {
      title: (data.seo?.title || data.title || "Samuga Media").trim(),
      description: (data.seo?.description || data.excerpt || data.summary || "Live Maldives news powered by Samuga AI.").trim(),
      image: absoluteUrl(data.cover_image),
      category: data.category || "LOCAL",
      author: data.author?.name || "Samuga Media",
      publishedAt: data.published_at || "",
      updatedAt: data.updated_at || data.published_at || "",
    };
  } catch (error) {
    return null;
  }
}

function metaHtml(meta, id) {
  const articleUrl = `${SITE_URL}/article?id=${encodeURIComponent(id)}`;
  const title = meta?.title || "Samuga Media";
  const description = meta?.description || "Live Maldives news powered by Samuga AI.";
  const image = meta?.image || DEFAULT_IMG;
  const publishedAt = meta?.publishedAt || "";
  const updatedAt = meta?.updatedAt || publishedAt;
  const author = meta?.author || "Samuga Media";
  const category = meta?.category || "LOCAL";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(title)} | Samuga Media</title>
  <meta name="description" content="${esc(description)}">
  <link rel="canonical" href="${articleUrl}">

  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Samuga Media">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
  <meta property="og:image" content="${esc(image)}">
  <meta property="og:image:secure_url" content="${esc(image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="${articleUrl}">
  ${publishedAt ? `<meta property="article:published_time" content="${esc(publishedAt)}">` : ""}
  ${updatedAt ? `<meta property="article:modified_time" content="${esc(updatedAt)}">` : ""}
  <meta property="article:section" content="${esc(category)}">
  <meta property="article:author" content="${esc(author)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(description)}">
  <meta name="twitter:image" content="${esc(image)}">

  <script type="application/ld+json">${JSON.stringify({
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: title,
    description,
    image,
    url: articleUrl,
    datePublished: publishedAt,
    dateModified: updatedAt,
    articleSection: category,
    author: { "@type": "Person", name: author },
    publisher: {
      "@type": "Organization",
      name: "Samuga Media",
      logo: { "@type": "ImageObject", url: DEFAULT_IMG }
    }
  }).replace(/</g, "\\u003c")}</script>
</head>
<body>
  <main>
    <h1>${esc(title)}</h1>
    <p>${esc(description)}</p>
    <p><a href="${articleUrl}">Read on Samuga Media</a></p>
  </main>
</body>
</html>`;
}

async function serveArticleAsset(request, env) {
  const originalUrl = new URL(request.url);
  const assetUrl = new URL(request.url);
  assetUrl.pathname = "/article.html";
  assetUrl.search = originalUrl.search;

  const assetRequest = new Request(assetUrl.toString(), request);
  return env.ASSETS.fetch(assetRequest);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const id = url.searchParams.get("id");
    const pathname = url.pathname.replace(/\/+$/, "") || "/";
    const articlePath = pathname === "/article" || pathname === "/article.html";

    if (!articlePath) {
      return env.ASSETS.fetch(request);
    }

    if (!id) {
      return serveArticleAsset(request, env);
    }

    if (isCrawler(request.headers.get("user-agent") || "")) {
      const meta = await fetchArticleMeta(id);
      return new Response(metaHtml(meta, id), {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=300, s-maxage=300",
        },
      });
    }

    return serveArticleAsset(request, env);
  },
};
