/* ════════════════════════════════════════════════════════════════
   Samuga Media Website V2 — script.js
   Consumes Sprint A API fields: cover_image, author{}, reading_time,
   featured, breaking, seo{}, published_at, updated_at
════════════════════════════════════════════════════════════════ */

"use strict";

const BOT_API_BASE  = "https://samuga-news-bot-production.up.railway.app";
const FALLBACK_IMG  = "assets/SamugaNewsBot_Profile.png";

/* ── Sponsor definitions ── */
const SPONSORS = [
  {
    name:    "Samuga Media",
    caption: "Promote your business with Samuga Media",
    link:    "https://t.me/samugacommunity",
    images:  ["assets/sponsor_samuga_media.png"]
  },
  {
    name:    "Etronic Maldives",
    caption: "Etronic Maldives — electrical solutions",
    link:    "#",
    images:  ["assets/sponsor_etronic.png"]
  },
  {
    name:    "Berry Travels",
    caption: "Berry Travels — speedboat transfers & trips",
    link:    "#",
    images:  ["assets/sponsor_berry_travels.png"]
  }
];

/* ── Category colours & tag classes ── */
const CAT_COLOR = {
  BREAKING:"var(--cat-breaking)", LOCAL:"var(--cat-local)",
  POLITICAL:"var(--cat-political)", BUSINESS:"var(--cat-business)",
  SPORTS:"var(--cat-sports)", WORLD:"var(--cat-world)", LIFESTYLE:"var(--cat-lifestyle)"
};
const CAT_TAG_CLASS = {
  BREAKING:"breaking", POLITICAL:"politics", BUSINESS:"business",
  SPORTS:"sports", WORLD:"world", LIFESTYLE:"lifestyle"
};
const CAT_EN = { BREAKING:"Breaking", LOCAL:"Local", POLITICAL:"Politics", BUSINESS:"Business", SPORTS:"Sports", WORLD:"World", LIFESTYLE:"Lifestyle" };
const CAT_DV = { BREAKING:"ބްރޭކިންގ", LOCAL:"ލޯކަލް", POLITICAL:"ސިޔާސީ", BUSINESS:"އިޤްތިޞާދީ", SPORTS:"ކުޅިވަރު", WORLD:"ދުނިޔެ", LIFESTYLE:"ލައިފްސްޓައިލް" };

/* ── Static UI strings ── */
const UI = {
  en: {
    latest:"Latest Stories", popular:"Popular", tipTitle:"Send a Tip",
    tipText:"Have a Maldives story for Samuga AI to watch?",
    community:"Join Samuga Community →", footer:"Live news, powered by Samuga AI.",
    search:"Search stories…", searchLabel:"Search", empty:"No stories found",
    emptyHint:"Try another category or search term.",
    chatWelcome:"Hi! Ask me about Maldives news, breaking stories, or anything on Samuga. 🇲🇻",
    chatSub:"Live Maldives news assistant", readMore:"Read more →"
  },
  dv: {
    latest:"އެންމެ ފަހުގެ ޚަބަރުތައް", popular:"ޕޮޕިއުލަރ", tipTitle:"ޚަބަރު ފޮނުވާ",
    tipText:"ސަމުގާ އޭއައި ބަލަންޖެހޭ ޚަބަރެއް އޮތްތަ؟",
    community:"ސަމުގާ ކޮމިއުނިޓީއަށް ޖޮއިން ވޭ →", footer:"ސަމުގާ އޭއައިއިން ހިންގާ ލައިވް ޚަބަރު.",
    search:"ޚަބަރު ހޯދާ…", searchLabel:"ހޯދާ", empty:"ޚަބަރެއް ނުފެނުނު",
    emptyHint:"އެހެން ކެޓަގަރީއެއް ތަޖުރިބާ ކޮށްލާ.",
    chatWelcome:"ހެލޯ! ދިވެހި ޚަބަރާ ބެހޭ ކޮންމެ ސުވާލެއް ވެސް ކޮށްލާ. 🇲🇻",
    chatSub:"ސަމުގާ ލައިވް ޚަބަރު", readMore:"ތަފްސީލް ކިޔާ →"
  }
};

