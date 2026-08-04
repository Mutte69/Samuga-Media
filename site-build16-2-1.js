"use strict";
const API="https://samuga-news-bot-production.up.railway.app";
const SAMUGA_SITE_BUILD="16.2.1";
const FALLBACK_IMG="assets/SamugaNewsBot_Profile.png";
const SCENIC_COVERS=[
  "assets/maldives-scenic/male-city.jpg",
  "assets/maldives-scenic/island-lagoon.jpg",
  "assets/maldives-scenic/coral-reef.jpg",
  "assets/maldives-scenic/speedboat.jpg",
  "assets/maldives-scenic/lagoon-beach.jpg",
  "assets/maldives-scenic/island-harbour.jpg"
];
function scenicCover(key){let h=2166136261;for(const ch of String(key||"samuga")){h^=ch.charCodeAt(0);h=Math.imul(h,16777619)}return SCENIC_COVERS[(h>>>0)%SCENIC_COVERS.length]}
function brandedCover(id){return `${API}/api/article-cover/${encodeURIComponent(String(id||"article"))}.jpg`}
const SPONSORS=[
  {name:"Samuga Media",caption:"Promote your business with Samuga Media",link:"https://t.me/samugacommunity",img:"assets/sponsor_samuga_media.png"},
  {name:"Etronic Maldives",caption:"Etronic Maldives — electrical solutions",link:"#",img:"assets/sponsor_etronic.png"},
  {name:"Berry Travels",caption:"Berry Travels — speedboat transfers & trips",link:"#",img:"assets/sponsor_berry_travels.png"}
];
const CATS={BREAKING:"Breaking",LOCAL:"Local",POLITICAL:"Politics",BUSINESS:"Business",WORLD:"World",SPORTS:"Sports",LIFESTYLE:"Lifestyle"};
const CATS_DV={BREAKING:"ބްރޭކިންގ",LOCAL:"ލޯކަލް",POLITICAL:"ސިޔާސީ",BUSINESS:"އިޤްތިޞާދީ",WORLD:"ދުނިޔެ",SPORTS:"ކުޅިވަރު",LIFESTYLE:"ލައިފްސްޓައިލް"};
const COLORS={BREAKING:"#f04444",LOCAL:"#20b8f5",POLITICAL:"#9c6ade",BUSINESS:"#23a36d",WORLD:"#22a6b3",SPORTS:"#d99216",LIFESTYLE:"#d84d90"};
const UI={
 en:{latest:"Latest stories",top:"Top stories",search:"Search stories",empty:"No stories found",hint:"Try another category or search term.",read:"Read story",footer:"Maldives, as it happens.",chat:"Maldives news assistant"},
 dv:{latest:"އެންމެ ފަހުގެ ޚަބަރުތައް",top:"މުހިންމު ޚަބަރުތައް",search:"ޚަބަރު ހޯދާ",empty:"ޚަބަރެއް ނުފެނުނު",hint:"އެހެން ކެޓަގަރީއެއް ނުވަތަ ހޯދުމެއް ކޮށްލާ.",read:"ޚަބަރު ކިޔާ",footer:"ދިވެހިރާއްޖޭގެ ޚަބަރު ފަސޭހަކޮށް.",chat:"ދިވެހިރާއްޖޭގެ ޚަބަރު އެސިސްޓެންޓް"}
};
const safeStorage={
  get(key){try{return window.localStorage?.getItem(key)??null}catch{return null}},
  set(key,value){try{window.localStorage?.setItem(key,String(value));return true}catch{return false}}
};
let stories=[],activeLang=safeStorage.get("samuga-lang")==="dv"?"dv":"en",activeCat="all",dynamicSponsors=[],siteSettings={tagline_en:UI.en.footer,tagline_dv:UI.dv.footer,community_url:"https://t.me/samugacommunity",tip_url:"https://t.me/Samuga_Media",show_ai_chat:true,default_theme:"system"};
let storyRefreshTimer=null;
const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const attr=s=>esc(s).replace(/`/g,"&#096;");
const asBool=value=>value===true||value===1||String(value??"").trim().toLowerCase()==="true";
const boolSetting=(value,fallback=true)=>value===undefined||value===null||value===""?fallback:asBool(value);
async function apiFetch(path,options={}){
  const requestOptions={...options};
  const attempts=[path,`${API}${path}`];
  let lastError=null;
  for(const url of attempts){
    try{
      const response=await fetch(url,requestOptions);
      if(response.ok)return response;
      lastError=new Error(`HTTP ${response.status}`);
    }catch(error){lastError=error}
  }
  throw lastError||new Error("API unavailable");
}

document.addEventListener("DOMContentLoaded",async()=>{
  try{
    const requestedCat=new URLSearchParams(location.search).get("cat");if(requestedCat&&["all","BREAKING","LOCAL","POLITICAL","BUSINESS","WORLD","SPORTS","LIFESTYLE"].includes(requestedCat))activeCat=requestedCat;
    setupTheme();setupMenu();setupLanguage();setupCategories();setupSearch();setupChat();
    const year=$("#footerYear");if(year)year.textContent=new Date().getFullYear();
    applyLanguage();
    await Promise.allSettled([loadStories(),loadBanner(),loadSiteSettings()]);
    applySiteSettings();applyLanguage();renderAll();
    storyRefreshTimer=setInterval(refreshStories,60000);
    document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")refreshStories()});
  }catch(error){
    console.error("[SAMUGA SITE] startup failed",error);
    try{applyLanguage();renderAll()}catch{}
  }
});


async function loadSiteSettings(){
  try{const r=await apiFetch("/api/site-settings",{cache:"no-store"});if(!r.ok)return;const d=await r.json();if(d?.settings)siteSettings={...siteSettings,...d.settings}}catch{}
}
function applySiteSettings(){
  const community=siteSettings.community_url||"https://t.me/samugacommunity",tip=siteSettings.tip_url||"https://t.me/Samuga_Media";
  $("#headerCommunity")?.setAttribute("href",community);$("#footerCommunity")?.setAttribute("href",community);$("#footerTip")?.setAttribute("href",tip);
  if(!safeStorage.get("samuga-theme")&&["light","dark"].includes(siteSettings.default_theme)){document.documentElement.dataset.theme=siteSettings.default_theme}
}

function setupTheme(){
  $("#themeToggle")?.addEventListener("click",()=>{const next=document.documentElement.dataset.theme==="light"?"dark":"light";document.documentElement.dataset.theme=next;safeStorage.set("samuga-theme",next)});
}
function setupMenu(){/* V3 drawer is bound by samuga-v3-shell.js. */}
function setupLanguage(){
  $$(".lang-btn").forEach(b=>{
    if(b.dataset.v3LangBound==="true")return;
    b.dataset.v3LangBound="true";
    b.addEventListener("click",()=>{activeLang=b.dataset.lang||"en";safeStorage.set("samuga-lang",activeLang);applyLanguage();renderAll()});
  });
}
function applyLanguage(){
  const dv=activeLang==="dv";document.documentElement.lang=dv?"dv":"en";document.documentElement.dir="ltr";document.body.classList.toggle("lang-dv",dv);document.body.classList.toggle("lang-en",!dv);
  $$(".lang-btn").forEach(b=>{const on=b.dataset.lang===activeLang;b.classList.toggle("active",on);b.setAttribute("aria-pressed",String(on))});
  const t=UI[activeLang];if($("#latestTitle"))$("#latestTitle").textContent=t.latest;if($("#topStoriesTitle"))$("#topStoriesTitle").textContent=t.top;if($("#searchInput"))$("#searchInput").placeholder=t.search;if($("#footerText"))$("#footerText").textContent=dv?(siteSettings.tagline_dv||t.footer):(siteSettings.tagline_en||t.footer);if($("#chatSubtitle"))$("#chatSubtitle").textContent=t.chat;
  document.dispatchEvent(new CustomEvent("samuga:languagechange",{detail:{lang:activeLang}}));
}
function setupCategories(){
  $$(".nav-btn").forEach(b=>b.addEventListener("click",()=>{$$(".nav-btn").forEach(x=>x.classList.remove("active"));b.classList.add("active");activeCat=b.dataset.cat||"all";renderCards();$("#primaryNav")?.classList.remove("open");document.dispatchEvent(new CustomEvent("samuga:categorychange",{detail:{category:activeCat}}))}));
  const initial=$(".nav-btn[data-cat=\""+activeCat+"\"]");if(initial){$$(".nav-btn").forEach(x=>x.classList.remove("active"));initial.classList.add("active")}
}
function setupSearch(){$("#searchInput")?.addEventListener("input",renderCards)}

async function loadBanner(){
  try{const r=await apiFetch("/api/ads?placement=feed",{cache:"no-store"});const d=await r.json();if(Array.isArray(d?.ads))dynamicSponsors=d.ads.map(a=>({name:a.name,caption:a.caption,link:a.destination_url||"#",img:a.image_url,mobile_img:a.mobile_image_url,fit_mode:a.fit_mode||"contain"})).filter(a=>a.img)}catch{}
  if(dynamicSponsors.length)return;
  try{const r=await apiFetch("/api/banner",{cache:"no-store"});const d=await r.json();if(d?.active&&d?.image_url)dynamicSponsors=[{name:d.name||"Sponsor",caption:d.text||"Sponsored",link:d.link||"#",img:d.image_url,fit_mode:"contain"}]}catch{}
}
async function loadStories(){
  try{const r=await apiFetch("/api/stories",{cache:"no-store"});if(!r.ok)throw new Error("stories");const d=await r.json();stories=Array.isArray(d)?d.map(normalizeStory).filter(Boolean):[];return true}
  catch(e){console.warn(e);return false}
}
async function refreshStories(){
  const ok=await loadStories();
  if(ok)renderAll();
}
function normalizeStory(s){
  if(!s?.title)return null;const text=`${s.title||""} ${s.summary||""}`;const lang=(s.lang==="dv"||/[ހ-޿]/.test(text))?"dv":"en";
  const storyId=String(s.id||"");const fallback=brandedCover(storyId);const outageFallback=scenicCover(`${storyId}|${s.title||""}`);
  return{id:storyId,title:String(s.title||"").trim(),summary:String(s.summary||"").trim(),category:normalizeCat(s.category,text),source:"Samuga Media",time:s.published_at||s.time||"",lang,cover_image:s.cover_image||fallback,fallback_cover:fallback,outage_fallback:outageFallback,cover_video:s.cover_video||null,video_poster:s.video_poster||s.cover_image||fallback,author:s.author||null,reading_time:s.reading_time||null,featured:asBool(s.featured),breaking:asBool(s.breaking)||normalizeCat(s.category,text)==="BREAKING",slug:s.slug||""};
}
function normalizeCat(cat,text=""){const raw=String(cat||"LOCAL").toUpperCase();if(["BREAKING","LOCAL","POLITICAL","BUSINESS","WORLD","SPORTS","LIFESTYLE"].includes(raw))return raw;if(raw==="POLITICS")return"POLITICAL";if(/breaking|killed|dead|fire|crash|missing|emergency/i.test(text))return"BREAKING";return"LOCAL"}
function visibleStories(){const q=$("#searchInput")?.value.toLowerCase().trim()||"";return stories.filter(s=>s.lang===activeLang&&(activeCat==="all"||s.category===activeCat)&&(!q||`${s.title} ${s.summary}`.toLowerCase().includes(q)))}
function articleHref(s){return s.id?`/article?id=${encodeURIComponent(s.id)}`:"#"}
function renderAll(){renderStrip();renderFeatured();renderPopular();renderCards()}
function storyAgeMs(story){
  const raw=story?.time||"";const stamp=new Date(raw).getTime();
  return Number.isFinite(stamp)?Math.max(0,Date.now()-stamp):Number.POSITIVE_INFINITY;
}
function renderStrip(){
  const bar=$("#newsStrip"),labelEl=$("#stripLabel"),windowEl=$("#stripWindow"),track=$("#stripTrack");
  if(!bar||!labelEl||!windowEl||!track)return;
  const pool=stories
    .filter(s=>s.lang===activeLang&&storyAgeMs(s)<=4*60*60*1000)
    .sort((a,b)=>new Date(b.time||0)-new Date(a.time||0))
    .slice(0,8);
  if(!pool.length){bar.hidden=true;bar.setAttribute("aria-hidden","true");track.innerHTML="";return}

  const hasFreshBreaking=pool.some(story=>(story.breaking||story.category==="BREAKING")&&storyAgeMs(story)<=30*60*1000);
  const label=hasFreshBreaking
    ?(activeLang==="dv"?"ބްރޭކިންގ":"Breaking")
    :(activeLang==="dv"?"ލައިވް އަޕްޑޭޓް":"Live update");
  bar.hidden=false;bar.removeAttribute("aria-hidden");bar.classList.toggle("is-breaking",hasFreshBreaking);
  labelEl.textContent=label;

  const itemDirection=activeLang==="dv"?"rtl":"ltr";
  const items=pool.map(story=>{
    const isBreaking=(story.breaking||story.category==="BREAKING")&&storyAgeMs(story)<=30*60*1000;
    return `<a class="news-strip-item${isBreaking?" is-item-breaking":""}" dir="${itemDirection}" href="${attr(articleHref(story))}"><span class="news-strip-headline">${esc(story.title)}</span><span class="news-strip-time">${esc(relativeTime(story.time))}</span></a><span class="news-strip-separator" aria-hidden="true">•</span>`;
  }).join("");
  track.classList.toggle("ticker-right-to-left",activeLang!=="dv");
  track.classList.toggle("ticker-left-to-right",activeLang==="dv");
  track.innerHTML=`<div class="news-strip-group">${items}</div><div class="news-strip-group" aria-hidden="true">${items}</div>`;

  requestAnimationFrame(()=>{
    const firstGroup=track.querySelector(".news-strip-group");
    if(!firstGroup)return;
    const pixels=Math.max(firstGroup.scrollWidth,windowEl.clientWidth);
    const duration=Math.min(110,Math.max(28,pixels/70));
    track.style.setProperty("--ticker-duration",`${duration.toFixed(1)}s`);
  });
}
function renderFeatured(){
  const pool=stories.filter(s=>s.lang===activeLang);const s=pool.find(x=>x.featured)||pool[0];if(!s)return;
  const leadSection=$(".lead-section");if(leadSection&&leadSection.dataset.settingsHidden!=="true")leadSection.hidden=false;
  const shell=$("#featuredStory");shell?.classList.remove("lead-story-no-media");
  $("#featuredCategory").textContent=(activeLang==="dv"?CATS_DV:CATS)[s.category]||s.category;$("#featuredTime").textContent=relativeTime(s.time);$("#featuredHeadline").textContent=s.title;$("#featuredSummary").textContent=s.summary||"";$("#featuredReadBtn").href=articleHref(s);$("#featuredReadBtn").innerHTML=`${esc(UI[activeLang].read)} <span>→</span>`;$("#featuredMediaLink").href=articleHref(s);
  const media=$("#featuredMedia");media.className="";const mediaLink=$("#featuredMediaLink");if(mediaLink)mediaLink.style.display="";
  if(s.cover_video){media.innerHTML=s.video_poster?`<img src="${attr(s.video_poster)}" alt="" loading="eager"><span class="video-badge">▶ Video</span>`:`<div class="video-poster-fallback" aria-hidden="true">▶</div><span class="video-badge">▶ Video</span>`}
  else{const cover=s.cover_image||s.fallback_cover||brandedCover(s.id);media.innerHTML=`<img src="${attr(cover)}" alt="" loading="eager" onerror="this.onerror=null;this.src='${attr(s.outage_fallback||scenicCover(`${s.id}|${s.title}`))}'">`}
}
function renderPopular(){const list=$("#popularList"),pool=stories.filter(s=>s.lang===activeLang).slice(0,5);$("#storyCountInline").textContent=pool.length?`${stories.filter(s=>s.lang===activeLang).length} stories`:"";if(!pool.length){list.innerHTML=`<li class="top-item"><span>—</span><div>${esc(UI[activeLang].empty)}</div></li>`;return}list.innerHTML=pool.map((s,i)=>`<li class="top-item"><span class="top-number">${String(i+1).padStart(2,"0")}</span><div><a href="${attr(articleHref(s))}">${esc(s.title)}</a><div class="top-meta">${esc((activeLang==="dv"?CATS_DV:CATS)[s.category]||s.category)} · ${esc(relativeTime(s.time))}</div></div></li>`).join("")}
function renderCards(){
  const grid=$("#storyGrid"),pool=visibleStories();if(!pool.length){grid.innerHTML=`<div class="empty-state"><strong>${esc(UI[activeLang].empty)}</strong><span>${esc(UI[activeLang].hint)}</span></div>`;return}
  const ads=dynamicSponsors.length?[...dynamicSponsors,...SPONSORS]:SPONSORS;const html=[];pool.forEach((s,i)=>{html.push(cardHTML(s));if((i+1)%3===0&&ads.length)html.push(adHTML(ads[Math.floor(i/3)%ads.length]))});grid.innerHTML=html.join("")
}
function cardHTML(s){
  const cat=(activeLang==="dv"?CATS_DV:CATS)[s.category]||s.category;
  const fallback=s.fallback_cover||brandedCover(s.id);const outage=s.outage_fallback||scenicCover(`${s.id}|${s.title}`);const cover=s.cover_image||fallback;
  const media=s.cover_video?`<div class="card-media"><img src="${attr(s.video_poster||fallback)}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${attr(outage)}'"><span class="video-badge">▶ Video</span></div>`:`<div class="card-media"><img src="${attr(cover)}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${attr(outage)}'"></div>`;
  const noMedia="";
  const author=s.author?.name||"Samuga AI";const avatar=s.author?.photo?`<img src="${attr(s.author.photo)}" alt="${esc(author)}" loading="lazy">`:`<span class="author-fallback">S</span>`;
  return`<a class="story-card${noMedia}" style="--cat:${COLORS[s.category]||COLORS.LOCAL}" role="listitem" href="${attr(articleHref(s))}" aria-label="${attr(s.title)}" dir="${s.lang==="dv"?"rtl":"ltr"}">${media}<div class="card-body"><div class="card-kicker"><strong>${esc(cat)}</strong><span>${esc(relativeTime(s.time))}</span></div><h3 class="card-title">${esc(s.title)}</h3>${s.summary?`<p class="card-summary">${esc(s.summary)}</p>`:""}<div class="card-footer"><div class="author-chip" dir="ltr">${avatar}<span>${esc(author)}</span></div><span class="read-time">${s.reading_time?`${esc(s.reading_time)} min read`:"Samuga Media"}</span></div></div></a>`
}
function adHTML(ad){const mobile=ad.mobile_img?`<source media="(max-width:760px)" srcset="${attr(ad.mobile_img)}">`:"";const fit=ad.fit_mode==="cover"?"cover":"contain";return`<aside class="inline-ad" aria-label="Advertisement" dir="ltr"><div class="ad-head"><span>Sponsored · ${esc(ad.name||"Samuga Media")}</span><span>Ad</span></div><a class="ad-media" href="${attr(ad.link||"#")}" target="_blank" rel="noopener sponsored"><picture>${mobile}<img style="object-fit:${fit}" src="${attr(ad.img||FALLBACK_IMG)}" alt="${esc(ad.caption||ad.name||"Advertisement")}" loading="lazy"></picture></a>${ad.caption?`<p class="ad-caption">${esc(ad.caption)}</p>`:""}</aside>`}
function relativeTime(raw){if(!raw)return"Recent";const d=new Date(raw);if(Number.isNaN(d.getTime()))return String(raw);const mins=Math.max(0,Math.floor((Date.now()-d.getTime())/60000));if(mins<1)return"Just now";if(mins<60)return`${mins}m ago`;const h=Math.floor(mins/60);if(h<24)return`${h}h ago`;const days=Math.floor(h/24);return days<7?`${days}d ago`:d.toLocaleDateString(activeLang==="dv"?"dv-MV":"en-GB",{day:"numeric",month:"short"})}

function setupChat(){/* Shared chat is bound once by samuga-v3-shell-16-2-1.js. */}

function addMessage(box,text,type){const d=document.createElement("div");d.className=`msg ${type}`;d.textContent=text;box.appendChild(d);box.scrollTop=box.scrollHeight;return d}
