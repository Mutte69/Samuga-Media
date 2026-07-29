"use strict";
const API="https://samuga-news-bot-production.up.railway.app";
const SAMUGA_SITE_BUILD="15.9.7";
const FALLBACK_IMG="assets/SamugaNewsBot_Profile.png";
const SPONSORS=[
  {name:"Samuga Media",caption:"Promote your business with Samuga Media",link:"https://t.me/samugacommunity",img:"assets/sponsor_samuga_media.png"},
  {name:"Etronic Maldives",caption:"Etronic Maldives — electrical solutions",link:"#",img:"assets/sponsor_etronic.png"},
  {name:"Berry Travels",caption:"Berry Travels — speedboat transfers & trips",link:"#",img:"assets/sponsor_berry_travels.png"}
];
const CATS={BREAKING:"Breaking",LOCAL:"Local",POLITICAL:"Politics",BUSINESS:"Business",WORLD:"World",SPORTS:"Sports",LIFESTYLE:"Lifestyle"};
const CATS_DV={BREAKING:"ބްރޭކިންގ",LOCAL:"ލޯކަލް",POLITICAL:"ސިޔާސީ",BUSINESS:"އިޤްތިޞާދީ",WORLD:"ދުނިޔެ",SPORTS:"ކުޅިވަރު",LIFESTYLE:"ލައިފްސްޓައިލް"};
const COLORS={BREAKING:"#f04444",LOCAL:"#20b8f5",POLITICAL:"#9c6ade",BUSINESS:"#23a36d",WORLD:"#22a6b3",SPORTS:"#d99216",LIFESTYLE:"#d84d90"};
const UI={
 en:{latest:"Latest stories",top:"Top stories",search:"Search stories",empty:"No stories found",hint:"Try another category or search term.",read:"Read story",footer:"Maldives news made simple.",chat:"Maldives news assistant"},
 dv:{latest:"އެންމެ ފަހުގެ ޚަބަރުތައް",top:"މުހިންމު ޚަބަރުތައް",search:"ޚަބަރު ހޯދާ",empty:"ޚަބަރެއް ނުފެނުނު",hint:"އެހެން ކެޓަގަރީއެއް ނުވަތަ ހޯދުމެއް ކޮށްލާ.",read:"ޚަބަރު ކިޔާ",footer:"ދިވެހިރާއްޖޭގެ ޚަބަރު ފަސޭހަކޮށް.",chat:"ދިވެހިރާއްޖޭގެ ޚަބަރު އެސިސްޓެންޓް"}
};
let stories=[],activeLang=localStorage.getItem("samuga-lang")||"en",activeCat="all",dynamicSponsors=[],siteSettings={tagline_en:UI.en.footer,tagline_dv:UI.dv.footer,community_url:"https://t.me/samugacommunity",tip_url:"https://t.me/Samuga_Media",show_ai_chat:true,default_theme:"system"};
let stripRotationTimer=null,stripRotationIndex=0,storyRefreshTimer=null;
const $=s=>document.querySelector(s),$$=s=>document.querySelectorAll(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const attr=s=>esc(s).replace(/`/g,"&#096;");
const asBool=value=>value===true||value===1||String(value??"").trim().toLowerCase()==="true";

document.addEventListener("DOMContentLoaded",async()=>{
  setupTheme();setupMenu();setupLanguage();setupCategories();setupSearch();setupChat();
  $("#footerYear").textContent=new Date().getFullYear();
  await Promise.all([loadStories(),loadBanner(),loadSiteSettings()]);
  applySiteSettings();applyLanguage();renderAll();
  storyRefreshTimer=setInterval(refreshStories,60000);
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")refreshStories()});
});


async function loadSiteSettings(){
  try{const r=await fetch(`${API}/api/site-settings`,{cache:"no-store"});if(!r.ok)return;const d=await r.json();if(d?.settings)siteSettings={...siteSettings,...d.settings}}catch{}
}
function applySiteSettings(){
  const community=siteSettings.community_url||"https://t.me/samugacommunity",tip=siteSettings.tip_url||"https://t.me/Samuga_Media";
  $("#headerCommunity")?.setAttribute("href",community);$("#footerCommunity")?.setAttribute("href",community);$("#footerTip")?.setAttribute("href",tip);
  const showAi=siteSettings.show_ai_chat!==false;$("#chatFab").hidden=!showAi;$("#chatPanel").hidden=!showAi;
  if(!localStorage.getItem("samuga-theme")&&["light","dark"].includes(siteSettings.default_theme)){document.documentElement.dataset.theme=siteSettings.default_theme}
}

function setupTheme(){
  $("#themeToggle")?.addEventListener("click",()=>{const next=document.documentElement.dataset.theme==="light"?"dark":"light";document.documentElement.dataset.theme=next;localStorage.setItem("samuga-theme",next)});
}
function setupMenu(){const b=$("#menuBtn"),n=$("#primaryNav");b?.addEventListener("click",()=>{const open=n.classList.toggle("open");b.setAttribute("aria-expanded",String(open))})}
function setupLanguage(){
  $$(".lang-btn").forEach(b=>b.addEventListener("click",()=>{activeLang=b.dataset.lang||"en";localStorage.setItem("samuga-lang",activeLang);applyLanguage();renderAll()}));
}
function applyLanguage(){
  const dv=activeLang==="dv";document.documentElement.lang=dv?"dv":"en";document.documentElement.dir=dv?"rtl":"ltr";document.body.classList.toggle("lang-dv",dv);
  $$(".lang-btn").forEach(b=>{const on=b.dataset.lang===activeLang;b.classList.toggle("active",on);b.setAttribute("aria-pressed",String(on))});
  const t=UI[activeLang];$("#latestTitle").textContent=t.latest;$("#topStoriesTitle").textContent=t.top;$("#searchInput").placeholder=t.search;$("#footerText").textContent=dv?(siteSettings.tagline_dv||t.footer):(siteSettings.tagline_en||t.footer);$("#chatSubtitle").textContent=t.chat;
}
function setupCategories(){
  $$(".nav-btn").forEach(b=>b.addEventListener("click",()=>{$$(".nav-btn").forEach(x=>x.classList.remove("active"));b.classList.add("active");activeCat=b.dataset.cat||"all";renderCards();$("#primaryNav")?.classList.remove("open")}));
}
function setupSearch(){$("#searchInput")?.addEventListener("input",renderCards)}

async function loadBanner(){
  try{const r=await fetch(`${API}/api/ads?placement=feed`,{cache:"no-store"});const d=await r.json();if(Array.isArray(d?.ads))dynamicSponsors=d.ads.map(a=>({name:a.name,caption:a.caption,link:a.destination_url||"#",img:a.image_url,mobile_img:a.mobile_image_url,fit_mode:a.fit_mode||"contain"})).filter(a=>a.img)}catch{}
  if(dynamicSponsors.length)return;
  try{const r=await fetch(`${API}/api/banner`,{cache:"no-store"});const d=await r.json();if(d?.active&&d?.image_url)dynamicSponsors=[{name:d.name||"Sponsor",caption:d.text||"Sponsored",link:d.link||"#",img:d.image_url,fit_mode:"contain"}]}catch{}
}
async function loadStories(){
  try{const r=await fetch(`${API}/api/stories`,{cache:"no-store"});if(!r.ok)throw new Error("stories");const d=await r.json();stories=Array.isArray(d)?d.map(normalizeStory).filter(Boolean):[];return true}
  catch(e){console.warn(e);return false}
}
async function refreshStories(){
  const ok=await loadStories();
  if(ok)renderAll();
}
function normalizeStory(s){
  if(!s?.title)return null;const text=`${s.title||""} ${s.summary||""}`;const lang=(s.lang==="dv"||/[ހ-޿]/.test(text))?"dv":"en";
  return{id:String(s.id||""),title:String(s.title||"").trim(),summary:String(s.summary||"").trim(),category:normalizeCat(s.category,text),source:"Samuga Media",time:s.published_at||s.time||"",lang,cover_image:s.cover_image||null,cover_video:s.cover_video||null,video_poster:s.video_poster||s.cover_image||null,author:s.author||null,reading_time:s.reading_time||null,featured:asBool(s.featured),breaking:asBool(s.breaking)||normalizeCat(s.category,text)==="BREAKING",slug:s.slug||""};
}
function normalizeCat(cat,text=""){const raw=String(cat||"LOCAL").toUpperCase();if(["BREAKING","LOCAL","POLITICAL","BUSINESS","WORLD","SPORTS","LIFESTYLE"].includes(raw))return raw;if(raw==="POLITICS")return"POLITICAL";if(/breaking|killed|dead|fire|crash|missing|emergency/i.test(text))return"BREAKING";return"LOCAL"}
function visibleStories(){const q=$("#searchInput")?.value.toLowerCase().trim()||"";return stories.filter(s=>s.lang===activeLang&&(activeCat==="all"||s.category===activeCat)&&(!q||`${s.title} ${s.summary}`.toLowerCase().includes(q)))}
function articleHref(s){return s.id?`/article?id=${encodeURIComponent(s.id)}`:"#"}
function renderAll(){renderStrip();renderFeatured();renderPopular();renderCards()}
function storyAgeMs(story){
  const raw=story?.time||"";const stamp=new Date(raw).getTime();
  return Number.isFinite(stamp)?Math.max(0,Date.now()-stamp):Number.POSITIVE_INFINITY;
}
function setStripStory(story,label,isBreaking=false){
  const bar=$("#newsStrip"),labelEl=$("#stripLabel"),link=$("#stripLink"),time=$("#stripTime");
  if(!bar||!story)return;
  bar.hidden=false;bar.removeAttribute("aria-hidden");bar.classList.toggle("is-breaking",Boolean(isBreaking));
  if(labelEl)labelEl.textContent=label;
  link.textContent=story.title;link.href=articleHref(story);time.textContent=relativeTime(story.time);
}
function renderStrip(){
  clearInterval(stripRotationTimer);stripRotationTimer=null;stripRotationIndex=0;
  const pool=stories.filter(s=>s.lang===activeLang).sort((a,b)=>new Date(b.time||0)-new Date(a.time||0));
  const bar=$("#newsStrip");
  if(!pool.length){bar.hidden=true;bar.setAttribute("aria-hidden","true");return}
  const livePool=pool.slice(0,Math.min(8,pool.length));
  const showCurrent=()=>{
    const story=livePool[stripRotationIndex];
    const isBreaking=Boolean((story.breaking||story.category==="BREAKING")&&storyAgeMs(story)<=6*60*60*1000);
    const label=isBreaking?(activeLang==="dv"?"ބްރޭކިންގ":"Breaking"):(activeLang==="dv"?"ލައިވް އަޕްޑޭޓް":"Live update");
    setStripStory(story,label,isBreaking);
  };
  showCurrent();
  if(livePool.length>1){stripRotationTimer=setInterval(()=>{stripRotationIndex=(stripRotationIndex+1)%livePool.length;showCurrent()},6000)}
}
function renderFeatured(){
  const pool=stories.filter(s=>s.lang===activeLang);const s=pool.find(x=>x.featured)||pool[0];if(!s)return;
  const shell=$("#featuredStory");shell?.classList.remove("lead-story-no-media");
  $("#featuredCategory").textContent=(activeLang==="dv"?CATS_DV:CATS)[s.category]||s.category;$("#featuredTime").textContent=relativeTime(s.time);$("#featuredHeadline").textContent=s.title;$("#featuredSummary").textContent=s.summary||"";$("#featuredReadBtn").href=articleHref(s);$("#featuredReadBtn").innerHTML=`${esc(UI[activeLang].read)} <span>→</span>`;$("#featuredMediaLink").href=articleHref(s);
  const media=$("#featuredMedia");media.className="";const mediaLink=$("#featuredMediaLink");if(mediaLink)mediaLink.style.display="";
  if(s.cover_video){media.innerHTML=s.video_poster?`<img src="${attr(s.video_poster)}" alt="" loading="eager"><span class="video-badge">▶ Video</span>`:`<div class="video-poster-fallback" aria-hidden="true">▶</div><span class="video-badge">▶ Video</span>`}
  else if(s.cover_image){media.innerHTML=`<img src="${attr(s.cover_image)}" alt="" loading="eager" onerror="this.onerror=null;this.closest('.lead-media').style.display='none';document.querySelector('#featuredStory')?.classList.add('lead-story-no-media')">`}
  else{media.innerHTML="";media.closest('.lead-media').style.display="none";shell?.classList.add("lead-story-no-media")}
}
function renderPopular(){const list=$("#popularList"),pool=stories.filter(s=>s.lang===activeLang).slice(0,5);$("#storyCountInline").textContent=pool.length?`${stories.filter(s=>s.lang===activeLang).length} stories`:"";if(!pool.length){list.innerHTML=`<li class="top-item"><span>—</span><div>${esc(UI[activeLang].empty)}</div></li>`;return}list.innerHTML=pool.map((s,i)=>`<li class="top-item"><span class="top-number">${String(i+1).padStart(2,"0")}</span><div><a href="${attr(articleHref(s))}">${esc(s.title)}</a><div class="top-meta">${esc((activeLang==="dv"?CATS_DV:CATS)[s.category]||s.category)} · ${esc(relativeTime(s.time))}</div></div></li>`).join("")}
function renderCards(){
  const grid=$("#storyGrid"),pool=visibleStories();if(!pool.length){grid.innerHTML=`<div class="empty-state"><strong>${esc(UI[activeLang].empty)}</strong><span>${esc(UI[activeLang].hint)}</span></div>`;return}
  const ads=dynamicSponsors.length?[...dynamicSponsors,...SPONSORS]:SPONSORS;const html=[];pool.forEach((s,i)=>{html.push(cardHTML(s));if((i+1)%6===0&&ads.length)html.push(adHTML(ads[Math.floor(i/6)%ads.length]))});grid.innerHTML=html.join("")
}
function cardHTML(s){
  const cat=(activeLang==="dv"?CATS_DV:CATS)[s.category]||s.category;
  const media=s.cover_video?`<div class="card-media">${s.video_poster?`<img src="${attr(s.video_poster)}" alt="" loading="lazy" onerror="this.closest('.card-media')?.remove()">`:`<div class="video-poster-fallback" aria-hidden="true">▶</div>`}<span class="video-badge">▶ Video</span></div>`:s.cover_image?`<div class="card-media"><img src="${attr(s.cover_image)}" alt="" loading="lazy" onerror="this.closest('.card-media')?.remove()"></div>`:"";
  const noMedia=media?"":" no-cover";
  const author=s.author?.name||"Samuga AI";const avatar=s.author?.photo?`<img src="${attr(s.author.photo)}" alt="${esc(author)}" loading="lazy">`:`<span class="author-fallback">S</span>`;
  return`<a class="story-card${noMedia}" style="--cat:${COLORS[s.category]||COLORS.LOCAL}" role="listitem" href="${attr(articleHref(s))}" aria-label="${attr(s.title)}" dir="${s.lang==="dv"?"rtl":"ltr"}">${media}<div class="card-body"><div class="card-kicker"><strong>${esc(cat)}</strong><span>${esc(relativeTime(s.time))}</span></div><h3 class="card-title">${esc(s.title)}</h3>${s.summary?`<p class="card-summary">${esc(s.summary)}</p>`:""}<div class="card-footer"><div class="author-chip" dir="ltr">${avatar}<span>${esc(author)}</span></div><span class="read-time">${s.reading_time?`${esc(s.reading_time)} min read`:"Samuga Media"}</span></div></div></a>`
}
function adHTML(ad){const mobile=ad.mobile_img?`<source media="(max-width:760px)" srcset="${attr(ad.mobile_img)}">`:"";const fit=ad.fit_mode==="cover"?"cover":"contain";return`<aside class="inline-ad" aria-label="Advertisement" dir="ltr"><div class="ad-head"><span>Sponsored · ${esc(ad.name||"Samuga Media")}</span><span>Ad</span></div><a class="ad-media" href="${attr(ad.link||"#")}" target="_blank" rel="noopener sponsored"><picture>${mobile}<img style="object-fit:${fit}" src="${attr(ad.img||FALLBACK_IMG)}" alt="${esc(ad.caption||ad.name||"Advertisement")}" loading="lazy"></picture></a>${ad.caption?`<p class="ad-caption">${esc(ad.caption)}</p>`:""}</aside>`}
function relativeTime(raw){if(!raw)return"Recent";const d=new Date(raw);if(Number.isNaN(d.getTime()))return String(raw);const mins=Math.max(0,Math.floor((Date.now()-d.getTime())/60000));if(mins<1)return"Just now";if(mins<60)return`${mins}m ago`;const h=Math.floor(mins/60);if(h<24)return`${h}h ago`;const days=Math.floor(h/24);return days<7?`${days}d ago`:d.toLocaleDateString(activeLang==="dv"?"dv-MV":"en-GB",{day:"numeric",month:"short"})}

function setupChat(){
  const fab=$("#chatFab"),panel=$("#chatPanel"),close=$("#chatClose"),form=$("#chatForm"),input=$("#chatInput"),send=$("#chatSend"),msgs=$("#chatMessages");
  if(!fab||!panel)return;
  panel.dir="ltr";
  if(form)form.dir="ltr";
  const isMobile=()=>window.matchMedia("(max-width:760px)").matches;
  const baseViewportHeight=()=>Math.max(window.innerHeight||0,document.documentElement.clientHeight||0);
  const fitMobileViewport=()=>{
    if(!panel.classList.contains("open")||!isMobile())return;
    const vv=window.visualViewport;
    const viewportLeft=Math.round(vv?.offsetLeft||0);
    const viewportTop=Math.round(vv?.offsetTop||0);
    const viewportWidth=Math.max(280,Math.round(vv?.width||window.innerWidth));
    const viewportHeight=Math.max(320,Math.round(vv?.height||window.innerHeight));
    const keyboardOpen=viewportHeight < baseViewportHeight()*0.78;
    const sideGap=8;
    const verticalGap=8;
    const panelHeight=keyboardOpen
      ? Math.max(300,viewportHeight-(verticalGap*2))
      : Math.min(620,Math.max(400,viewportHeight-24));
    const panelTop=keyboardOpen
      ? viewportTop+verticalGap
      : viewportTop+Math.max(verticalGap,viewportHeight-panelHeight-verticalGap);
    panel.style.left=`${viewportLeft+sideGap}px`;
    panel.style.right="auto";
    panel.style.width=`${Math.max(264,viewportWidth-(sideGap*2))}px`;
    panel.style.top=`${panelTop}px`;
    panel.style.height=`${panelHeight}px`;
    panel.style.bottom="auto";
    requestAnimationFrame(()=>{msgs.scrollTop=msgs.scrollHeight});
  };
  const resetViewport=()=>{
    ["left","right","width","top","height","bottom"].forEach(name=>panel.style.removeProperty(name));
  };
  const open=()=>{
    panel.hidden=false;
    panel.classList.add("open");
    panel.setAttribute("aria-hidden","false");
    fab.setAttribute("aria-expanded","true");
    document.body.classList.add("chat-open");
    fitMobileViewport();
    if(!isMobile())setTimeout(()=>input?.focus(),30);
  };
  const hide=()=>{
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden","true");
    fab.setAttribute("aria-expanded","false");
    document.body.classList.remove("chat-open");
    input?.blur();
    resetViewport();
  };
  fab.addEventListener("click",()=>panel.classList.contains("open")?hide():open());
  close?.addEventListener("click",hide);
  window.visualViewport?.addEventListener("resize",fitMobileViewport);
  window.visualViewport?.addEventListener("scroll",fitMobileViewport);
  window.addEventListener("resize",fitMobileViewport);
  window.addEventListener("orientationchange",()=>setTimeout(fitMobileViewport,160));
  document.addEventListener("keydown",event=>{if(event.key==="Escape"&&panel.classList.contains("open"))hide()});
  input?.addEventListener("focus",()=>setTimeout(fitMobileViewport,120));
  input?.addEventListener("blur",()=>setTimeout(fitMobileViewport,120));
  form?.addEventListener("submit",async event=>{
    event.preventDefault();
    const message=input.value.trim();
    if(!message)return;
    addMessage(msgs,message,"user");
    input.value="";
    send.disabled=true;
    fitMobileViewport();
    const wait=addMessage(msgs,"Samuga AI is checking…","bot");
    try{
      const response=await fetch(`${API}/api/chat`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message,lang:activeLang})});
      const data=await response.json();
      wait.remove();
      addMessage(msgs,data.reply||"I could not find an answer right now.","bot");
    }catch{
      wait.remove();
      addMessage(msgs,"Connection issue. Please try again.","bot");
    }finally{
      send.disabled=false;
      fitMobileViewport();
      if(!isMobile())input.focus();
    }
  });
}
function addMessage(box,text,type){const d=document.createElement("div");d.className=`msg ${type}`;d.textContent=text;box.appendChild(d);box.scrollTop=box.scrollHeight;return d}
