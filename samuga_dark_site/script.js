const BOT_API_BASE = "https://samuga-news-bot-production.up.railway.app";
const FALLBACK_IMAGE = "assets/SamugaNewsBot_Profile.png";

const fallbackStories = [
  {
    title: "Samuga AI newsroom is now monitoring Maldives news live",
    summary: "The system tracks local updates, breaking incidents, politics, economy and public-interest stories from multiple sources.",
    category: "Breaking",
    source: "Samuga Media",
    time: "Live",
    url: "#",
    image: FALLBACK_IMAGE,
    lang: "en"
  },
  {
    title: "AI-assisted publishing helps Samuga reduce social media posting limits",
    summary: "Stories can be published through the website while Telegram and social platforms continue operating with controlled posting.",
    category: "Community",
    source: "Samuga AI",
    time: "Today",
    url: "#",
    image: FALLBACK_IMAGE,
    lang: "en"
  }
];

let stories = [];
let activeCategory = "all";
let activeLang = "en";

const qs = (s) => document.querySelector(s);
const qsa = (s) => document.querySelectorAll(s);

const storyGrid = qs("#storyGrid");
const popularList = qs("#popularList");
const tickerTrack = qs("#tickerTrack");
const storyCount = qs("#storyCount");
const lastPost = qs("#lastPost");
const searchInput = qs("#searchInput");
const menuButton = qs("#menuButton");
const primaryNav = qs("#primaryNav");
const todayLine = qs("#todayLine");
const liveText = qs("#liveText");

document.addEventListener("DOMContentLoaded", init);

async function init() {
  setTodayLine();
  setupMenu();
  setupCategoryFilters();
  setupLanguageToggle();
  setupSearch();

  await loadStories();
}

function setTodayLine() {
  if (!todayLine) return;

  todayLine.textContent = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric"
  });
}

function setupMenu() {
  if (!menuButton || !primaryNav) return;

  menuButton.addEventListener("click", () => {
    const open = primaryNav.classList.toggle("open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

function setupCategoryFilters() {
  qsa(".nav-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      qsa(".nav-filter").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      activeCategory = btn.dataset.category || "all";

      renderAll();

      btn.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest"
      });
    });
  });
}

function setupLanguageToggle() {
  qsa(".lang-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      qsa(".lang-toggle").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      activeLang = btn.dataset.lang || "en";
      document.body.classList.toggle("lang-dv", activeLang === "dv");
      document.documentElement.lang = activeLang === "dv" ? "dv" : "en";
      document.documentElement.dir = activeLang === "dv" ? "rtl" : "ltr";

      renderAll();
    });
  });
}

function setupSearch() {
  searchInput?.addEventListener("input", render);
}

async function loadStories() {
  try {
    const res = await fetch(`${BOT_API_BASE}/api/stories`, { cache: "no-store" });

    if (!res.ok) throw new Error("API error");

    const data = await res.json();

    stories = Array.isArray(data)
      ? data.map(cleanStory).filter(Boolean)
      : [];

    if (!stories.length) {
      stories = fallbackStories.map(cleanStory).filter(Boolean);
    }
  } catch (e) {
    console.error("API failed, using fallback:", e);
    stories = fallbackStories.map(cleanStory).filter(Boolean);
  }

  renderAll();
}

function cleanStory(s) {
  if (!s || !s.title) return null;

  const title = String(s.title || "").trim();
  const summary = String(s.summary || "").trim();
  const source = String(s.source || "Samuga Media").trim();
  const rawCategory = s.category || s.cat || "LOCAL";
  const lang = detectLanguage(s);

  return {
    title,
    summary,
    source,
    time: s.time || s.posted_at || "Recent",
    url: s.url || s.link || "#",
    image: s.image || s.card || s.image_url || FALLBACK_IMAGE,
    lang,
    category: normalizeCategory(rawCategory, title, summary, source)
  };
}

function detectLanguage(s) {
  const declared = String(s.lang || s.language || "").toLowerCase();
  const text = `${s.title || ""} ${s.summary || ""}`;

  if (declared === "dv" || declared === "dhivehi") return "dv";
  if (/[\u0780-\u07BF]/.test(text)) return "dv";

  return "en";
}

