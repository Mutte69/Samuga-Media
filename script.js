/* ════════════════════════════════════════════════════════════════
   Samuga Media V3 — script.js
   Fully consumes Sprint A API: cover_image, author{},
   reading_time, featured, breaking, seo{}, published_at, updated_at
════════════════════════════════════════════════════════════════ */
"use strict";

const API          = "https://samuga-news-bot-production.up.railway.app";
const FALLBACK_IMG = "assets/SamugaNewsBot_Profile.png";

const SPONSORS = [
  { name:"Samuga Media", caption:"Promote your business with Samuga Media", link:"https://t.me/samugacommunity", img:"assets/sponsor_samuga_media.png" },
  { name:"Etronic Maldives", caption:"Etronic Maldives — electrical solutions", link:"#", img:"assets/sponsor_etronic.png" },
  { name:"Berry Travels", caption:"Berry Travels — speedboat transfers & trips", link:"#", img:"assets/sponsor_berry_travels.png" },
];

const CAT_COLOR = {
  BREAKING:"var(--cat-breaking)", LOCAL:"var(--cat-local)",
  POLITICAL:"var(--cat-political)", BUSINESS:"var(--cat-business)",
  SPORTS:"var(--cat-sports)", WORLD:"var(--cat-world)", LIFESTYLE:"var(--cat-lifestyle)",
};
const CAT_CLASS = { BREAKING:"breaking", POLITICAL:"politics", BUSINESS:"business", SPORTS:"sports", WORLD:"world", LIFESTYLE:"lifestyle" };
const CAT_EN = { BREAKING:"Breaking", LOCAL:"Local", POLITICAL:"Politics", BUSINESS:"Business", SPORTS:"Sports", WORLD:"World", LIFESTYLE:"Lifestyle" };
const CAT_DV = { BREAKING:"ބްރޭކިންގ", LOCAL:"ލޯކަލް", POLITICAL:"ސިޔާސީ", BUSINESS:"އިޤްތިޞާދީ", SPORTS:"ކުޅިވަރު", WORLD:"ދުނިޔެ", LIFESTYLE:"ލައިފްސްޓައިލް" };

const UI = {
  en:{ latest:"Latest Stories", popular:"Most Read", tipTitle:"Send a Tip", tipText:"Have a Maldives story for Samuga AI to watch?", community:"Join Samuga Community →", footer:"Live news, powered by Samuga AI.", search:"Search stories…", chatSub:"Live Maldives news assistant", readMore:"Read more →", statsTitle:"Newsroom", empty:"No stories found", emptyHint:"Try another category or search term." },
  dv:{ latest:"އެންމެ ފަހުގެ ޚަބަރުތައް", popular:"ޕޮޕިއުލަރ", tipTitle:"ޚަބަރު ފޮނުވާ", tipText:"ސަމުގާ އޭއައި ބަލަންޖެހޭ ޚަބަރެއް އޮތްތަ؟", community:"ސަމުގާ ކޮމިއުނިޓީ ޖޮއިން ވޭ →", footer:"ސަމުގާ އޭއައިއިން ހިންގާ ލައިވް ޚަބަރު.", search:"ޚަބަރު ހޯދާ…", chatSub:"ސަމުގާ ލައިވް ޚަބަރު", readMore:"ތަފްސީލް →", statsTitle:"ނިއުސްރޫމް", empty:"ޚަބަރެއް ނުފެނުނު", emptyHint:"އެހެން ކެޓަގަރީއެއް ތަޖުރިބާ ކޮށްލާ." }
};

// State
let stories = [], activeLang = "en", activeCat = "all", dynBanner = null;
let sponsorIdx = 0, sponsorTimer = null;

const qs  = s => document.querySelector(s);
const qsa = s => document.querySelectorAll(s);
const esc = s => String(s||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
const escA = s => esc(s).replaceAll("`","&#096;");

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  startClock();
  setTodayLine();
  setupMenu();
  setupCatNav();
  setupLang();
  setupSearch();
  setupChat();
  await loadBanner();
  initSponsors();
  await loadStories();
});

