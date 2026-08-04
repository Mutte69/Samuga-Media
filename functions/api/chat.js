const UPSTREAM = "https://samuga-news-bot-production.up.railway.app/api/chat";
const MAX_BODY_BYTES = 32 * 1024;
const HEADERS = {"content-type":"application/json;charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff"};
export async function onRequest({request}) {
  if (request.method !== "POST") return new Response(JSON.stringify({ok:false,error:"Method not allowed"}), {status:405,headers:HEADERS});
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > MAX_BODY_BYTES) return new Response(JSON.stringify({ok:false,error:"Request too large"}), {status:413,headers:HEADERS});
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return new Response(JSON.stringify({ok:false,error:"Request too large"}), {status:413,headers:HEADERS});
    JSON.parse(raw);
    const upstream = await fetch(UPSTREAM, {method:"POST",headers:{"content-type":"application/json","accept":"application/json"},body:raw});
    const text = await upstream.text();
    return new Response(text || "{}", {status:upstream.status,headers:HEADERS});
  } catch {
    return new Response(JSON.stringify({ok:false,error:"Samuga AI temporarily unavailable"}), {status:503,headers:HEADERS});
  }
}
