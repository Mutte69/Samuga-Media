"use strict";
const SAMUGA_API="https://samuga-news-bot-production.up.railway.app";
const samugaStorage={
  get(key){try{return window.localStorage?.getItem(key)??null}catch{return null}},
  set(key,value){try{window.localStorage?.setItem(key,String(value));return true}catch{return false}}
};
async function samugaApiFetch(path,options={}){
  let lastError=null;
  for(const url of [path,`${SAMUGA_API}${path}`]){
    try{
      const response=await fetch(url,{...options});
      if(response.ok)return response;
      lastError=new Error(`HTTP ${response.status}`);
      if(response.status>=400&&response.status<500&&![404,408,429].includes(response.status))break;
    }catch(error){lastError=error}
  }
  throw lastError||new Error("API unavailable");
}
document.addEventListener("DOMContentLoaded",async()=>{
  document.querySelectorAll("#themeToggle").forEach(button=>button.addEventListener("click",()=>{
    const next=document.documentElement.dataset.theme==="light"?"dark":"light";
    document.documentElement.dataset.theme=next;
    samugaStorage.set("samuga-theme",next);
  }));
  document.querySelectorAll("[data-current-year]").forEach(node=>node.textContent=new Date().getFullYear());
  try{
    const response=await samugaApiFetch("/api/site-settings",{cache:"no-store"});
    const data=await response.json();
    const settings=data?.settings||{};
    document.querySelectorAll("[data-community-link]").forEach(node=>{if(settings.community_url)node.href=settings.community_url});
    document.querySelectorAll("[data-tip-link]").forEach(node=>{if(settings.tip_url)node.href=settings.tip_url});
    document.querySelectorAll("[data-contact-email]").forEach(node=>{
      if(settings.contact_email){node.href=`mailto:${settings.contact_email}`;node.textContent=settings.contact_email;node.closest("[data-contact-email-block]")?.removeAttribute("hidden")}
    });
    if(!samugaStorage.get("samuga-theme")&&["light","dark"].includes(settings.default_theme))document.documentElement.dataset.theme=settings.default_theme;
  }catch{}
});