/* ── State ── */
let stories       = [];
let activeLang    = "en";
let activeCat     = "all";
let dynBanner     = null;
let sponsorIdx    = 0;
let sponsorTimer  = null;

/* ── DOM refs ── */
const qs  = s => document.querySelector(s);
const qsa = s => document.querySelectorAll(s);

/* ════════════════════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", init);

async function init() {
  startClock();
  updateTodayLine();
  setupMenu();
  setupCategoryNav();
  setupLangToggle();
  setupSearch();
  setupChat();
  await loadBanner();
  initSponsors();
  await loadStories();
}

/* ════════════════════════════════════════════════════════════════
   CLOCK
════════════════════════════════════════════════════════════════ */

function startClock() {
  const timeEl  = qs("#clockTime");
  const dateEl  = qs("#clockDate");
  const hijriEl = qs("#clockHijri");
  if (!timeEl) return;

  function tick() {
    const now = new Date();
    // MVT = UTC+5
    const mvt = new Date(now.getTime() + 5 * 3600000);
    const hh = String(mvt.getUTCHours()).padStart(2,"0");
    const mm = String(mvt.getUTCMinutes()).padStart(2,"0");
    const ss = String(mvt.getUTCSeconds()).padStart(2,"0");
    timeEl.textContent = `${hh}:${mm}:${ss}`;
    if (dateEl) dateEl.textContent = mvt.toLocaleDateString("en-GB", { weekday:"short", day:"2-digit", month:"short", year:"numeric", timeZone:"UTC" });
    if (hijriEl) {
      try {
        const hDate = new Intl.DateTimeFormat("en-TN-u-ca-islamic", { day:"numeric", month:"long", year:"numeric" }).format(mvt);
        hijriEl.textContent = hDate;
      } catch (_) { hijriEl.textContent = ""; }
    }
  }
  tick();
  setInterval(tick, 1000);
}

function updateTodayLine() {
  const el = qs("#todayLine");
  if (!el) return;
  const mvt = new Date(Date.now() + 5 * 3600000);
  el.textContent = mvt.toLocaleDateString("en-GB", { weekday:"long", day:"2-digit", month:"long", year:"numeric", timeZone:"UTC" });
}

/* ════════════════════════════════════════════════════════════════
   NAVIGATION
════════════════════════════════════════════════════════════════ */

function setupMenu() {
  const btn = qs("#menuBtn");
  const nav = qs("#primaryNav");
  if (!btn || !nav) return;
  btn.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    btn.setAttribute("aria-expanded", String(open));
  });
}

function setupCategoryNav() {
  qsa(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      qsa(".nav-btn").forEach(b => { b.classList.remove("active"); b.removeAttribute("aria-current"); });
      btn.classList.add("active");
      btn.setAttribute("aria-current", "page");
      activeCat = btn.dataset.cat || "all";
      renderStories();
    });
  });
}

function setupLangToggle() {
  qsa(".lang-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      qsa(".lang-btn").forEach(b => { b.classList.remove("active"); b.setAttribute("aria-pressed","false"); });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed","true");
      activeLang = btn.dataset.lang || "en";
      const isDv = activeLang === "dv";
      document.body.classList.toggle("lang-dv", isDv);
      document.documentElement.lang = isDv ? "dv" : "en";
      document.documentElement.dir  = isDv ? "rtl" : "ltr";
      applyUIStrings();
      renderAll();
    });
  });
}

function setupSearch() {
  const input = qs("#searchInput");
  if (input) input.addEventListener("input", renderStories);
}

/* ════════════════════════════════════════════════════════════════
   BANNER
════════════════════════════════════════════════════════════════ */

async function loadBanner() {
  try {
    const res  = await fetch(`${BOT_API_BASE}/api/banner`, { cache:"no-store" });
    if (!res.ok) throw new Error("banner unavailable");
    const data = await res.json();
    if (data?.active && data?.image_url) {
      dynBanner = { name:"Sponsor", caption: data.text || "Sponsored", link: data.link || "https://samugamedia.com", images:[data.image_url] };
    }
  } catch (_) { dynBanner = null; }
}

