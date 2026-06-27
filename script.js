const BOT_API_BASE = "https://samuga-news-bot-production.up.railway.app";
const FALLBACK_IMAGE = "assets/SamugaNewsBot_Profile.png";

const SPONSORS = [
  {
    image: "assets/sponsor_samuga_media.png",
    alt: "Promote your business with Samuga Media",
    url: "https://t.me/samugacommunity"
  },
  {
    image: "assets/sponsor_etronic.png",
    alt: "Etronic Maldives electrical solutions",
    url: "#"
  },
  {
    image: "assets/sponsor_berry_travels.png",
    alt: "Berry Travels speedboat transfer and trips",
    url: "#"
  }
];

const fallbackStories = [
  {title:"Samuga AI newsroom is now monitoring Maldives news live",summary:"The system tracks local updates, breaking incidents, politics, economy and public-interest stories from multiple sources.",category:"Breaking",source:"Samuga Media",time:"Live",url:"#",image:FALLBACK_IMAGE,lang:"en"},
  {title:"AI-assisted publishing helps Samuga reduce social media posting limits",summary:"Stories can be published through the website while Telegram and social platforms continue operating with controlled posting.",category:"Community",source:"Samuga AI",time:"Today",url:"#",image:FALLBACK_IMAGE,lang:"en"}
];

let stories = [];
let activeCategory = "all";
let activeLang = "en";
let sponsorIndex = 0;

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
const sponsorImage = qs("#sponsorImage");
const sponsorLink = qs("#sponsorLink");
const sponsorDots = qs("#sponsorDots");

const STATIC_TEXT = {
  en:{latest:"Latest Stories",popular:"Popular",tipTitle:"Send a Tip",tipText:"Have a Maldives story for Samuga AI to watch?",community:"Join Samuga Community →",footer:"Live news, powered by Samuga AI.",placeholder:"Search stories"},
  dv:{latest:"އެންމެ ފަހުގެ ޚަބަރުތައް",popular:"ޕޮޕިއުލަރ",tipTitle:"ޚަބަރު ފޮނުވާ",tipText:"ސަމުގާ އޭއައި ބަލަންޖެހޭ ޚަބަރެއް އޮތްތަ؟",community:"ސަމުގާ ކޮމިއުނިޓީއަށް ޖޮއިން ވޭ →",footer:"ސަމުގާ އޭއައިއިން ހިންގާ ލައިވް ޚަބަރު.",placeholder:"ޚަބަރު ހޯދާ"}
};

document.addEventListener("DOMContentLoaded", init);

async function init(){
  setTodayLine();
  setupMenu();
  setupCategoryFilters();
  setupLanguageToggle();
  setupSearch();
  setupSponsors();
  await loadStories();
}

function setTodayLine(){
  if(!todayLine) return;
  todayLine.textContent = new Date().toLocaleDateString("en-GB",{weekday:"long",day:"2-digit",month:"long",year:"numeric"});
}