// ── Clock ─────────────────────────────────────────────────────────
function startClock(){
  const te=qs("#clockTime"), de=qs("#clockDate"), he=qs("#clockHijri");
  if(!te)return;
  const tick=()=>{
    const mvt=new Date(Date.now()+5*3600000);
    te.textContent=[mvt.getUTCHours(),mvt.getUTCMinutes(),mvt.getUTCSeconds()].map(n=>String(n).padStart(2,"0")).join(":");
    if(de) de.textContent=mvt.toLocaleDateString("en-GB",{weekday:"short",day:"2-digit",month:"short",year:"numeric",timeZone:"UTC"});
    if(he){ try{ he.textContent=new Intl.DateTimeFormat("en-TN-u-ca-islamic",{day:"numeric",month:"long",year:"numeric"}).format(mvt); }catch{} }
  };
  tick(); setInterval(tick,1000);
}
function setTodayLine(){
  const el=qs("#todayLine"); if(!el)return;
  const mvt=new Date(Date.now()+5*3600000);
  el.textContent=mvt.toLocaleDateString("en-GB",{weekday:"long",day:"2-digit",month:"long",year:"numeric",timeZone:"UTC"});
}

// ── Navigation ────────────────────────────────────────────────────
function setupMenu(){
  const btn=qs("#menuBtn"),nav=qs("#primaryNav");
  if(!btn||!nav)return;
  btn.addEventListener("click",()=>{
    const o=nav.classList.toggle("open");
    btn.setAttribute("aria-expanded",String(o));
  });
}
function setupCatNav(){
  qsa(".nav-btn").forEach(b=>b.addEventListener("click",()=>{
    qsa(".nav-btn").forEach(x=>{x.classList.remove("active");x.removeAttribute("aria-current");});
    b.classList.add("active"); b.setAttribute("aria-current","page");
    activeCat=b.dataset.cat||"all"; renderStories();
  }));
}
function setupLang(){
  qsa(".lang-btn").forEach(b=>b.addEventListener("click",()=>{
    qsa(".lang-btn").forEach(x=>{x.classList.remove("active");x.setAttribute("aria-pressed","false");});
    b.classList.add("active"); b.setAttribute("aria-pressed","true");
    activeLang=b.dataset.lang||"en";
    const dv=activeLang==="dv";
    document.body.classList.toggle("lang-dv",dv);
    document.documentElement.lang=dv?"dv":"en";
    document.documentElement.dir=dv?"rtl":"ltr";
    applyUI(); renderAll();
  }));
}
function setupSearch(){
  const el=qs("#searchInput");
  if(el) el.addEventListener("input",renderStories);
}

// ── Banner ────────────────────────────────────────────────────────
async function loadBanner(){
  try{
    const r=await fetch(`${API}/api/banner`,{cache:"no-store"});
    const d=await r.json();
    if(d?.active&&d?.image_url) dynBanner={name:"Sponsor",caption:d.text||"Sponsored",link:d.link||"https://samugamedia.com",img:d.image_url};
  }catch{}
}

// ── Sponsors ──────────────────────────────────────────────────────
function sponsorPool(){ return dynBanner?[{...dynBanner},...SPONSORS]:SPONSORS.slice(); }

