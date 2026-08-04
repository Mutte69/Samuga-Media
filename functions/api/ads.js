const UPSTREAM = "https://samuga-news-bot-production.up.railway.app/api/ads";
const HEADERS = {"content-type":"application/json;charset=utf-8","cache-control":"public,max-age=30,s-maxage=60","x-content-type-options":"nosniff"};
export async function onRequest({request}) {
  if (request.method !== "GET") return new Response(JSON.stringify({ok:false,error:"Method not allowed"}), {status:405,headers:HEADERS});
  const url = new URL(request.url);
  try {
    const upstream = await fetch(`${UPSTREAM}${url.search}`, {headers:{accept:"application/json"},cf:{cacheTtl:30,cacheEverything:true}});
    const text = await upstream.text();
    return new Response(text || "{}", {status:upstream.status,headers:HEADERS});
  } catch {
    return new Response(JSON.stringify({ok:false,error:"Ads temporarily unavailable"}), {status:503,headers:{...HEADERS,"cache-control":"no-store"}});
  }
}