/* ════════════════════════════════════════════════════════════════
   SPONSORS
════════════════════════════════════════════════════════════════ */

function sponsorPool() {
  return dynBanner ? [dynBanner, ...SPONSORS] : SPONSORS.slice();
}

function initSponsors() {
  buildSponsorDots();
  showSponsor(0);
  sponsorTimer = setInterval(() => showSponsor((sponsorIdx + 1) % sponsorPool().length), 6000);

  qs("#sponsorPrev")?.addEventListener("click", () => showSponsor(sponsorIdx - 1, true));
  qs("#sponsorNext")?.addEventListener("click", () => showSponsor(sponsorIdx + 1, true));

  // Side sponsor: show sponsor[1] if available
  const pool = sponsorPool();
  if (pool.length > 1) {
    const side = pool[1];
    const sidePanel = qs("#sideSponsorPanel");
    const sideImg   = qs("#sideSponsorImage");
    const sideCap   = qs("#sideSponsorCaption");
    const sideLink  = qs("#sideSponsorLink");
    if (sidePanel && sideImg && side.images?.[0]) {
      sideImg.src  = side.images[0];
      sideImg.alt  = side.caption || side.name;
      if (sideCap)  sideCap.textContent  = side.caption || "";
      if (sideLink) sideLink.href = side.link || "#";
      sidePanel.style.display = "block";
    }
  }
}

function buildSponsorDots() {
  const dotsEl = qs("#sponsorDots");
  if (!dotsEl) return;
  const pool = sponsorPool();
  dotsEl.innerHTML = pool.map((_, i) =>
    `<button class="sp-dot${i===0?" active":""}" data-si="${i}" aria-label="Sponsor ${i+1}" role="tab" aria-selected="${i===0}"></button>`
  ).join("");
  qsa("[data-si]").forEach(d => d.addEventListener("click", () => showSponsor(+d.dataset.si, true)));
}

function showSponsor(idx, manual = false) {
  const pool = sponsorPool();
  sponsorIdx = ((idx % pool.length) + pool.length) % pool.length;
  const item  = pool[sponsorIdx];
  const imgEl = qs("#sponsorImage");
  const capEl = qs("#sponsorCaption");
  const lnkEl = qs("#heroSponsorLink");
  const frame = qs(".sponsor-panel .sponsor-frame");
  if (!imgEl || !item) return;

  frame?.classList.add("changing");
  setTimeout(() => {
    imgEl.src = item.images?.[0] || FALLBACK_IMG;
    imgEl.alt = item.caption || item.name;
    if (capEl) capEl.textContent = item.caption || "";
    if (lnkEl) lnkEl.href       = item.link || "#";
    frame?.classList.remove("changing");
  }, 200);

  qsa(".sp-dot").forEach((d, i) => {
    d.classList.toggle("active", i === sponsorIdx);
    d.setAttribute("aria-selected", String(i === sponsorIdx));
  });

  if (manual) {
    clearInterval(sponsorTimer);
    sponsorTimer = setInterval(() => showSponsor(sponsorIdx + 1), 6000);
  }
}

/* ════════════════════════════════════════════════════════════════
   STORIES — FETCH & CLEAN
════════════════════════════════════════════════════════════════ */

const FALLBACK_STORIES = [
  {
    id:"fb1", title:"Samuga AI newsroom is monitoring Maldives news live",
    summary:"The system tracks local updates, breaking incidents, politics, economy and public-interest stories from multiple sources.",
    category:"LOCAL", source:"Samuga Media", time:"Live", lang:"en",
    url:"#", cover_image:null, author:null, reading_time:null, featured:false, breaking:false
  },
  {
    id:"fb2", title:"AI-assisted publishing helps Samuga deliver faster news",
    summary:"Stories can be published through the website while Telegram and social platforms continue operating.",
    category:"LOCAL", source:"Samuga AI", time:"Today", lang:"en",
    url:"#", cover_image:null, author:null, reading_time:null, featured:false, breaking:false
  }
];