function initSponsors(){
  buildDots(); showSponsor(0);
  sponsorTimer=setInterval(()=>showSponsor(sponsorIdx+1),6000);
  qs("#sponsorPrev")?.addEventListener("click",()=>showSponsor(sponsorIdx-1,true));
  qs("#sponsorNext")?.addEventListener("click",()=>showSponsor(sponsorIdx+1,true));
  const pool=sponsorPool();
  if(pool.length>1){
    const s=pool[1],p=qs("#sideSponsorPanel"),i=qs("#sideSponsorImage"),c=qs("#sideSponsorCaption"),l=qs("#sideSponsorLink");
    if(p&&i&&s.img){ i.src=s.img; i.alt=s.caption||s.name; if(c)c.textContent=s.caption||""; if(l)l.href=s.link||"#"; p.style.display=""; }
  }
}
function buildDots(){
  const d=qs("#sponsorDots"); if(!d)return;
  d.innerHTML=sponsorPool().map((_,i)=>`<button class="sp-dot${i===0?" active":""}" data-si="${i}" aria-label="Sponsor ${i+1}" role="tab" aria-selected="${i===0}"></button>`).join("");
  qsa("[data-si]").forEach(b=>b.addEventListener("click",()=>showSponsor(+b.dataset.si,true)));
}
function showSponsor(idx,manual=false){
  const pool=sponsorPool();
  sponsorIdx=((idx%pool.length)+pool.length)%pool.length;
  const item=pool[sponsorIdx];
  const img=qs("#sponsorImage"),cap=qs("#sponsorCaption"),link=qs("#heroSponsorLink"),frame=qs(".sponsor-frame");
  if(!img||!item)return;
  frame?.classList.add("changing");
  setTimeout(()=>{
    img.src=item.img||FALLBACK_IMG; img.alt=item.caption||item.name;
    if(cap)cap.textContent=item.caption||"";
    if(link)link.href=item.link||"#";
    frame?.classList.remove("changing");
  },180);
  qsa(".sp-dot").forEach((d,i)=>{d.classList.toggle("active",i===sponsorIdx);d.setAttribute("aria-selected",String(i===sponsorIdx));});
  if(manual){clearInterval(sponsorTimer);sponsorTimer=setInterval(()=>showSponsor(sponsorIdx+1),6000);}
}

// ── Stories: load ─────────────────────────────────────────────────
const FALLBACK_STORIES=[
  {id:"fb1",title:"Samuga AI newsroom is monitoring Maldives news live",summary:"The system tracks local updates, breaking incidents, politics, economy and public-interest stories.",category:"LOCAL",source:"Samuga Media",time:"Live",lang:"en",url:"#",cover_image:null,author:null,reading_time:null,featured:false,breaking:false},
  {id:"fb2",title:"AI-assisted publishing helps Samuga deliver faster news",summary:"Stories can be published through the website while Telegram and social platforms continue operating.",category:"LOCAL",source:"Samuga AI",time:"Today",lang:"en",url:"#",cover_image:null,author:null,reading_time:null,featured:false,breaking:false},
];

async function loadStories(){
  try{
    const r=await fetch(`${API}/api/stories`,{cache:"no-store"});
    if(!r.ok)throw Error("api");
    const d=await r.json();
    stories=Array.isArray(d)?d.map(clean).filter(Boolean):[];
    if(!stories.length)stories=FALLBACK_STORIES;
  }catch(e){ console.warn("stories failed",e); stories=FALLBACK_STORIES; }
  applyUI(); renderAll();
}

function clean(s){
  if(!s?.title)return null;
  return {
    id:s.id||"", title:String(s.title||"").trim(), summary:String(s.summary||"").trim(),
    source:String(s.source||"Samuga Media").trim(), time:s.time||s.published_at||"Recent",
    url:s.url||s.link||"#", lang:detectLang(s),
    category:normCat(s.category||s.cat||"LOCAL",s.title,s.summary,s.source),
    cover_image:s.cover_image||null, author:s.author||null,
    reading_time:s.reading_time||null, featured:!!s.featured,
    breaking:!!(s.breaking||(s.category||"").toUpperCase()==="BREAKING"),
  };
}

function detectLang(s){
  const d=String(s.lang||"").toLowerCase();
  if(d==="dv"||d==="dhivehi")return"dv";
  if(/[\u0780-\u07BF]/.test(`${s.title||""} ${s.summary||""}`))return"dv";
  return"en";
}

function normCat(v,title="",summary="",source=""){
  const raw=String(v||"").toUpperCase().trim();
  const txt=`${title} ${summary} ${source}`.toLowerCase();
  if(raw==="BREAKING"||raw==="DISASTER"||/breaking|murder|killed|dead|dies|death|stabbed|shot|accident|crash|fire|capsize|sinking|missing|drug|arrested|emergency/.test(txt))return"BREAKING";
  if(raw==="POLITICAL"||raw==="POLITICS"||/president|parliament|majlis|minister|government|election|court|law|policy|cabinet|opposition|mdp|pnc/.test(txt))return"POLITICAL";
  if(raw==="BUSINESS"||raw==="ECONOMY"||/economy|business|finance|budget|debt|mvr|dollar|bank|tax|price|market/.test(txt))return"BUSINESS";
  if(raw==="SPORT"||raw==="SPORTS"||raw==="FOOTBALL"||/football|sports|match|fifa|world cup|tournament/.test(txt))return"SPORTS";
  if(raw==="WORLD"||/war|iran|israel|palestine|ukraine|china|global|india/.test(txt))return"WORLD";
  if(raw==="LIFESTYLE"||raw==="TOURISM"||raw==="WEATHER"||/tourism|resort|travel|weather|rain|storm|health|education|culture/.test(txt))return"LIFESTYLE";
  return"LOCAL";
}