function normalizeCategory(value, title = "", summary = "", source = "") {
  const raw = String(value || "").toUpperCase().trim();
  const text = `${title} ${summary} ${source}`.toLowerCase();

  if (
    raw === "BREAKING" ||
    raw === "DISASTER" ||
    text.includes("breaking") ||
    text.includes("murder") ||
    text.includes("killed") ||
    text.includes("dead") ||
    text.includes("dies") ||
    text.includes("death") ||
    text.includes("stabbed") ||
    text.includes("shot") ||
    text.includes("accident") ||
    text.includes("crash") ||
    text.includes("fire") ||
    text.includes("capsize") ||
    text.includes("sinking") ||
    text.includes("missing") ||
    text.includes("drug") ||
    text.includes("arrested") ||
    text.includes("emergency")
  ) {
    return "BREAKING";
  }

  if (
    raw === "POLITICAL" ||
    raw === "POLITICS" ||
    text.includes("president") ||
    text.includes("parliament") ||
    text.includes("majlis") ||
    text.includes("minister") ||
    text.includes("government") ||
    text.includes("election") ||
    text.includes("court") ||
    text.includes("law") ||
    text.includes("policy") ||
    text.includes("cabinet") ||
    text.includes("opposition") ||
    text.includes("mdp") ||
    text.includes("pnc")
  ) {
    return "POLITICAL";
  }

  if (
    raw === "BUSINESS" ||
    raw === "ECONOMY" ||
    text.includes("economy") ||
    text.includes("business") ||
    text.includes("finance") ||
    text.includes("budget") ||
    text.includes("debt") ||
    text.includes("mvr") ||
    text.includes("dollar") ||
    text.includes("bank") ||
    text.includes("tax") ||
    text.includes("price") ||
    text.includes("market")
  ) {
    return "BUSINESS";
  }

  if (
    raw === "SPORT" ||
    raw === "SPORTS" ||
    raw === "FOOTBALL" ||
    text.includes("football") ||
    text.includes("sports") ||
    text.includes("match") ||
    text.includes("fifa") ||
    text.includes("world cup") ||
    text.includes("tournament")
  ) {
    return "SPORTS";
  }

  if (
    raw === "WORLD" ||
    text.includes("war") ||
    text.includes("iran") ||
    text.includes("israel") ||
    text.includes("palestine") ||
    text.includes("ukraine") ||
    text.includes("china") ||
    text.includes("global")
  ) {
    return "WORLD";
  }

  if (
    raw === "LIFESTYLE" ||
    raw === "TOURISM" ||
    raw === "WEATHER" ||
    text.includes("tourism") ||
    text.includes("resort") ||
    text.includes("travel") ||
    text.includes("weather") ||
    text.includes("rain") ||
    text.includes("storm") ||
    text.includes("health") ||
    text.includes("education") ||
    text.includes("culture")
  ) {
    return "LIFESTYLE";
  }

  return "LOCAL";
}

function renderAll() {
  renderHeroIntro();
  render();
  renderTicker();
  renderPopular();
  updateStats();
}

function render() {
  if (!storyGrid) return;

  const query = (searchInput?.value || "").toLowerCase().trim();

  const filtered = stories.filter((s) => {
    const langOk = s.lang === activeLang;

    const catOk =
      activeCategory === "all" ||
      s.category === normalizeCategory(activeCategory);

    const qOk =
      !query ||
      `${s.title} ${s.summary} ${s.source}`.toLowerCase().includes(query);

    return langOk && catOk && qOk;
  });

  if (!filtered.length) {
    storyGrid.innerHTML = `
      <div class="empty-state">
        <strong>${activeLang === "dv" ? "ޚަބަރެއް ނުފެނުނު" : "No stories found"}</strong>
        ${activeLang === "dv" ? "އެހެން ކެޓަގަރީއެއް ނުވަތަ ސަރޗް ތަޖުރިބާ ކޮށްލާ." : "Try another category or search term."}
      </div>
    `;
    return;
  }

  storyGrid.innerHTML = filtered.map(cardHTML).join("");
}

