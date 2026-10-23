import {backendBase, fetchWithTimeout, SECURITY_HEADERS} from "../_lib/runtime.js";
const HEADERS = {"content-type":"application/json;charset=utf-8","cache-control":"public,max-age=15,s-maxage=30",...SECURITY_HEADERS};
export async function onRequest({request, env}) {
  if (request.method !== "GET") return new Response(JSON.stringify({ok:false,error:"Method not allowed"}), {status:405,headers:HEADERS});
  const url = new URL(request.url);
  try {
    const upstream = await fetchWithTimeout(`${backendBase(env)}/api/article${url.search}`, {headers:{accept:"application/json"}}, Number(env?.UPSTREAM_TIMEOUT_MS || 9000));
    const text = await upstream.text();
    return new Response(text || "{}", {status:upstream.status,headers:upstream.ok?HEADERS:{...HEADERS,"cache-control":"no-store"}});
  } catch {
    return new Response(JSON.stringify({ok:false,error:"Samuga service temporarily unavailable"}), {status:503,headers:{...HEADERS,"cache-control":"no-store"}});
  }
}