// ── Render all ────────────────────────────────────────────────────
function renderAll(){ renderFeatured(); renderBreaking(); renderStories(); renderTicker(); renderPopular(); renderTrending(); updateStats(); }

// ── Featured hero ─────────────────────────────────────────────────
function renderFeatured(){
  const featured=stories.filter(s=>s.lang===activeLang&&(s.featured||s.breaking))[0]
    || stories.filter(s=>s.lang===activeLang)[0];
  if(!featured){ renderDefaultHero(); return; }

  const hl=qs("#featuredHeadline"),sm=qs("#featuredSummary"),ey=qs("#featuredEyebrow");
  const meta=qs("#featuredMeta"),rb=qs("#featuredReadBtn"),cov=qs("#featuredCover");

  if(ey)ey.textContent=featured.breaking?"🔴 Breaking":(CAT_EN[featured.category]||featured.category||"Samuga AI Feed");
  if(hl){ hl.textContent=featured.title; hl.dir=featured.lang==="dv"?"rtl":"ltr"; }
  if(sm){ sm.textContent=featured.summary; sm.dir=featured.lang==="dv"?"rtl":"ltr"; }

  // Cover image or keep orb
  if(featured.cover_image&&cov){
    cov.innerHTML=`<img src="${esc(featured.cover_image)}" alt="${esc(featured.title)}" loading="eager" style="width:100%;height:100%;object-fit:cover"><div class="featured-cover-gradient"></div>`;
  }

  if(meta){
    const aName=featured.author?.name||"Samuga AI";
    const aPhoto=featured.author?.photo;
    const avatarHTML=aPhoto?`<img src="${esc(aPhoto)}" alt="${esc(aName)}" style="width:20px;height:20px;border-radius:50%;object-fit:cover">`:`<div class="featured-author-dot">🤖</div>`;
    const rt=featured.reading_time?`<span style="font-size:11px;color:var(--muted-faint);font-family:var(--font-ui)">· ${esc(String(featured.reading_time))} min read</span>`:"";
    meta.innerHTML=`<div class="featured-author">${avatarHTML}<span>${esc(aName)}</span></div><span class="featured-time">${esc(relTime(featured.time))}</span>${rt}`;
  }
  const href=featured.id&&featured.id.startsWith("fb")?featured.url:`article.html?id=${encodeURIComponent(featured.id)}`;
  if(rb){ rb.href=href; rb.textContent="Read story →"; }
}

function renderDefaultHero(){
  const ey=qs("#featuredEyebrow"),hl=qs("#featuredHeadline"),sm=qs("#featuredSummary");
  const rb=qs("#featuredReadBtn");
  if(activeLang==="dv"){
    if(ey)ey.textContent="ސަމުގާ އޭއައި ފީޑް";
    if(hl){ hl.textContent="ސަމުގާ އޭއައިއާ އެކު ލައިވް ޚަބަރު"; hl.dir="rtl"; }
    if(sm){ sm.textContent="ސަމުގާ ލައިވް ޚަބަރު ފީޑްގެ ދިވެހި ތަޖުރިބާ."; sm.dir="rtl"; }
  } else {
    if(ey)ey.textContent="Samuga AI Feed";
    if(hl){ hl.textContent="Live Maldives news, powered by Samuga AI"; hl.dir="ltr"; }
    if(sm){ sm.textContent="Ask Samuga AI about the latest Maldives news, breaking stories and public archive."; sm.dir="ltr"; }
  }
  if(rb){ rb.href="#latest"; rb.textContent="Explore all stories →"; }
}