function cardHTML(s) {
  const isBreaking = s.category === "BREAKING";
  const readMore = activeLang === "dv" ? "ތަފްސީލް ކިޔާ →" : "Read more →";

  return `
    <article class="story-card story-${s.lang}" dir="${s.lang === "dv" ? "rtl" : "ltr"}">
      <a class="story-image story-card-image" href="${escapeAttr(s.url)}" target="_blank" rel="noopener">
        <img
          src="${escapeAttr(s.image)}"
          alt="${escapeAttr(s.title)}"
          loading="lazy"
          onerror="this.src='${FALLBACK_IMAGE}'"
        />
      </a>

      <div class="story-body story-card-body">
        <div class="story-meta">
          <span class="tag ${isBreaking ? "breaking" : ""}">${escapeHTML(displayCategory(s.category))}</span>
          <span>${escapeHTML(s.source)}</span>
          <span>${escapeHTML(s.time)}</span>
        </div>

        <h3>
          <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHTML(s.title)}</a>
        </h3>

        <p>${escapeHTML(s.summary || "")}</p>

        <a class="read-more" href="${escapeAttr(s.url)}" target="_blank" rel="noopener">
          ${escapeHTML(readMore)}
        </a>
      </div>
    </article>
  `;
}

function renderHeroIntro() {
  const eyebrow =
    qs("#leadStory .eyebrow") ||
    qs("#leadStory .lead-copy .eyebrow");

  const title =
    qs("#leadStory .hero-title") ||
    qs("#leadStory h1");

  const summary =
    qs("#leadStory .hero-copy p") ||
    qs("#leadStory .lead-copy p") ||
    qs("#leadStory p");

  if (activeLang === "dv") {
    if (eyebrow) eyebrow.textContent = "ސަމުގާ އޭއައި ފީޑް";

    if (title) {
      title.textContent = "ސަމުގާ އޭއައިއިން ހިންގާ ލައިވް ޚަބަރު";
      title.dir = "rtl";
    }

    if (summary) {
      summary.textContent = "ދިވެހި ޚަބަރުތައް ސަމުގާ މީޑިއާ ފީޑްގައި ފެނޭނެ.";
      summary.dir = "rtl";
    }

    if (liveText) {
      liveText.textContent = "ސަމުގާ އޭއައި ނިއުސްރޫމް ޚަބަރު ބަލަމުން ދަނީ";
    }
  } else {
    if (eyebrow) eyebrow.textContent = "Samuga AI Feed";

    if (title) {
      title.textContent = "Live Maldives news, powered by Samuga AI";
      title.dir = "ltr";
    }

    if (summary) {
      summary.textContent = "Clean live updates from Samuga Media’s automated newsroom system.";
      summary.dir = "ltr";
    }

    if (liveText) {
      liveText.textContent = "Samuga AI newsroom is monitoring Maldives news live";
    }
  }
}

function renderTicker() {
  if (!tickerTrack) return;

  const items = stories
    .filter((s) => s.lang === activeLang)
    .slice(0, 6)
    .map((s) => `<span>${escapeHTML(s.title)}</span>`)
    .join("");

  tickerTrack.innerHTML = items + items;
}

function renderPopular() {
  if (!popularList) return;

  const popular = stories
    .filter((s) => s.lang === activeLang)
    .slice(0, 5);

  if (!popular.length) {
    popularList.innerHTML = `<li>${activeLang === "dv" ? "ޕޮޕިއުލަރ ޚަބަރެއް އަދި ނެތް." : "No popular stories yet."}</li>`;
    return;
  }

  popularList.innerHTML = popular
    .map((s) => `
      <li dir="${s.lang === "dv" ? "rtl" : "ltr"}">
        <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHTML(s.title)}</a>
      </li>
    `)
    .join("");
}

function updateStats() {
  const visible = stories.filter((s) => s.lang === activeLang);

  if (storyCount) storyCount.textContent = visible.length;
  if (lastPost) lastPost.textContent = visible[0]?.time || "Waiting";
}

function displayCategory(value) {
  const en = {
    BREAKING: "Breaking",
    LOCAL: "Local",
    POLITICAL: "Politics",
    BUSINESS: "Business",
    SPORTS: "Sports",
    WORLD: "World",
    LIFESTYLE: "Lifestyle"
  };

  const dv = {
    BREAKING: "ބްރޭކިންގ",
    LOCAL: "ލޯކަލް",
    POLITICAL: "ސިޔާސީ",
    BUSINESS: "އިޤްތިޞާދީ",
    SPORTS: "ކުޅިވަރު",
    WORLD: "ދުނިޔެ",
    LIFESTYLE: "ލައިފްސްޓައިލް"
  };

  return activeLang === "dv" ? (dv[value] || value) : (en[value] || value);
}

function normalize(value) {
  return String(value || "").toLowerCase().trim();
}

function escapeHTML(str) {
  return String(str || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(str) {
  return escapeHTML(str).replaceAll("`", "&#096;");
}
