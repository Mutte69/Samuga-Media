/**
 * Samuga Media — Cloudflare Pages Function
 * Route: /article?id=ARTICLE_ID
 * Returns real server-side HTML with Open Graph tags for Facebook/WhatsApp/Telegram/X.
 */

const RAILWAY_API = "https://samuga-news-bot-production.up.railway.app";
const SITE_URL = "https://samugamedia.com";
const DEFAULT_IMG = `${SITE_URL}/assets/SamugaNewsBot_Profile.png`;
const FB_APP_ID = "4546722118978306"; // Change if you later use another Meta app.

function esc(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function textLimit(value, limit = 300) {
  const s = String(value || "").replace(/\s+/g, " ").trim();
  return s.length > limit ? s.slice(0, limit - 1) + "…" : s;
}

function absoluteUrl(raw) {
  const value = String(raw || "").trim();
  if (!value) return DEFAULT_IMG;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("//")) return `https:${value}`;
  if (value.startsWith("/")) return `${SITE_URL}${value}`;
  return `${SITE_URL}/${value.replace(/^\.\//, "")}`;
}

function fmtDate(raw) {
  if (!raw) return "";
  try {
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return String(raw);
    return d.toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", hour12: false,
      timeZone: "Indian/Maldives"
    }) + " MVT";
  } catch (_) {
    return String(raw);
  }
}

async function getArticle(id) {
  const response = await fetch(`${RAILWAY_API}/api/article?id=${encodeURIComponent(id)}`, {
    headers: {
      "Accept": "application/json",
      "User-Agent": "SamugaMedia-CloudflarePagesFunction/3.0"
    },
    cf: { cacheTtl: 120, cacheEverything: true }
  });
  if (!response.ok) throw new Error("Article API failed");
  const data = await response.json();
  if (!data || data.error) throw new Error(data?.error || "Article not found");
  return data;
}

function paragraphHtml(data) {
  const paragraphs = Array.isArray(data.paragraphs) && data.paragraphs.length
    ? data.paragraphs
    : String(data.body || data.content || data.article || data.excerpt || data.summary || "")
        .split(/\n\s*\n+/)
        .filter(Boolean);
  if (!paragraphs.length) return `<p>${esc(data.title || "")}</p>`;
  return paragraphs.map(p => `<p>${esc(p)}</p>`).join("\n");
}