// ── Breaking panel ────────────────────────────────────────────────
function renderBreaking(){
  const panel=qs("#breakingPanel"),items=qs("#breakingItems");
  if(!panel||!items)return;
  const brk=stories.filter(s=>s.lang===activeLang&&s.breaking).slice(0,3);
  if(!brk.length){ panel.style.display="none"; return; }
  panel.style.display="";
  items.innerHTML=brk.map(s=>{
    const href=s.id&&!s.id.startsWith("fb")?`article.html?id=${encodeURIComponent(s.id)}`:escA(s.url);
    return`<a class="breaking-item" href="${escA(href)}">
      <div class="breaking-item-title">${esc(s.title)}</div>
      <div class="breaking-item-time">${esc(relTime(s.time))}</div>
    </a>`;
  }).join("");
}

// ── Ticker ────────────────────────────────────────────────────────
function renderTicker(){
  const track=qs("#tickerTrack"); if(!track)return;
  const items=stories.filter(s=>s.lang===activeLang).slice(0,8);
  const fallback=activeLang==="dv"?"ސަމުގާ އޭއައި ނިއުސްރޫމް ލައިވް ބަލަމުން ދަނީ":"Samuga AI newsroom is monitoring Maldives news live";
  const html=(items.length?items:[{title:fallback}]).map(s=>`<span>${esc(s.title)}</span>`).join("");
  track.innerHTML=html+html;
}

// ── Story cards ───────────────────────────────────────────────────
function renderStories(){
  const grid=qs("#storyGrid"); if(!grid)return;
  const q=(qs("#searchInput")?.value||"").toLowerCase().trim();
  const t=UI[activeLang];
  const filtered=stories.filter(s=>{
    if(s.lang!==activeLang)return false;
    if(activeCat!=="all"&&s.category!==normCat(activeCat))return false;
    if(q&&!`${s.title} ${s.summary} ${s.source}`.toLowerCase().includes(q))return false;
    return true;
  });

  if(!filtered.length){
    grid.innerHTML=`<div class="empty-state" role="status"><strong>${esc(t.empty)}</strong><p>${esc(t.emptyHint)}</p></div>`;
    return;
  }

  const pool=sponsorPool();
  let featuredUsed=false;
  const chunks=[];
  filtered.forEach((s,idx)=>{
    const isFeat=s.featured&&!featuredUsed;
    if(isFeat)featuredUsed=true;
    chunks.push(cardHTML(s,isFeat));
    if((idx+1)%4===0&&pool.length){
      const sp=pool[Math.floor((idx+1)/4-1)%pool.length];
      chunks.push(inlineSponsor(sp));
    }
  });
  grid.innerHTML=chunks.join("");
}

function cardHTML(s,featured=false){
  const cat=s.category||"LOCAL";
  const color=CAT_COLOR[cat]||"var(--cat-local)";
  const cls=CAT_CLASS[cat]||"";
  const label=activeLang==="dv"?(CAT_DV[cat]||cat):(CAT_EN[cat]||cat);
  const href=s.id&&!s.id.startsWith("fb")?`article.html?id=${encodeURIComponent(s.id)}`:escA(s.url);
  const age=relTime(s.time);
  const rm=UI[activeLang].readMore;

  const coverHTML=s.cover_image
    ?`<div class="card-cover"><img src="${esc(s.cover_image)}" alt="" loading="lazy">${s.breaking?`<span class="card-breaking-badge">Breaking</span>`:""}</div>`
    :(featured?`<div class="card-cover"><div class="card-no-cover"><div class="card-no-cover-icon">📰</div></div>${s.breaking?`<span class="card-breaking-badge">Breaking</span>`:""}</div>`:"");

  const authorHTML=s.author?.name?`<div class="card-author-row">
    ${s.author.photo?`<img class="card-author-avatar" src="${esc(s.author.photo)}" alt="${esc(s.author.name)}" loading="lazy">`:``}
    <span class="card-author-name">${esc(s.author.name)}</span>
    ${s.reading_time?`<span class="card-reading-time">${esc(String(s.reading_time))} min</span>`:""}
  </div>`:(s.reading_time?`<div class="card-author-row"><span class="card-reading-time">${esc(String(s.reading_time))} min read</span></div>`:"");

  return`<article class="story-card${featured?" featured-card":""}" style="--cat-color:${color}" dir="${s.lang==="dv"?"rtl":"ltr"}" role="listitem">
    ${coverHTML}
    <div class="card-body">
      <div class="card-meta">
        <span class="card-source"><span class="source-dot"></span>${esc(s.source)}</span>
        ${age?`<span class="card-time">${esc(age)}</span>`:""}
      </div>
      <span class="cat-tag ${cls}">${esc(label)}</span>
      <h3 class="card-title"><a href="${escA(href)}">${esc(s.title)}</a></h3>
      ${s.summary?`<p class="card-summary">${esc(s.summary)}</p>`:""}
      ${authorHTML}
      <div class="card-footer"><a class="read-link" href="${escA(href)}">${esc(rm)}</a></div>
    </div>
  </article>`;
}

