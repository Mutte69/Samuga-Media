"use strict";
(()=>{
  const API="https://samuga-news-bot-production.up.railway.app";
  if(location.pathname.startsWith("/admin"))return;
  let sid="";
  try{sid=localStorage.getItem("samuga-analytics-session")||""}catch{}
  if(!sid){sid=(crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(36).slice(2)}`);try{localStorage.setItem("samuga-analytics-session",sid)}catch{}}
  const params=new URLSearchParams(location.search);
  const payload={event:"pageview",path:location.pathname+location.search,article_id:params.get("id")||null,session_id:sid,referrer:document.referrer||"",language:document.documentElement.lang||navigator.language||""};
  const body=JSON.stringify(payload);
  const send=()=>{try{if(navigator.sendBeacon){const ok=navigator.sendBeacon(`${API}/api/track`,new Blob([body],{type:"application/json"}));if(ok)return}fetch(`${API}/api/track`,{method:"POST",headers:{"Content-Type":"application/json"},body,keepalive:true,cache:"no-store"}).catch(()=>{})}catch{}};
  if(document.readyState==="complete")setTimeout(send,650);else addEventListener("load",()=>setTimeout(send,650),{once:true});
})();