async function loadStories() {
  try {
    const res  = await fetch(`${BOT_API_BASE}/api/stories`, { cache:"no-store" });
    if (!res.ok) throw new Error("stories unavailable");
    const data = await res.json();
    stories = Array.isArray(data) ? data.map(cleanStory).filter(Boolean) : [];
    if (!stories.length) stories = FALLBACK_STORIES;
  } catch (e) {
    console.warn("Stories API failed, using fallback:", e);
    stories = FALLBACK_STORIES;
  }
  applyUIStrings();
  renderAll();
}

function cleanStory(s) {
  if (!s?.title) return null;
  return {
    id:           s.id  || "",
    title:        String(s.title   || "").trim(),
    summary:      String(s.summary || "").trim(),
    source:       String(s.source  || "Samuga Media").trim(),
    time:         s.time || s.published_at || "Recent",
    url:          s.url  || s.link || "#",
    lang:         detectLang(s),
    category:     normalizeCat(s.category || s.cat || "LOCAL", s.title, s.summary, s.source),
    // V2 fields (nullable — backward compatible)
    cover_image:  s.cover_image  || null,
    author:       s.author       || null,
    reading_time: s.reading_time || null,
    featured:     !!s.featured,
    breaking:     !!(s.breaking || (s.category || "").toUpperCase() === "BREAKING"),
  };
}

function detectLang(s) {
  const d = String(s.lang || s.language || "").toLowerCase();
  if (d === "dv" || d === "dhivehi") return "dv";
  if (/[\u0780-\u07BF]/.test(`${s.title||""} ${s.summary||""}`)) return "dv";
  return "en";
}

function normalizeCat(value, title="", summary="", source="") {
  const raw  = String(value || "").toUpperCase().trim();
  const text = `${title} ${summary} ${source}`.toLowerCase();
  if (raw==="BREAKING"||raw==="DISASTER"||/breaking|murder|killed|dead|dies|death|stabbed|shot|accident|crash|fire|capsize|sinking|missing|drug|arrested|emergency/.test(text)) return "BREAKING";
  if (raw==="POLITICAL"||raw==="POLITICS"||/president|parliament|majlis|minister|government|election|court|law|policy|cabinet|opposition|mdp|pnc/.test(text)) return "POLITICAL";
  if (raw==="BUSINESS"||raw==="ECONOMY"||/economy|business|finance|budget|debt|mvr|dollar|bank|tax|price|market|port|project/.test(text)) return "BUSINESS";
  if (raw==="SPORT"||raw==="SPORTS"||raw==="FOOTBALL"||/football|sports|match|fifa|world cup|tournament/.test(text)) return "SPORTS";
  if (raw==="WORLD"||/war|iran|israel|palestine|ukraine|china|global|venezuela|india/.test(text)) return "WORLD";
  if (raw==="LIFESTYLE"||raw==="TOURISM"||raw==="WEATHER"||/tourism|resort|travel|weather|rain|storm|health|education|culture/.test(text)) return "LIFESTYLE";
  return "LOCAL";
}

/* ════════════════════════════════════════════════════════════════
   RENDER
════════════════════════════════════════════════════════════════ */

function renderAll() {
  renderHero();
  renderBreakingStrip();
  renderStories();
  renderTicker();
  renderPopular();
  updateStats();
}

function renderHero() {
  const eyebrow = qs("#heroEyebrow");
  const title   = qs("#heroTitle");
  const summary = qs("#heroSummary");
  if (activeLang === "dv") {
    if (eyebrow) eyebrow.textContent = "ސަމުގާ އޭއައި ފީޑް";
    if (title)   title.textContent   = "ސަމުގާ އޭއައިއާ އެކު ލައިވް ޚަބަރު";
    if (summary) summary.textContent = "ސަމުގާ ލައިވް ޚަބަރު ފީޑްގެ ދިވެހި ތަޖުރިބާ.";
    const chatInput = qs("#chatInput");
    if (chatInput) chatInput.placeholder = "ޚަބަރުތަކާ ބެހޭ ސުވާލެއް ކޮށްލާ…";
  } else {
    if (eyebrow) eyebrow.textContent = "Samuga AI Feed";
    if (title)   title.textContent   = "Live Maldives news, powered by Samuga AI";
    if (summary) summary.textContent = "Ask Samuga AI about the latest Maldives news, breaking stories and public archive.";
    const chatInput = qs("#chatInput");
    if (chatInput) chatInput.placeholder = "Ask about Maldives news…";
  }
}