function inlineSponsor(sp){
  if(!sp)return"";
  const label=activeLang==="dv"?"ސްޕޮންސަރ":"Sponsor";
  return`<section class="inline-sponsor" dir="ltr">
    <div class="inline-sponsor-row"><span class="inline-sponsor-name">${esc(label)} · ${esc(sp.name||"Samuga")}</span><span class="ad-badge">Ad</span></div>
    <a class="inline-sponsor-frame" href="${escA(sp.link||"https://samugamedia.com")}" target="_blank" rel="noopener sponsored">
      <img src="${escA(sp.img||FALLBACK_IMG)}" alt="${esc(sp.caption||sp.name||"")}" loading="lazy">
    </a>
    ${sp.caption?`<p class="inline-sponsor-copy">${esc(sp.caption)}</p>`:""}
  </section>`;
}

// ── Popular / Trending ────────────────────────────────────────────
function renderPopular(){
  const list=qs("#popularList"); if(!list)return;
  const pop=stories.filter(s=>s.lang===activeLang).slice(0,6);
  if(!pop.length){ list.innerHTML=`<li class="popular-item"><span class="popular-num">—</span><div class="popular-link">${activeLang==="dv"?"ޕޮޕިއުލަރ ޚަބަރެއް ނެތް.":"No popular stories yet."}</div></li>`; return; }
  list.innerHTML=pop.map((s,i)=>{
    const href=s.id&&!s.id.startsWith("fb")?`article.html?id=${encodeURIComponent(s.id)}`:escA(s.url);
    return`<li class="popular-item" dir="${s.lang==="dv"?"rtl":"ltr"}">
      <span class="popular-num">${i+1}</span>
      <div>
        <a class="popular-link" href="${escA(href)}">${esc(s.title)}</a>
        <div class="popular-time">${esc(relTime(s.time))}</div>
      </div>
    </li>`;
  }).join("");
}

function renderTrending(){
  const el=qs("#trendingList"); if(!el)return;
  const cats=["BREAKING","POLITICAL","BUSINESS","LOCAL","WORLD"];
  const counts={};
  stories.filter(s=>s.lang===activeLang).forEach(s=>{ counts[s.category]=(counts[s.category]||0)+1; });
  const sorted=cats.filter(c=>counts[c]).sort((a,b)=>(counts[b]||0)-(counts[a]||0)).slice(0,4);
  if(!sorted.length){ el.style.display="none"; return; }
  const label=activeLang==="dv"?"ޓްރެންޑިންގ":"Trending topics";
  el.innerHTML=`<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-family:var(--font-ui);margin-bottom:6px">${esc(label)}</div>`+
    sorted.map(c=>{
      const color=CAT_COLOR[c]||"var(--cat-local)";
      const cls=CAT_CLASS[c]||"";
      const lbl=activeLang==="dv"?(CAT_DV[c]||c):(CAT_EN[c]||c);
      return`<button class="cat-tag ${cls}" style="--cat-color:${color};cursor:pointer" onclick="filterBycat('${c}')">${esc(lbl)} <span style="opacity:.6;font-size:9px">${counts[c]}</span></button>`;
    }).join(" ");
}

