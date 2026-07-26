"use strict";
const SAMUGA_API="https://samuga-news-bot-production.up.railway.app";
document.addEventListener("DOMContentLoaded",async()=>{
  document.querySelectorAll("#themeToggle").forEach(b=>b.addEventListener("click",()=>{const n=document.documentElement.dataset.theme==="light"?"dark":"light";document.documentElement.dataset.theme=n;localStorage.setItem("samuga-theme",n)}));
  document.querySelectorAll("[data-current-year]").forEach(x=>x.textContent=new Date().getFullYear());
  try{const r=await fetch(`${SAMUGA_API}/api/site-settings`,{cache:"no-store"});const d=await r.json(),s=d?.settings||{};
    document.querySelectorAll("[data-community-link]").forEach(x=>{if(s.community_url)x.href=s.community_url});
    document.querySelectorAll("[data-tip-link]").forEach(x=>{if(s.tip_url)x.href=s.tip_url});
    document.querySelectorAll("[data-contact-email]").forEach(x=>{if(s.contact_email){x.href=`mailto:${s.contact_email}`;x.textContent=s.contact_email;x.closest("[data-contact-email-block]")?.removeAttribute("hidden")}});
    if(!localStorage.getItem("samuga-theme")&&["light","dark"].includes(s.default_theme))document.documentElement.dataset.theme=s.default_theme;
  }catch{}
});