function renderBreakingStrip() {
  const el = qs("#breakingStrip");
  if (!el) return;
  const breaking = stories.filter(s => s.lang === activeLang && s.breaking).slice(0, 1);
  if (!breaking.length) { el.innerHTML = ""; return; }
  const s = breaking[0];
  el.innerHTML = `
    <div class="breaking-strip" role="alert" aria-label="Breaking news">
      <span class="breaking-label">🔴 Breaking</span>
      <a class="breaking-strip-title" href="${escAttr(s.url)}" target="_blank" rel="noopener">${escHTML(s.title)}</a>
    </div>`;
}

function renderStories() {
  const grid  = qs("#storyGrid");
  if (!grid) return;

  const query = (qs("#searchInput")?.value || "").toLowerCase().trim();
  const t     = UI[activeLang];

  const filtered = stories.filter(s => {
    const langOk = s.lang === activeLang;
    const catOk  = activeCat === "all" || s.category === normalizeCat(activeCat);
    const qOk    = !query || `${s.title} ${s.summary} ${s.source}`.toLowerCase().includes(query);
    return langOk && catOk && qOk;
  });

  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state" role="status"><strong>${escHTML(t.empty)}</strong><p>${escHTML(t.emptyHint)}</p></div>`;
    return;
  }

  const pool   = sponsorPool();
  const chunks = [];
  let   featuredUsed = false;

  filtered.forEach((story, idx) => {
    const isFeatured = story.featured && !featuredUsed;
    if (isFeatured) featuredUsed = true;
    chunks.push(cardHTML(story, isFeatured));

    // Inject inline sponsor every 4 cards
    if ((idx + 1) % 4 === 0 && pool.length) {
      chunks.push(inlineSponsorHTML(pool[Math.floor((idx + 1) / 4 - 1) % pool.length]));
    }
  });

  grid.innerHTML = chunks.join("");
}

/* ── Story card ── */
function cardHTML(s, featured = false) {
  const cat      = s.category || "LOCAL";
  const color    = CAT_COLOR[cat]    || "var(--cat-local)";
  const tagCls   = CAT_TAG_CLASS[cat] || "";
  const catLabel = activeLang === "dv" ? (CAT_DV[cat] || cat) : (CAT_EN[cat] || cat);
  const isRTL    = s.lang === "dv";
  const age      = relativeTime(s.time);
  const readMore = UI[activeLang].readMore;
  const articleHref = s.id && s.id !== "" ? `article.html?id=${encodeURIComponent(s.id)}` : escAttr(s.url);

  // Cover image or emoji placeholder
  const coverHTML = s.cover_image
    ? `<div class="card-cover">
         <img src="${escAttr(s.cover_image)}" alt="" loading="lazy" />
         ${s.breaking ? '<span class="card-breaking-badge" aria-label="Breaking">Breaking</span>' : ""}
       </div>`
    : (featured
        ? `<div class="card-cover"><div class="card-cover-fallback" aria-hidden="true">📰</div>
           ${s.breaking ? '<span class="card-breaking-badge" aria-label="Breaking">Breaking</span>' : ""}
         </div>`
        : "");

  // Mini author
  const authorHTML = s.author?.name
    ? `<div class="card-author">
         ${s.author.photo
           ? `<img class="card-author-avatar" src="${escAttr(s.author.photo)}" alt="${escAttr(s.author.name)}" loading="lazy" />`
           : `<div class="card-author-avatar ai" aria-hidden="true">🤖</div>`}
         <span class="card-author-name">${escHTML(s.author.name)}</span>
         ${s.reading_time ? `<span class="card-reading-time">${escHTML(String(s.reading_time))} min</span>` : ""}
       </div>`
    : (s.reading_time
        ? `<div class="card-author"><span class="card-reading-time">${escHTML(String(s.reading_time))} min read</span></div>`
        : "");

  return `
    <article class="story-card${featured ? " featured" : ""}" style="--cat-color:${color}" dir="${isRTL ? "rtl" : "ltr"}" role="listitem">
      ${coverHTML}
      <div class="card-body">
        <div class="card-top">
          <span class="card-source"><span class="source-dot" aria-hidden="true"></span>${escHTML(s.source)}</span>
          ${age ? `<span class="card-age">${escHTML(age)}</span>` : ""}
        </div>
        <span class="cat-tag ${tagCls}">${escHTML(catLabel)}</span>
        <h3 class="card-title"><a href="${escAttr(articleHref)}">${escHTML(s.title)}</a></h3>
        ${s.summary ? `<p class="card-summary">${escHTML(s.summary)}</p>` : ""}
        ${authorHTML}
        <div class="card-footer">
          <a class="read-more" href="${escAttr(articleHref)}">${escHTML(readMore)}</a>
        </div>
      </div>
    </article>`;
}

