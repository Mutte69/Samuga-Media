"use strict";

const API = "https://samuga-news-bot-production.up.railway.app";
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
}[ch]));
const attr = value => esc(value).replace(/`/g, "&#096;");
const id = new URLSearchParams(location.search).get("id") || "";

const DV_TEXT = /[ހ-޿]/;
const isDhivehiArticle = article => {
  const declared = String(article?.lang || "").trim().toLowerCase();
  const text = `${article?.title || ""} ${article?.excerpt || ""} ${article?.body || ""}`;
  return declared === "dv" || declared === "dhivehi" || DV_TEXT.test(text);
};

window.addEventListener("DOMContentLoaded", () => {
  setupTheme();
  loadSettings();
  loadArticle();
  window.addEventListener("scroll", updateProgress, {passive: true});
});

function setupTheme() {
  document.querySelector("#themeToggle")?.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("samuga-theme", next);
  });
}

async function loadSettings() {
  try {
    const response = await fetch(`${API}/api/site-settings`, {cache: "no-store"});
    const data = await response.json();
    const settings = data?.settings || {};
    if (settings.community_url) {
      document.querySelector("#articleCommunity")?.setAttribute("href", settings.community_url);
    }
    if (!localStorage.getItem("samuga-theme") && ["light", "dark"].includes(settings.default_theme)) {
      document.documentElement.dataset.theme = settings.default_theme;
    }
  } catch {}
}

function updateProgress() {
  const total = document.documentElement.scrollHeight - innerHeight;
  const bar = document.querySelector("#readingBar");
  if (bar) bar.style.width = `${total > 0 ? Math.min(100, scrollY / total * 100) : 0}%`;
}

async function loadArticle() {
  try {
    const response = await fetch(`${API}/api/article?id=${encodeURIComponent(id)}`, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || "Article unavailable");
    render(data);
  } catch (error) {
    document.querySelector("#articleRoot").innerHTML = `
      <div class="policy-main">
        <h1>Article unavailable</h1>
        <p>${esc(error.message)}</p>
        <p><a href="/">Return to latest stories →</a></p>
      </div>`;
  }
}

function render(article) {
  const dv = isDhivehiArticle(article);

  // Keep the site chrome stable in LTR. Only the article itself becomes RTL.
  // This prevents uppercase "DV" values or Thaana-detected stories from
  // reversing the header, share controls, and mobile browser layout.
  document.documentElement.lang = dv ? "dv" : "en";
  document.documentElement.dir = "ltr";
  document.body.classList.toggle("lang-dv", dv);
  document.body.classList.toggle("lang-en", !dv);
  document.title = `${article.title} | Samuga Media`;

  const shareUrl = `${location.origin}/article?id=${encodeURIComponent(article.id)}`;
  const root = document.querySelector("#articleRoot");
  root.innerHTML = articleMarkup(article, shareUrl, dv);
  root.dataset.articleLanguage = dv ? "dv" : "en";

  document.querySelector("#copyBtn")?.addEventListener("click", async event => {
    await navigator.clipboard.writeText(shareUrl);
    event.currentTarget.textContent = dv ? "ކޮޕީކުރެވިއްޖެ" : "Copied";
  });
}

function articleMarkup(article, url, dv) {
  const cover = article.cover_video
    ? `<div class="article-cover article-cover-top"><video src="${attr(article.cover_video)}" poster="${attr(article.video_poster || article.cover_image || "")}" controls playsinline preload="metadata"></video>${article.cover_caption ? `<p class="media-caption">${esc(article.cover_caption)}</p>` : ""}</div>`
    : article.cover_image
      ? `<div class="article-cover article-cover-top"><img src="${attr(article.cover_image)}" alt="${esc(article.cover_caption || article.title || "")}" fetchpriority="high" onerror="this.onerror=null;this.src='${ARTICLE_FALLBACK_COVER}'">${article.cover_caption ? `<p class="media-caption">${esc(article.cover_caption)}</p>` : ""}</div>`
      : `<div class="article-cover article-cover-top article-cover-fallback"><img src="${ARTICLE_FALLBACK_COVER}" alt="Samuga Media" fetchpriority="high"></div>`;

  const author = article.author || {};
  const avatar = author.photo
    ? `<img src="${attr(author.photo)}" alt="${esc(author.name || "Samuga Media")}">`
    : `<span class="byline-avatar">S</span>`;
  const updated = article.updated_at && article.updated_at !== article.published_at
    ? `<span class="updated-note">${dv ? "އަޕްޑޭޓްކުރީ" : "Updated"} ${esc(formatDate(article.updated_at, dv))}</span>`
    : "";

  const shareLabel = dv ? "ހިއްސާކުރަން" : "Share";
  const copyLabel = dv ? "ލިންކް ކޮޕީ" : "Copy link";

  // The cover is intentionally outside the RTL copy column. This gives both
  // languages the exact same stable page geometry and keeps the cover at the
  // top, before the headline and byline.
  return `
    <div class="article-container">
      <article class="article-story ${dv ? "article-dv" : "article-en"}" lang="${dv ? "dv" : "en"}" dir="ltr">
        ${cover}
        <div class="article-copy" lang="${dv ? "dv" : "en"}" dir="${dv ? "rtl" : "ltr"}">
          <div class="article-kicker"><strong>${esc(article.category || "Local")}</strong><span>${article.breaking ? (dv ? "ލައިވް · " : "Live · ") : ""}Samuga Media</span></div>
          <h1 class="article-headline">${esc(article.title)}</h1>
          ${article.excerpt ? `<p class="article-subhead">${esc(article.excerpt)}</p>` : ""}
          <div class="byline" dir="ltr">
            ${avatar}
            <div class="byline-details"><strong>${esc(author.name || "Samuga Media")}</strong><span>${esc(author.role || "Newsroom")}</span></div>
            <div class="byline-time"><time>${esc(formatDate(article.published_at || article.time, dv))}</time>${article.reading_time ? `<br>${esc(article.reading_time)} ${dv ? "މިނެޓް" : "min read"}` : ""}${updated}</div>
          </div>
          <div class="article-body">${bodyWithMedia(article)}</div>
          <div class="share-row" dir="ltr">
            <strong>${shareLabel}</strong>
            <a class="share-btn" target="_blank" rel="noopener" href="https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}">Facebook</a>
            <a class="share-btn" target="_blank" rel="noopener" href="https://twitter.com/intent/tweet?text=${encodeURIComponent(article.title)}&url=${encodeURIComponent(url)}">X</a>
            <a class="share-btn" target="_blank" rel="noopener" href="https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(article.title)}">Telegram</a>
            <button class="share-btn" id="copyBtn">${copyLabel}</button>
          </div>
          ${relatedMarkup(article.related || [], dv)}
        </div>
      </article>
    </div>
    ${footerMarkup()}`;
}

function bodyWithMedia(article) {
  const sourceParagraphs = Array.isArray(article.paragraphs) && article.paragraphs.length
    ? article.paragraphs
    : String(article.body || "").split(/\r?\n\s*\r?\n+/);
  const paragraphs = sourceParagraphs.map(value => String(value || "").trim()).filter(Boolean);
  const media = Array.isArray(article.media_items) ? article.media_items : [];
  let output = "";

  paragraphs.forEach((paragraph, index) => {
    // Preserve intentional single line breaks without injecting raw HTML.
    const safeParagraph = esc(paragraph).replace(/\r?\n/g, "<br>");
    output += `<p>${safeParagraph}</p>`;
    media
      .filter(item => Number(item.position || 0) === index + 1)
      .forEach(item => { output += mediaMarkup(item); });
  });

  media
    .filter(item => !item.position || Number(item.position) > paragraphs.length)
    .forEach(item => { output += mediaMarkup(item); });

  return output || `<p>${esc(article.excerpt || article.title || "")}</p>`;
}

function mediaMarkup(item) {
  if (!item?.url) return "";
  const visual = item.type === "video"
    ? `<video src="${attr(item.url)}" poster="${attr(item.poster || "")}" controls playsinline preload="metadata"></video>`
    : `<img src="${attr(item.url)}" alt="${esc(item.caption || "")}" loading="lazy">`;
  return `<figure class="article-media">${visual}${item.caption ? `<figcaption class="media-caption">${esc(item.caption)}</figcaption>` : ""}</figure>`;
}

function relatedMarkup(items, dv) {
  // Keep recommendations in the same language even when an older backend is
  // briefly cached during deployment.
  const sameLanguage = items.filter(item => dv ? DV_TEXT.test(item.title || "") : !DV_TEXT.test(item.title || ""));
  if (!sameLanguage.length) return "";
  return `<section class="related"><h2>${dv ? "ސަމުގާއިން އިތުރަށް" : "More from Samuga"}</h2><div class="related-grid">${sameLanguage.slice(0, 4).map(item => `
    <a class="related-card" href="/article?id=${encodeURIComponent(item.id)}" dir="${dv ? "rtl" : "ltr"}">
      <small>${esc(item.category || "Latest")}</small><h3>${esc(item.title)}</h3>
    </a>`).join("")}</div></section>`;
}

function footerMarkup() {
  return `<footer class="site-footer" style="margin-top:70px"><div class="wrap footer-bottom"><span>© ${new Date().getFullYear()} Samuga Media. All rights reserved.</span><span>Powered by <a href="https://www.samugacreative.com" target="_blank" rel="noopener">Samuga Creative</a></span></div></footer>`;
}

function formatDate(value, dv = false) {
  if (!value) return dv ? "ފަހުގެ" : "Recent";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  try {
    return date.toLocaleString(dv ? "dv-MV" : "en-MV", {dateStyle: "medium", timeStyle: "short"});
  } catch {
    return date.toLocaleString("en-GB", {dateStyle: "medium", timeStyle: "short"});
  }
}
