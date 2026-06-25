const BOT_API_BASE = ""; // Example: "https://samuga-news-bot.up.railway.app"
const fallbackStories = [
  { title:"Samuga AI newsroom is now monitoring Maldives news live", summary:"The system tracks local updates, breaking incidents, politics, economy and public-interest stories from multiple sources.", category:"Breaking", source:"Samuga Media", time:"Live", url:"#" },
  { title:"AI-assisted publishing helps Samuga reduce social media posting limits", summary:"Stories can be published through the website while Telegram and social platforms continue operating with controlled posting.", category:"Community", source:"Samuga AI", time:"Today", url:"#" },
  { title:"Politics, economy and public-interest stories receive higher priority", summary:"The newsroom system is designed to prioritize issues that affect Maldivians directly.", category:"Politics", source:"Samuga AI", time:"Today", url:"#" },
  { title:"Weather, prayer times and alerts will be part of Samuga daily updates", summary:"The bot can generate weather cards and public alerts for Telegram and the Samuga website.", category:"Community", source:"Samuga AI", time:"Today", url:"#" }
];
let stories = [];
let activeCategory = "all";
const qs = (s)=>document.querySelector(s);
const qsa = (s)=>document.querySelectorAll(s);
const storyGrid = qs("#storyGrid"), popularList = qs("#popularList"), tickerTrack = qs("#tickerTrack"), storyCount = qs("#storyCount"), lastPost = qs("#lastPost"), searchInput = qs("#searchInput"), menuButton = qs("#menuButton"), primaryNav = qs("#primaryNav");
document.addEventListener("DOMContentLoaded", init);
async function init(){
  qs("#todayLine").textContent = new Date().toLocaleDateString("en-GB", {weekday:"long", day:"2-digit", month:"long", year:"numeric"});
  menuButton?.addEventListener("click", ()=>{ const open = primaryNav.classList.toggle("open"); menuButton.setAttribute("aria-expanded", String(open)); });
  qsa(".nav-filter").forEach(btn=>btn.addEventListener("click",()=>{ qsa(".nav-filter").forEach(b=>b.classList.remove("active")); btn.classList.add("active"); activeCategory=btn.dataset.category; btn.scrollIntoView({behavior:"smooth",inline:"center",block:"nearest"}); render(); }));
  searchInput?.addEventListener("input", render);
  qsa(".lang-toggle").forEach(btn=>btn.addEventListener("click",()=>{ qsa(".lang-toggle").forEach(b=>b.classList.remove("active")); btn.classList.add("active"); document.body.classList.toggle("lang-dv", btn.dataset.lang === "dv"); }));
  await loadStories();
}
async function loadStories(){
  try{
    if(!BOT_API_BASE) throw new Error("API not connected");
    const res = await fetch(`${BOT_API_BASE}/api/stories`);
    if(!res.ok) throw new Error("API error");
    stories = await res.json();
  }catch(e){ stories = fallbackStories; }
  render(); renderTicker(); renderLead(); renderPopular();
  storyCount.textContent = stories.length;
  lastPost.textContent = stories[0]?.time || "Now";
}
function render(){
  const query = (searchInput?.value || "").toLowerCase().trim();
  const filtered = stories.filter(s=>{
    const catOk = activeCategory === "all" || normalize(s.category) === normalize(activeCategory);
    const qOk = !query || `${s.title} ${s.summary} ${s.source}`.toLowerCase().includes(query);
    return catOk && qOk;
  });
  if(!filtered.length){ storyGrid.innerHTML = `<div class="empty-state">No stories found yet.</div>`; return; }
  storyGrid.innerHTML = filtered.map(cardHTML).join("");
}
function cardHTML(s){
  return `<article class="story-card">
    <div class="story-card-image"><img src="${s.image || 'assets/SamugaNewsBot_Profile.png'}" alt=""></div>
    <div class="story-card-body">
      <div class="story-meta"><span class="tag">${escapeHTML(s.category || 'Community')}</span><span>${escapeHTML(s.time || 'Now')} • ${escapeHTML(s.source || 'Samuga Media')}</span></div>
      <h3><a href="${s.url || '#'}" target="_blank" rel="noopener">${escapeHTML(s.title)}</a></h3>
      <p>${escapeHTML(s.summary || '')}</p>
    </div>
  </article>`;
}
function renderTicker(){
  const items = stories.slice(0,6).map(s=>`<span>${escapeHTML(s.title)}</span>`).join("");
  tickerTrack.innerHTML = items + items;
}
function renderLead(){
  const lead = stories[0]; if(!lead) return;
  qs("#leadStory .eyebrow").textContent = `${lead.category || 'Latest'} • ${lead.source || 'Samuga Media'}`;
  qs("#leadStory h1").textContent = lead.title;
  qs("#leadStory p").textContent = lead.summary || "Latest Samuga Media update.";
}
function renderPopular(){
  popularList.innerHTML = stories.slice(0,5).map(s=>`<li><a href="${s.url || '#'}">${escapeHTML(s.title)}</a></li>`).join("");
}
function normalize(v){ return String(v || "").toLowerCase().replace("sport","sports"); }
function escapeHTML(str){ return String(str).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