/* ── Inline sponsor ── */
function inlineSponsorHTML(sp) {
  if (!sp) return "";
  const label = activeLang === "dv" ? "ސްޕޮންސަރ" : "Sponsor";
  const cta   = activeLang === "dv" ? "ބަލާލާ"    : "View";
  const img   = sp.images?.[0] || FALLBACK_IMG;
  return `
    <section class="inline-sponsor" dir="ltr" aria-label="Sponsored content">
      <div class="inline-sponsor-row">
        <span class="sponsor-name-label">${escHTML(label)} • ${escHTML(sp.name || "Samuga")}</span>
        <span class="ad-badge">Ad</span>
      </div>
      <a class="inline-sponsor-frame" href="${escAttr(sp.link || 'https://samugamedia.com')}" target="_blank" rel="noopener sponsored" aria-label="${escAttr(sp.caption || sp.name || 'Sponsor')}">
        <img src="${escAttr(img)}" alt="${escAttr(sp.caption || sp.name || '')}" loading="lazy" />
      </a>
      ${sp.caption ? `<p class="inline-sponsor-copy">${escHTML(sp.caption)}</p>` : ""}
    </section>`;
}

/* ── Ticker ── */
function renderTicker() {
  const track = qs("#tickerTrack");
  if (!track) return;
  const items = stories.filter(s => s.lang === activeLang).slice(0, 8);
  const fallback = activeLang === "dv"
    ? "ސަމުގާ އޭއައި ނިއުސްރޫމް ލައިވް ބަލަމުން ދަނީ"
    : "Samuga AI newsroom is monitoring Maldives news live";
  const html = (items.length ? items : [{ title: fallback }])
    .map(s => `<span>${escHTML(s.title)}</span>`).join("");
  track.innerHTML = html + html;  // doubled for seamless loop
}

/* ── Popular list ── */
function renderPopular() {
  const list = qs("#popularList");
  if (!list) return;
  const pop = stories.filter(s => s.lang === activeLang).slice(0, 5);
  if (!pop.length) {
    list.innerHTML = `<li><span class="popular-num">—</span><span>${activeLang==="dv" ? "ޕޮޕިއުލަރ ޚަބަރެއް ނެތް." : "No popular stories yet."}</span></li>`;
    return;
  }
  list.innerHTML = pop.map((s, i) => {
    const href = s.id ? `article.html?id=${encodeURIComponent(s.id)}` : escAttr(s.url);
    return `<li dir="${s.lang==="dv"?"rtl":"ltr"}">
      <span class="popular-num" aria-hidden="true">${i+1}</span>
      <a href="${escAttr(href)}">${escHTML(s.title)}</a>
    </li>`;
  }).join("");
}

/* ── Stats ── */
function updateStats() {
  const vis = stories.filter(s => s.lang === activeLang);
  const countEl = qs("#storyCount");
  const lastEl  = qs("#lastPost");
  if (countEl) countEl.textContent = vis.length || "—";
  if (lastEl)  lastEl.textContent  = vis[0]?.time || "Waiting";
}

