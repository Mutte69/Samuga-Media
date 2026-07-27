"use strict";
(()=>{
  if(location.pathname.startsWith("/admin"))return;
  const ENDPOINT="/api/track";
  let sessionId="";
  try{sessionId=localStorage.getItem("samuga-analytics-session")||""}catch{}
  if(!sessionId){
    sessionId=crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try{localStorage.setItem("samuga-analytics-session",sessionId)}catch{}
  }
  const params=new URLSearchParams(location.search);
  const eventId=crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const payload={
    event:"pageview",
    event_id:eventId,
    path:location.pathname+location.search,
    article_id:params.get("id")||null,
    session_id:sessionId,
    referrer:document.referrer||"",
    language:document.documentElement.lang||navigator.language||""
  };
  const body=JSON.stringify(payload);
  let started=false;

  const beaconFallback=()=>{
    try{return Boolean(navigator.sendBeacon&&navigator.sendBeacon(ENDPOINT,body))}catch{return false}
  };
  const send=async()=>{
    if(started)return;
    started=true;
    try{
      const response=await fetch(ENDPOINT,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body,
        keepalive:true,
        cache:"no-store",
        credentials:"omit"
      });
      if(!response.ok)throw new Error(`Analytics ${response.status}`);
    }catch{
      beaconFallback();
    }
  };

  if(document.readyState==="complete")setTimeout(send,300);
  else addEventListener("load",()=>setTimeout(send,300),{once:true});
})();