window.filterBycat=function(cat){
  activeCat=cat;
  qsa(".nav-btn").forEach(b=>{ b.classList.remove("active"); if(b.dataset.cat===cat)b.classList.add("active"); });
  renderStories();
  qs("#latest")?.scrollIntoView({behavior:"smooth"});
};

// ── Stats ─────────────────────────────────────────────────────────
function updateStats(){
  const vis=stories.filter(s=>s.lang===activeLang);
  const sc=qs("#storyCount"),lp=qs("#lastPost"),si=qs("#storyCountInline");
  if(sc)sc.textContent=vis.length||"—";
  if(lp)lp.textContent=vis[0]?.time||"Waiting";
  if(si)si.textContent=vis.length?`${vis.length} stories`:"";
}

// ── UI strings ────────────────────────────────────────────────────
function applyUI(){
  const t=UI[activeLang];
  const map={
    "#latestTitle":"latest","#popularTitle":"popular",
    "#tipTitle":"tipTitle","#tipText":"tipText",
    "#communityLink":"community","#footerText":"footer",
    "#statsTitle":"statsTitle",
  };
  for(const[sel,key]of Object.entries(map)){
    const el=qs(sel); if(el)el.textContent=t[key]||"";
  }
  const si=qs("#searchInput"); if(si)si.placeholder=t.search;
  const cs=qs("#chatSubtitle"); if(cs)cs.textContent=t.chatSub;
}

// ── Chat ──────────────────────────────────────────────────────────
function setupChat(){
  const fab=qs("#chatFab"),panel=qs("#chatPanel"),
        close=qs("#chatClose"),form=qs("#chatForm"),
        input=qs("#chatInput"),send=qs("#chatSend"),msgs=qs("#chatMessages");
  if(!fab||!panel)return;

  const open=()=>{ panel.classList.add("open"); fab.setAttribute("aria-expanded","true"); setTimeout(()=>input?.focus(),80); };
  const hide=()=>{ panel.classList.remove("open"); fab.setAttribute("aria-expanded","false"); };
  fab.addEventListener("click",()=>panel.classList.contains("open")?hide():open());
  close?.addEventListener("click",hide);
  qsa("[data-open-chat]").forEach(b=>b.addEventListener("click",open));
  qsa(".quick-prompt-btn").forEach(b=>b.addEventListener("click",()=>{ open(); if(input){input.value=b.dataset.prompt||b.textContent;input.focus();} }));

  form?.addEventListener("submit",async e=>{
    e.preventDefault();
    const msg=input?.value.trim(); if(!msg)return;
    addMsg(msgs,msg,"user"); input.value=""; if(send)send.disabled=true;
    const typing=addMsg(msgs,activeLang==="dv"?"ސަމުގާ އޭއައި ޖަވާބު ހޯދަނީ…":"Samuga AI is thinking…","bot");
    try{
      const r=await fetch(`${API}/api/chat`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,lang:activeLang})});
      const d=await r.json().catch(()=>({}));
      typing.remove(); addMsg(msgs,d.reply||"I could not find a clear answer right now.","bot");
    }catch{ typing.remove(); addMsg(msgs,"Connection issue. Please try again.","bot"); }
    finally{ if(send)send.disabled=false; input?.focus(); }
  });

  input?.addEventListener("input",()=>{ input.style.height="auto"; input.style.height=Math.min(input.scrollHeight,120)+"px"; });
  input?.addEventListener("keydown",e=>{ if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();form?.requestSubmit();} });
}

function addMsg(container,text,cls){
  const d=document.createElement("div");
  d.className=`msg ${cls}`; d.textContent=text;
  container.appendChild(d); container.scrollTop=container.scrollHeight;
  return d;
}

// ── Utilities ─────────────────────────────────────────────────────
function relTime(raw){
  if(!raw||raw==="Live"||raw==="Recent"||raw==="Today")return raw||"";
  try{
    const d=new Date(raw); if(isNaN(d))return raw;
    const mins=Math.floor((Date.now()-d.getTime())/60000);
    if(mins<1)return"just now";
    if(mins<60)return`${mins}m ago`;
    const h=Math.floor(mins/60);
    if(h<24)return`${h}h ago`;
    return`${Math.floor(h/24)}d ago`;
  }catch{return raw;}
}
