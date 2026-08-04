const API = "https://samuga-news-bot-production.up.railway.app";
const SITE = "https://samugamedia.com";
const DEFAULT_IMG = `${SITE}/assets/SamugaNewsBot_Profile.png`;
const DV_TEXT = /[ހ-޿]/;

const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
}[char]));
const abs = value => !value ? "" : /^https?:\/\//i.test(value)
  ? value
  : `${SITE}/${String(value).replace(/^\//, "")}`;
const fmt = value => {
  if (!value) return "Recent";
  try {
    return new Date(value).toLocaleString("en-MV", {
      dateStyle: "medium", timeStyle: "short", timeZone: "Indian/Maldives",
    });
  } catch {
    return String(value);
  }
};

async function getArticle(id) {
  const response = await fetch(`${API}/api/article?id=${encodeURIComponent(id)}`, {
    headers: {Accept: "application/json"},
  });
  if (!response.ok) throw new Error("Article unavailable");
  const data = await response.json();
  if (data.error) throw new Error(data.error);
  return data;
}

async function getSettings() {
  try {
    const response = await fetch(`${API}/api/site-settings`, {headers: {Accept: "application/json"}});
    const data = await response.json();
    return data?.settings || {};
  } catch {
    return {};
  }
}

function media(item) {
  if (!item?.url) return "";
  const visual = item.type === "video"
    ? `<video src="${esc(abs(item.url))}" poster="${esc(abs(item.poster || ""))}" controls playsinline preload="metadata"></video>`
    : `<img src="${esc(abs(item.url))}" alt="${esc(item.caption || "")}" loading="lazy">`;
  return `<figure class="article-media">${visual}${item.caption ? `<figcaption class="media-caption">${esc(item.caption)}</figcaption>` : ""}</figure>`;
}

function bodyMarkup(article) {
  const paragraphs = (Array.isArray(article.paragraphs) && article.paragraphs.length
    ? article.paragraphs
    : String(article.body || "").split(/\n\s*\n+/))
    .map(value => String(value || "").trim())
    .filter(Boolean);
  const mediaItems = Array.isArray(article.media_items) ? article.media_items : [];
  let output = "";
  paragraphs.forEach((paragraph, index) => {
    output += `<p>${esc(paragraph).replace(/\r?\n/g, "<br>")}</p>`;
    mediaItems.filter(item => Number(item.position || 0) === index + 1).forEach(item => { output += media(item); });
  });
  mediaItems.filter(item => !item.position || Number(item.position) > paragraphs.length).forEach(item => { output += media(item); });
  return output || `<p>${esc(article.excerpt || article.title || "")}</p>`;
}

function relatedMarkup(items = [], isDv = false) {
  const sameLanguage = items.filter(item => isDv ? DV_TEXT.test(item.title || "") : !DV_TEXT.test(item.title || ""));
  if (!sameLanguage.length) return "";
  return `<section class="related"><h2>${isDv ? "ސަމުގާއިން އިތުރަށް" : "More from Samuga"}</h2><div class="related-grid">${sameLanguage.slice(0, 4).map(item => `
    <a class="related-card" href="/article?id=${encodeURIComponent(item.id)}" dir="${isDv ? "rtl" : "ltr"}">
      <small>${esc(item.category || "Latest")}</small><h3>${esc(item.title)}</h3>
    </a>`).join("")}</div></section>`;
}