function articleHtml(data, id) {
  const articleUrl = `${SITE_URL}/article?id=${encodeURIComponent(id)}`;
  const title = textLimit(data.seo?.title || data.title || "Samuga Media", 160);
  const desc = textLimit(data.seo?.description || data.excerpt || data.summary || data.body || "Live Maldives news powered by Samuga AI.", 280);
  const image = absoluteUrl(data.cover_image || data.image || data.thumbnail);
  const isDv = data.lang === "dv" || /[ހ-޿]/.test(`${data.title || ""} ${data.body || ""}`);
  const category = data.category || "LOCAL";
  const authorName = data.author?.name || "Samuga Media";
  const authorRole = data.author?.role || "Newsroom";
  const authorPhoto = data.author?.photo ? absoluteUrl(data.author.photo) : "";
  const published = data.published_at || data.time || "";
  const updated = data.updated_at || published;
  const coverCaption = data.cover_caption || data.title || "";
  const body = paragraphHtml(data);
  const readTime = data.reading_time ? `${esc(data.reading_time)} min read` : "";

  const jsonLd = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: title,
    description: desc,
    image: [image],
    url: articleUrl,
    mainEntityOfPage: articleUrl,
    datePublished: published,
    dateModified: updated,
    articleSection: category,
    author: { "@type": "Person", name: authorName },
    publisher: {
      "@type": "Organization",
      name: "Samuga Media",
      logo: { "@type": "ImageObject", url: DEFAULT_IMG }
    }
  }).replace(/</g, "\\u003c");

  return `<!DOCTYPE html>
<html lang="${isDv ? "dv" : "en"}" dir="${isDv ? "rtl" : "ltr"}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${esc(title)} | Samuga Media</title>
  <meta name="description" content="${esc(desc)}">
  <link rel="canonical" href="${articleUrl}">
  <link rel="icon" href="/assets/SamugaNewsBot_Profile.png">
  <link rel="stylesheet" href="/styles.css">

  <meta property="fb:app_id" content="${FB_APP_ID}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Samuga Media">
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(desc)}">
  <meta property="og:image" content="${esc(image)}">
  <meta property="og:image:secure_url" content="${esc(image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="${articleUrl}">
  ${published ? `<meta property="article:published_time" content="${esc(published)}">` : ""}
  ${updated ? `<meta property="article:modified_time" content="${esc(updated)}">` : ""}
  <meta property="article:section" content="${esc(category)}">
  <meta property="article:author" content="${esc(authorName)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(desc)}">
  <meta name="twitter:image" content="${esc(image)}">
  <script type="application/ld+json">${jsonLd}</script>
</head>
<body>
  <div class="reading-progress" aria-hidden="true"><div class="reading-progress-bar" id="readingBar"></div></div>
  <header class="article-header" role="banner">
    <div class="wrap article-header-inner">
      <a class="article-header-brand" href="/" aria-label="Samuga Media"><img src="/assets/Samuga_Media_Logo_Transparent.png" alt="Samuga Media" style="height:28px;width:auto;max-width:140px;object-fit:contain;border-radius:0;filter:drop-shadow(0 0 8px rgba(40,184,255,.2))" onerror="this.style.display='none'"></a>
      <nav class="article-header-nav"><a class="header-btn" href="/">← Latest</a><a class="header-btn primary" href="https://t.me/samugacommunity" target="_blank" rel="noopener">Join Community</a></nav>
    </div>
  </header>
  <main class="article-main">
    ${image ? `<div class="article-cover"><img src="${esc(image)}" alt="${esc(coverCaption)}" loading="eager"><div class="article-cover-fade"></div>${data.cover_caption ? `<div class="article-cover-cap">${esc(data.cover_caption)}</div>` : ""}</div>` : `<div class="article-no-cover"></div>`}
    <div class="article-container">
      <article aria-label="Article" dir="${isDv ? "rtl" : "ltr"}">
        <header class="article-hero">
          <div class="article-eyebrow"><span class="article-cat-tag">${esc(category)}</span><span class="article-source-line">${esc(data.source || "Samuga Media")}</span>${data.breaking || category === "BREAKING" ? `<span class="live-badge">Live</span>` : ""}</div>
          <h1 class="article-headline">${esc(data.title || title)}</h1>
          ${data.excerpt || data.summary ? `<p class="article-excerpt">${esc(data.excerpt || data.summary)}</p>` : ""}
          <div class="author-row" dir="ltr">
            ${authorPhoto ? `<img class="author-avatar" src="${esc(authorPhoto)}" alt="${esc(authorName)}" loading="lazy">` : `<div class="author-avatar-ai" aria-label="${esc(authorName)}">🤖</div>`}
            <div class="author-text"><div class="author-name">${esc(authorName)}</div><div class="author-role">${esc(authorRole)}</div></div>
            <div class="author-sep"></div>
            <div class="article-dateline"><div class="article-dateline-label">Published</div><div class="article-dateline-val"><time datetime="${esc(published)}">${esc(fmtDate(published))}</time></div></div>
            ${readTime ? `<div class="article-readtime">${readTime}</div>` : ""}
          </div>
        </header>
        <div class="article-body">${body}</div>
        <div class="article-cta"><div class="article-cta-text"><strong>Follow this story on Samuga Community</strong><p>Live updates, breaking news, discussions.</p></div><a class="header-btn primary" href="https://t.me/samugacommunity" target="_blank" rel="noopener">Join Telegram →</a></div>
        <div class="share-bar"><div class="share-label">Share this story</div><div class="share-buttons" role="group"><a class="share-btn" href="https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(articleUrl)}" target="_blank" rel="noopener">Facebook</a><a class="share-btn" href="https://t.me/share/url?url=${encodeURIComponent(articleUrl)}&text=${encodeURIComponent(title)}" target="_blank" rel="noopener">Telegram</a><a class="share-btn" href="https://wa.me/?text=${encodeURIComponent(title + " " + articleUrl)}" target="_blank" rel="noopener">WhatsApp</a><a class="share-btn" href="https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(articleUrl)}" target="_blank" rel="noopener">X</a><button class="share-btn" id="copyBtn" type="button">Copy link</button></div></div>
      </article>
    </div>
  </main>
  <footer class="site-footer" role="contentinfo"><div class="wrap footer-inner"><div class="footer-brand"><img src="/assets/SamugaNewsBot_Profile.png" alt="Samuga Media" loading="lazy"><div><div class="footer-brand-name">Samuga Media</div><div class="footer-tagline">Live news, powered by Samuga AI.</div></div></div><nav class="footer-links"><a href="/">Home</a><a href="https://t.me/samugacommunity" target="_blank" rel="noopener">Community</a><a href="https://t.me/Samuga_Media" target="_blank" rel="noopener">Send a Tip</a></nav><p class="footer-copy">© 2026 Samuga Media</p></div></footer>
  <script>window.addEventListener("scroll",()=>{const total=Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)-innerHeight;const bar=document.getElementById("readingBar");if(bar)bar.style.width=(total>0?Math.min(100,scrollY/total*100):0)+"%";},{passive:true});document.getElementById("copyBtn")?.addEventListener("click",async()=>{try{await navigator.clipboard.writeText("${articleUrl}");const b=document.getElementById("copyBtn");b.textContent="✓ Copied!";setTimeout(()=>b.textContent="Copy link",1800)}catch(e){}});</script>
</body>
</html>`;
}

function errorHtml() {
  return `<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Article unavailable | Samuga Media</title><meta property="og:title" content="Samuga Media"><meta property="og:description" content="Article unavailable"><meta property="og:image" content="${DEFAULT_IMG}"><link rel="stylesheet" href="/styles.css"></head><body><main class="article-main"><div class="article-container"><div class="empty-state"><strong>Article unavailable</strong><p>We could not load this story. <a href="/" style="color:var(--blue)">Return to latest stories →</a></p></div></div></main></body></html>`;
}

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const id = url.searchParams.get("id") || "";
  if (!id) {
    return new Response(errorHtml(), { status: 404, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
  }
  try {
    const data = await getArticle(id);
    return new Response(articleHtml(data, id), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=120, s-maxage=120",
        "X-Samuga-Function": "article-server-rendered"
      }
    });
  } catch (err) {
    return new Response(errorHtml(), { status: 404, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
  }
}
