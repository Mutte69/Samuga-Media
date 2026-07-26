const UPSTREAM = "https://samuga-news-bot-production.up.railway.app/api/track";
const MAX_BODY_BYTES = 16 * 1024;
const JSON_HEADERS = {"content-type":"application/json;charset=utf-8","cache-control":"no-store"};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {status, headers: JSON_HEADERS});
}

export async function onRequest({request}) {
  if (request.method === "OPTIONS") {
    return new Response(null, {status: 204, headers: {"allow":"POST, OPTIONS","cache-control":"no-store"}});
  }
  if (request.method !== "POST") {
    return json({ok:false,error:"Method not allowed."}, 405);
  }

  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_BODY_BYTES) {
    return json({ok:false,error:"Analytics payload is too large."}, 413);
  }

  let raw = "";
  let payload;
  try {
    raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) {
      return json({ok:false,error:"Analytics payload is too large."}, 413);
    }
    payload = JSON.parse(raw);
  } catch {
    return json({ok:false,error:"Invalid analytics payload."}, 400);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return json({ok:false,error:"Invalid analytics payload."}, 400);
  }

  const headers = new Headers({
    "content-type":"application/json",
    "accept":"application/json",
    "x-samuga-analytics-proxy":"cloudflare-pages"
  });
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("x-samuga-user-agent", userAgent.slice(0, 500));

  try {
    const upstream = await fetch(UPSTREAM, {
      method:"POST",
      headers,
      body:JSON.stringify(payload),
      redirect:"manual"
    });
    const text = await upstream.text();
    return new Response(text || JSON.stringify({ok:upstream.ok}), {
      status:upstream.status,
      headers:JSON_HEADERS
    });
  } catch {
    return json({ok:false,error:"Analytics service is temporarily unavailable."}, 503);
  }
}
