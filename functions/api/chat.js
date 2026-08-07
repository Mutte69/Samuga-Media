import {backendBase, fetchWithTimeout, signedClientHeaders, SECURITY_HEADERS} from "../_lib/runtime.js";
const MAX_BODY_BYTES = 32 * 1024;
const HEADERS = {"content-type":"application/json;charset=utf-8","cache-control":"no-store",...SECURITY_HEADERS};
const json = (payload, status=200) => new Response(JSON.stringify(payload), {status,headers:HEADERS});
export async function onRequest({request, env}) {
  if (request.method !== "POST") return json({ok:false,error:"Method not allowed"}, 405);
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > MAX_BODY_BYTES) return json({ok:false,error:"Request too large"}, 413);
  let raw = "";
  try {
    raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return json({ok:false,error:"Request too large"}, 413);
  } catch {
    return json({ok:false,error:"Unable to read request"}, 400);
  }
  let payload;
  try { payload = JSON.parse(raw); }
  catch { return json({ok:false,error:"Invalid JSON"}, 400); }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return json({ok:false,error:"Invalid request payload"}, 400);
  try {
    const upstreamHeaders = await signedClientHeaders(request, env);
    upstreamHeaders.set("content-type", "application/json");
    upstreamHeaders.set("accept", "application/json");
    upstreamHeaders.set("x-samuga-chat-proxy", "cloudflare-pages");
    const upstream = await fetchWithTimeout(`${backendBase(env)}/api/chat`, {
      method:"POST", headers:upstreamHeaders, body:JSON.stringify(payload), redirect:"manual",
    }, Number(env?.CHAT_UPSTREAM_TIMEOUT_MS || 35000));
    const text = await upstream.text();
    return new Response(text || "{}", {status:upstream.status,headers:HEADERS});
  } catch {
    return json({ok:false,error:"Samuga AI temporarily unavailable"}, 503);
  }
}