function page(article, id, settings = {}) {
  const isDv = String(article.lang || "").toLowerCase() === "dv" || DV_TEXT.test(`${article.title || ""} ${article.body || ""}`);
  const url = `${SITE}/article?id=${encodeURIComponent(id)}`;
  const community = abs(settings.community_url) || "https://t.me/samugacommunity";
  const initialTheme = ["light", "dark"].includes(settings.default_theme) ? settings.default_theme : "dark";
  const title = article.seo?.title || article.title || "Samuga Media";
  const description = article.seo?.description || article.excerpt || article.summary || "Maldives, as it happens.";
  const image = abs(article.cover_image) || DEFAULT_IMG;
  const cover = article.cover_video
    ? `<div class="article-cover article-cover-top"><video src="${esc(abs(article.cover_video))}" poster="${esc(abs(article.video_poster || article.cover_image || ""))}" controls playsinline preload="metadata"></video>${article.cover_caption ? `<p class="media-caption">${esc(article.cover_caption)}</p>` : ""}</div>`
    : article.cover_image
      ? `<div class="article-cover article-cover-top"><img src="${esc(abs(article.cover_image))}" alt="${esc(article.cover_caption || article.title || "")}" fetchpriority="high">${article.cover_caption ? `<p class="media-caption">${esc(article.cover_caption)}</p>` : ""}</div>`
      : "";
  const author = article.author || {};
  const avatar = author.photo
    ? `<img src="${esc(abs(author.photo))}" alt="${esc(author.name || "Samuga Media")}">`
    : `<span class="byline-avatar">S</span>`;
  const updated = article.updated_at && article.updated_at !== article.published_at
    ? `<span class="updated-note">${isDv ? "އަޕްޑޭޓްކުރީ" : "Updated"} ${esc(fmt(article.updated_at))}</span>`
    : "";
  const shareLabel = isDv ? "ހިއްސާކުރަން" : "Share";
  const copyLabel = isDv ? "ލިންކް ކޮޕީ" : "Copy link";
  const jsonLd = JSON.stringify({
    "@context": "https://schema.org", "@type": "NewsArticle", headline: title,
    description, image: [image], datePublished: article.published_at,
    dateModified: article.updated_at || article.published_at,
    author: {"@type": "Person", name: author.name || "Samuga Media"},
    publisher: {"@type": "Organization", name: "Samuga Media", logo: {"@type": "ImageObject", url: DEFAULT_IMG}},
    mainEntityOfPage: url,
  }).replace(/</g, "\\u003c");

  return `<!doctype html><html lang="${isDv ? "dv" : "en"}" dir="ltr" data-theme="${initialTheme}" data-samuga-build="16.2.0"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#29b8fe">
    <title>${esc(title)} | Samuga Media</title><meta name="description" content="${esc(description)}">
    <link rel="canonical" href="${url}"><link rel="icon" href="/assets/SamugaNewsBot_Profile.png">
    <meta property="og:type" content="article"><meta property="og:site_name" content="Samuga Media">
    <meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(description)}">
    <meta property="og:image" content="${esc(image)}"><meta property="og:url" content="${url}">
    <meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${esc(title)}">
    <meta name="twitter:description" content="${esc(description)}"><meta name="twitter:image" content="${esc(image)}">
    <script type="application/ld+json">${jsonLd}</script>
    <script>(()=>{let s=null;try{s=localStorage.getItem('samuga-theme')}catch{}let l=false;try{l=matchMedia('(prefers-color-scheme:light)').matches}catch{}document.documentElement.dataset.theme=s||(l?'light':'dark')})()</script>
    <link rel="stylesheet" href="/site-build15-2.css?v=15.9.8.5"><link rel="stylesheet" href="/site-v3-16-0-1.css?v=16.0.1"><link rel="stylesheet" href="/website-settings-runtime-16-2-0.css?v=16.2.0">
  </head><body class="article-page-body ${isDv ? "lang-dv" : "lang-en"}">
    <div class="reading-progress"><span id="readingBar"></span></div>
    <header class="article-header settings-sticky-header" dir="ltr"><div class="article-header-row">
      <div class="header-brand-cluster"><button class="menu-btn v3-menu-btn" id="menuBtn" data-drawer-toggle type="button" aria-label="Open Samuga menu" aria-expanded="false" aria-controls="v3Drawer"><span></span><span></span><span></span></button><a class="brand" href="/"><img src="/assets/Samuga_Media_Logo_White.png" alt="Samuga Media" width="1200" height="453"></a></div>
      <div class="article-actions ltr-lock"><div class="segmented" aria-label="Language"><button class="lang-btn ${isDv ? "" : "active"}" data-lang="en" aria-pressed="${isDv ? "false" : "true"}" type="button">EN</button><button class="lang-btn ${isDv ? "active" : ""}" data-lang="dv" aria-pressed="${isDv ? "true" : "false"}" type="button">ދވ</button></div><button class="icon-btn theme-toggle" id="themeToggle" aria-label="Switch theme"><span class="theme-sun">☀</span><span class="theme-moon">☾</span></button></div>
    </div></header>
    <main class="article-main" data-article-language="${isDv ? "dv" : "en"}"><div class="article-container">
      <article class="article-story ${isDv ? "article-dv" : "article-en"}" lang="${isDv ? "dv" : "en"}" dir="ltr">
        ${cover}
        <div class="article-copy" lang="${isDv ? "dv" : "en"}" dir="${isDv ? "rtl" : "ltr"}">
          <div class="article-kicker"><strong>${esc(article.category || "Local")}</strong><span>${article.breaking ? (isDv ? "ލައިވް · " : "Live · ") : ""}Samuga Media</span></div>
          <h1 class="article-headline">${esc(article.title)}</h1>
          ${article.excerpt ? `<p class="article-subhead">${esc(article.excerpt)}</p>` : ""}
          <div class="byline" dir="ltr">${avatar}<div class="byline-details"><strong>${esc(author.name || "Samuga Media")}</strong><span>${esc(author.role || "Newsroom")}</span></div><div class="byline-time"><time>${esc(fmt(article.published_at || article.time))}</time>${article.reading_time ? `<br>${esc(article.reading_time)} ${isDv ? "މިނެޓް" : "min read"}` : ""}${updated}</div></div>
          <div class="article-body">${bodyMarkup(article)}</div>
          <div class="share-row" dir="ltr"><strong>${shareLabel}</strong><a class="share-btn" href="https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}" target="_blank" rel="noopener">Facebook</a><a class="share-btn" href="https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(url)}" target="_blank" rel="noopener">X</a><a class="share-btn" href="https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(title)}" target="_blank" rel="noopener">Telegram</a><button class="share-btn" id="copyBtn">${copyLabel}</button></div>
          ${relatedMarkup(article.related || [], isDv)}
        </div>
      </article>
    </div></main>
    <footer class="site-footer v3-footer" style="margin-top:70px"><div class="wrap v3-footer-main"><div class="v3-footer-brand"><img src="/assets/Samuga_Media_Logo_White.png" alt="Samuga Media" width="1200" height="453"><h2>Maldives, as it happens.</h2><p>From every island to every screen.</p><div class="v3-footer-socials" data-v3-footer-socials aria-label="Follow Samuga Media"></div></div><nav class="v3-footer-links" aria-label="Samuga Media links"><a href="/">Latest news</a><a href="/about">About</a><a href="/advertising">Advertise</a><a href="/contact">Contact</a><a href="/editorial-policy">Editorial policy</a><a href="/corrections-policy">Corrections</a><a href="/privacy-policy">Privacy</a><a href="/terms">Terms</a></nav></div><div class="wrap footer-bottom"><span>© ${new Date().getFullYear()} Samuga Media.</span><span>A division of <a href="https://www.samugacreative.com" target="_blank" rel="noopener">Samuga Creative Pvt Ltd</a></span></div></footer>
    <script>
      document.getElementById('themeToggle')?.addEventListener('click',()=>{const n=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=n;try{localStorage.setItem('samuga-theme',n)}catch{}});
      addEventListener('scroll',()=>{const t=document.documentElement.scrollHeight-innerHeight;document.getElementById('readingBar').style.width=(t>0?Math.min(100,scrollY/t*100):0)+'%'},{passive:true});
      document.getElementById('copyBtn')?.addEventListener('click',async e=>{await navigator.clipboard.writeText('${url}');e.currentTarget.textContent='${isDv ? "ކޮޕީކުރެވިއްޖެ" : "Copied"}'})
    </script>
    <script src="/analytics-build12.js"></script><script src="/samuga-v3-shell-16-2-0.js?v=16.2.0"></script><script src="/website-settings-runtime-16-2-0.js?v=16.2.0"></script>
  </body></html>`;
}