/* ── UI strings ── */
function applyUIStrings() {
  const t = UI[activeLang];
  const map = {
    "#latestTitle":   "latest", "#popularTitle":  "popular",
    "#tipTitle":      "tipTitle", "#tipText":      "tipText",
    "#communityLink": "community", "#footerText":  "footer"
  };
  for (const [sel, key] of Object.entries(map)) {
    const el = qs(sel);
    if (el) el.textContent = t[key] || "";
  }
  const si = qs("#searchInput");
  if (si) si.placeholder = t.search;
  const sl = qs("#searchLabel");
  if (sl) sl.textContent = t.searchLabel;
  const sub = qs("#chatSubtitle");
  if (sub) sub.textContent = t.chatSub;
}

/* ════════════════════════════════════════════════════════════════
   CHAT
════════════════════════════════════════════════════════════════ */

function setupChat() {
  const fab    = qs("#chatFab");
  const panel  = qs("#chatPanel");
  const close  = qs("#chatClose");
  const form   = qs("#chatForm");
  const input  = qs("#chatInput");
  const send   = qs("#chatSend");
  const msgs   = qs("#chatMessages");

  if (!fab || !panel) return;

  const open  = () => { panel.classList.add("open");  fab.setAttribute("aria-expanded","true");  setTimeout(()=>input?.focus(),80); };
  const close_ = () => { panel.classList.remove("open"); fab.setAttribute("aria-expanded","false"); };
  const toggle = () => panel.classList.contains("open") ? close_() : open();

  fab.addEventListener("click", toggle);
  close?.addEventListener("click", close_);
  qsa("[data-open-chat]").forEach(b => b.addEventListener("click", open));

  // Quick prompts in chat
  qsa(".quick-prompt-btn").forEach(b => b.addEventListener("click", () => {
    if (input) { input.value = b.dataset.prompt || b.textContent; open(); input.focus(); }
  }));
  // Quick prompts on hero
  qsa("[data-prompt][data-open-chat]").forEach(b => b.addEventListener("click", () => {
    open();
    if (input) { input.value = b.dataset.prompt; input.focus(); }
  }));

  form?.addEventListener("submit", async e => {
    e.preventDefault();
    const msg = input?.value.trim();
    if (!msg) return;
    addMsg(msgs, msg, "user");
    input.value = "";
    if (send) send.disabled = true;
    const typing = addMsg(msgs, activeLang==="dv" ? "ސަމުގާ އޭއައި ޖަވާބު ހޯދަނީ…" : "Samuga AI is thinking…", "bot typing");
    try {
      const res  = await fetch(`${BOT_API_BASE}/api/chat`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ message:msg, lang:activeLang })
      });
      const data = await res.json().catch(() => ({}));
      typing.remove();
      addMsg(msgs, data.reply || "I could not find a clear answer right now.", "bot");
    } catch (_) {
      typing.remove();
      addMsg(msgs, "Connection issue. Please try again.", "bot");
    } finally {
      if (send) send.disabled = false;
      input?.focus();
    }
  });

  // Auto-resize textarea
  input?.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });
  input?.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form?.requestSubmit(); }
  });
}

function addMsg(container, text, cls) {
  const d = document.createElement("div");
  d.className = `msg ${cls}`;
  d.textContent = text;
  container.appendChild(d);
  container.scrollTop = container.scrollHeight;
  return d;
}

/* ════════════════════════════════════════════════════════════════
   UTILITIES
════════════════════════════════════════════════════════════════ */

function relativeTime(raw) {
  if (!raw || raw === "Live" || raw === "Recent" || raw === "Today") return raw || "";
  try {
    // Try ISO parse
    const d = new Date(raw);
    if (isNaN(d)) return raw;
    const mins = Math.floor((Date.now() - d.getTime()) / 60000);
    if (mins < 1)  return "just now";
    if (mins < 60) return `${mins}m ago`;
    const h = Math.floor(mins / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  } catch (_) { return raw; }
}

function escHTML(s) {
  return String(s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function escAttr(s) {
  return escHTML(s).replaceAll("`","&#096;");
}
