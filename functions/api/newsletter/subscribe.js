import {fetchWithTimeout, SECURITY_HEADERS} from "../../_lib/runtime.js";
const MAX_BODY_BYTES=8*1024; const EMAIL_RE=/^[^\s@]+@[^\s@]+\.[^\s@]+$/; const JSON_HEADERS={"content-type":"application/json;charset=utf-8","cache-control":"no-store",...SECURITY_HEADERS};
const json=(payload,status=200)=>new Response(JSON.stringify(payload),{status,headers:JSON_HEADERS});
const clean=(value,max=500)=>String(value??"").replace(/[\u0000-\u001f\u007f]/g," ").trim().slice(0,max);
export async function onRequest({request,env}){
 if(request.method==="OPTIONS")return new Response(null,{status:204,headers:{"allow":"POST, OPTIONS","cache-control":"no-store",...SECURITY_HEADERS}});
 if(request.method!=="POST")return json({ok:false,message:"Method not allowed."},405);
 const declared=Number(request.headers.get("content-length")||0); if(declared>MAX_BODY_BYTES)return json({ok:false,message:"Request is too large."},413);
 let payload; try{const raw=await request.text();if(new TextEncoder().encode(raw).byteLength>MAX_BODY_BYTES)return json({ok:false,message:"Request is too large."},413);payload=JSON.parse(raw)}catch{return json({ok:false,message:"Invalid request."},400)}
 if(!payload||typeof payload!=="object"||Array.isArray(payload))return json({ok:false,message:"Invalid request."},400); if(clean(payload.company,200))return json({ok:true,accepted:true},202);
 const email=clean(payload.email,254).toLowerCase(); if(!EMAIL_RE.test(email))return json({ok:false,message:"Enter a valid email address."},400); if(payload.terms!==true)return json({ok:false,message:"Please agree to the Terms and Privacy Policy."},400);
 const apiKey=clean(env?.BUTTONDOWN_API_KEY,500); if(!apiKey)return json({ok:false,message:"Subscriptions are temporarily unavailable."},503);
 const language=clean(payload.language,8)==="dv"?"dv":"en",referrer=clean(payload.referrer,1000),cfCountry=clean(request.cf?.country,8);
 try{const upstream=await fetchWithTimeout("https://api.buttondown.com/v1/subscribers",{method:"POST",headers:{authorization:`Token ${apiKey}`,"content-type":"application/json",accept:"application/json","user-agent":"Samuga-Media-Newsletter/16.3.1"},body:JSON.stringify({email_address:email,referrer_url:referrer||undefined,metadata:{source:"samuga_media_sidebar",language,country:cfCountry||undefined}})},Number(env?.NEWSLETTER_TIMEOUT_MS||9000));
 if(upstream.ok)return json({ok:true,accepted:true,duplicate:false},202);const text=(await upstream.text()).toLowerCase();if([400,409,422].includes(upstream.status)&&/(already|exists|duplicate|subscribed)/.test(text))return json({ok:true,accepted:true,duplicate:true},200);if(upstream.status===429||upstream.status>=500)return json({ok:false,message:"Subscriptions are temporarily unavailable."},503);return json({ok:false,message:"We could not add this email. Please check it and try again."},400)}catch{return json({ok:false,message:"Subscriptions are temporarily unavailable."},503)}
}