function errorPage() {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Article unavailable | Samuga Media</title><link rel="stylesheet" href="/site-build15-2.css?v=15.9.8.5"><link rel="stylesheet" href="/site-v3-16-0-1.css?v=16.0.1"><link rel="stylesheet" href="/website-settings-runtime-16-2-0.css?v=16.2.0"></head><body><main class="policy-main"><h1>Article unavailable</h1><p>We could not load this story.</p><p><a href="/">Return to latest stories →</a></p></main></body></html>`;
}

function pendingPage() {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="45"><title>Finalizing this story | Samuga Media</title><link rel="stylesheet" href="/site-build15-2.css?v=15.9.8.5"><link rel="stylesheet" href="/site-v3-16-0-1.css?v=16.0.1"><link rel="stylesheet" href="/website-settings-runtime-16-2-0.css?v=16.2.0"></head><body><main class="policy-main"><h1>Almost ready</h1><p>We're still finalizing this story. This page will refresh automatically — or check back in a minute.</p><p><a href="/">Return to latest stories →</a></p></main></body></html>`;
}

export async function onRequest({request}) {
  const id = new URL(request.url).searchParams.get("id") || "";
  if (!id) return new Response(errorPage(), {status: 404, headers: {"content-type": "text/html;charset=utf-8"}});
  try {
    const [article, settings] = await Promise.all([getArticle(id), getSettings()]);
    return new Response(page(article, id, settings), {headers: {
      "content-type": "text/html;charset=utf-8",
      "cache-control": "public,max-age=30,s-maxage=60",
      "x-samuga-function": "article-build16.2.0",
    }});
  } catch (err) {
    const pending = err && err.message === "article body pending";
    return new Response(pending ? pendingPage() : errorPage(), {status: pending ? 503 : 404, headers: {"content-type": "text/html;charset=utf-8", "cache-control": "no-store", ...(pending ? {"retry-after": "45"} : {})}});
  }
}