function setupMenu(){
  if(!menuButton || !primaryNav) return;
  menuButton.addEventListener("click",()=>{
    const open = primaryNav.classList.toggle("open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

function setupCategoryFilters(){
  qsa(".nav-filter").forEach((btn)=>{
    btn.addEventListener("click",()=>{
      qsa(".nav-filter").forEach((b)=>b.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.dataset.category || "all";
      renderAll();
    });
  });
}

function setupLanguageToggle(){
  qsa(".lang-toggle").forEach((btn)=>{
    btn.addEventListener("click",()=>{
      qsa(".lang-toggle").forEach((b)=>b.classList.remove("active"));
      btn.classList.add("active");
      activeLang = btn.dataset.lang || "en";
      document.body.classList.toggle("lang-dv", activeLang === "dv");
      document.documentElement.lang = activeLang === "dv" ? "dv" : "en";
      document.documentElement.dir = activeLang === "dv" ? "rtl" : "ltr";
      updateStaticLanguageText();
      renderAll();
    });
  });
}

function setupSearch(){
  searchInput?.addEventListener("input", renderStories);
}

function setupSponsors(){
  if(!sponsorImage || !sponsorDots) return;
  sponsorDots.innerHTML = SPONSORS.map((_,i)=>`<button class="sponsor-dot${i===0?" active":""}" type="button" aria-label="Show sponsor ${i+1}" data-index="${i}"></button>`).join("");
  qsa(".sponsor-dot").forEach((dot)=>dot.addEventListener("click",()=>showSponsor(Number(dot.dataset.index || 0))));
  showSponsor(0);
  setInterval(()=>showSponsor((sponsorIndex + 1) % SPONSORS.length), 7000);
}

function showSponsor(index){
  sponsorIndex = index;
  const sponsor = SPONSORS[sponsorIndex];
  if(!sponsor || !sponsorImage) return;
  sponsorImage.style.opacity = "0";
  setTimeout(()=>{
    sponsorImage.src = sponsor.image;
    sponsorImage.alt = sponsor.alt;
    if(sponsorLink) sponsorLink.href = sponsor.url;
    sponsorImage.style.opacity = "1";
  }, 120);
  qsa(".sponsor-dot").forEach((dot,i)=>dot.classList.toggle("active", i === sponsorIndex));
}

async function loadStories(){
  try{
    const res = await fetch(`${BOT_API_BASE}/api/stories`,{cache:"no-store"});
    if(!res.ok) throw new Error("API error");
    const data = await res.json();
    stories = Array.isArray(data) ? data.map(cleanStory).filter(Boolean) : [];
    if(!stories.length) stories = fallbackStories.map(cleanStory).filter(Boolean);
  }catch(e){
    console.error("API failed, using fallback:", e);
    stories = fallbackStories.map(cleanStory).filter(Boolean);
  }
  updateStaticLanguageText();
  renderAll();
}

function cleanStory(s){
  if(!s || !s.title) return null;
  const title = String(s.title || "").trim();
  const summary = String(s.summary || "").trim();
  const source = String(s.source || "Samuga Media").trim();
  const rawCategory = s.category || s.cat || "LOCAL";
  const lang = detectLanguage(s);
  return {title,summary,source,time:s.time || s.posted_at || "Recent",url:s.url || s.link || "#",lang,category:normalizeCategory(rawCategory,title,summary,source)};
}

function detectLanguage(s){
  const declared = String(s.lang || s.language || "").toLowerCase();
  const text = `${s.title || ""} ${s.summary || ""}`;
  if(declared === "dv" || declared === "dhivehi") return "dv";
  if(/[\u0780-\u07BF]/.test(text)) return "dv";
  return "en";
}

function normalizeCategory(value,title="",summary="",source=""){
  const raw = String(value || "").toUpperCase().trim();
  const text = `${title} ${summary} ${source}`.toLowerCase();
  if(raw === "BREAKING" || raw === "DISASTER" || ["breaking","murder","killed","dead","dies","death","stabbed","shot","accident","crash","fire","capsize","sinking","missing","drug","arrested","emergency"].some(w=>text.includes(w))) return "BREAKING";
  if(raw === "POLITICAL" || raw === "POLITICS" || ["president","parliament","majlis","minister","government","election","court","law","policy","cabinet","opposition","mdp","pnc"].some(w=>text.includes(w))) return "POLITICAL";
  if(raw === "BUSINESS" || raw === "ECONOMY" || ["economy","business","finance","budget","debt","mvr","dollar","bank","tax","price","market"].some(w=>text.includes(w))) return "BUSINESS";
  if(raw === "SPORT" || raw === "SPORTS" || raw === "FOOTBALL" || ["football","sports","match","fifa","world cup","tournament"].some(w=>text.includes(w))) return "SPORTS";
  if(raw === "WORLD" || ["war","iran","israel","palestine","ukraine","china","global"].some(w=>text.includes(w))) return "WORLD";
  if(raw === "LIFESTYLE" || raw === "TOURISM" || raw === "WEATHER" || ["tourism","resort","travel","weather","rain","storm","health","education","culture"].some(w=>text.includes(w))) return "LIFESTYLE";
  return "LOCAL";
}

function renderAll(){
  renderHeroIntro();
  renderStories();
  renderTicker();
  renderPopular();
  updateStats();
}

function renderStories(){
  if(!storyGrid) return;
  const query = (searchInput?.value || "").toLowerCase().trim();
  const filtered = stories.filter((s)=>{
    const langOk = s.lang === activeLang;
    const catOk = activeCategory === "all" || s.category === normalizeCategory(activeCategory);
    const qOk = !query || `${s.title} ${s.summary} ${s.source}`.toLowerCase().includes(query);
    return langOk && catOk && qOk;
  });
  if(!filtered.length){
    storyGrid.innerHTML = `<div class="empty-state"><strong>${activeLang === "dv" ? "ޚަބަރެއް ނުފެނުނު" : "No stories found"}</strong>${activeLang === "dv" ? "އެހެން ކެޓަގަރީއެއް ނުވަތަ ސަރޗް ތަޖުރިބާ ކޮށްލާ." : "Try another category or search term."}</div>`;
    return;
  }
  storyGrid.innerHTML = filtered.map(cardHTML).join("");
}

function cardHTML(s){
  const isBreaking = s.category === "BREAKING";
  const readMore = activeLang === "dv" ? "ތަފްސީލް ކިޔާ →" : "Read more →";
  return `<article class="story-card story-${s.lang}" dir="${s.lang === "dv" ? "rtl" : "ltr"}">
    <div class="story-topline"><span class="story-source">${escapeHTML(s.source)}</span><span class="story-time">${escapeHTML(s.time)}</span></div>
    <div class="story-body story-card-body">
      <div class="story-meta"><span class="tag ${isBreaking ? "breaking" : ""}">${escapeHTML(displayCategory(s.category))}</span></div>
      <h3><a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHTML(s.title)}</a></h3>
      <p>${escapeHTML(s.summary || "")}</p>
      <a class="read-more" href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHTML(readMore)}</a>
    </div>
  </article>`;
}

function renderHeroIntro(){
  const eyebrow = qs("#leadStory .eyebrow");
  const title = qs("#leadStory .hero-title");
  const summary = qs("#leadStory .lead-copy p");
  if(activeLang === "dv"){
    if(eyebrow) eyebrow.textContent = "ސަމުގާ އޭއައި ފީޑް";
    if(title){title.textContent = "ސަމުގާ އޭއައިއިން ހިންގާ ލައިވް ޚަބަރު";title.dir = "rtl";}
    if(summary){summary.textContent = "ދިވެހި ޚަބަރުތައް ސަމުގާ މީޑިއާ ފީޑްގައި ފެނޭނެ.";summary.dir = "rtl";}
  }else{
    if(eyebrow) eyebrow.textContent = "Samuga AI Feed";
    if(title){title.textContent = "Live Maldives news, powered by Samuga AI";title.dir = "ltr";}
    if(summary){summary.textContent = "Clean live updates from Samuga Media’s automated newsroom system.";summary.dir = "ltr";}
  }
}

function renderTicker(){
  if(!tickerTrack) return;
  const visible = stories.filter((s)=>s.lang === activeLang).slice(0,6);
  const fallback = activeLang === "dv" ? "ސަމުގާ އޭއައި ނިއުސްރޫމް ޚަބަރު ބަލަމުން ދަނީ" : "Samuga AI newsroom is monitoring Maldives news live";
  const items = (visible.length ? visible : [{title:fallback}]).map((s)=>`<span>${escapeHTML(s.title)}</span>`).join("");
  tickerTrack.innerHTML = items + items;
}

function renderPopular(){
  if(!popularList) return;
  const popular = stories.filter((s)=>s.lang === activeLang).slice(0,5);
  if(!popular.length){
    popularList.innerHTML = `<li>${activeLang === "dv" ? "ޕޮޕިއުލަރ ޚަބަރެއް އަދި ނެތް." : "No popular stories yet."}</li>`;
    return;
  }
  popularList.innerHTML = popular.map((s)=>`<li dir="${s.lang === "dv" ? "rtl" : "ltr"}"><a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHTML(s.title)}</a></li>`).join("");
}

function updateStats(){
  const visible = stories.filter((s)=>s.lang === activeLang);
  if(storyCount) storyCount.textContent = visible.length;
  if(lastPost) lastPost.textContent = visible[0]?.time || "Waiting";
}

function updateStaticLanguageText(){
  const latestTitle = qs("#latestTitle");
  const popularTitle = qs("#popularTitle");
  const tipTitle = qs("#tipTitle");
  const tipText = qs("#tipText");
  const communityLink = qs("#communityLink");
  const footerText = qs("#footerText");
  const t = STATIC_TEXT[activeLang] || STATIC_TEXT.en;
  if(latestTitle) latestTitle.textContent = t.latest;
  if(popularTitle) popularTitle.textContent = t.popular;
  if(tipTitle) tipTitle.textContent = t.tipTitle;
  if(tipText) tipText.textContent = t.tipText;
  if(communityLink) communityLink.textContent = t.community;
  if(footerText) footerText.textContent = t.footer;
  if(searchInput) searchInput.placeholder = t.placeholder;
}

function displayCategory(value){
  const en = {BREAKING:"Breaking",LOCAL:"Local",POLITICAL:"Politics",BUSINESS:"Business",SPORTS:"Sports",WORLD:"World",LIFESTYLE:"Lifestyle"};
  const dv = {BREAKING:"ބްރޭކިންގ",LOCAL:"ލޯކަލް",POLITICAL:"ސިޔާސީ",BUSINESS:"އިޤްތިޞާދީ",SPORTS:"ކުޅިވަރު",WORLD:"ދުނިޔެ",LIFESTYLE:"ލައިފްސްޓައިލް"};
  return activeLang === "dv" ? (dv[value] || value) : (en[value] || value);
}

function escapeHTML(str){
  return String(str || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}

function escapeAttr(str){
  return escapeHTML(str).replaceAll("`","&#096;");
}
