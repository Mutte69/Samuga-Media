const DEFAULT_BACKEND = "https://samuga-news-bot-production.up.railway.app";

export function backendBase(env = {}) {
  const value = String(env?.SAMUGA_API_BASE || DEFAULT_BACKEND).trim().replace(/\/+$/, "");
  return /^https:\/\//i.test(value) ? value : DEFAULT_BACKEND;
}

export async function fetchWithTimeout(url, options = {}, timeoutMs = 9000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("upstream_timeout"), Math.max(1000, Number(timeoutMs) || 9000));
  try {
    return await fetch(url, {...options, signal: controller.signal});
  } finally {
    clearTimeout(timer);
  }
}

function toHex(buffer) {
  return [...new Uint8Array(buffer)].map(value => value.toString(16).padStart(2, "0")).join("");
}

export async function signedClientHeaders(request, env = {}) {
  const headers = new Headers();
  const secret = String(env?.SAMUGA_EDGE_PROXY_SECRET || "").trim();
  const client = String(request.headers.get("CF-Connecting-IP") || "").trim().slice(0, 120);
  if (!secret || !client) return headers;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), {name: "HMAC", hash: "SHA-256"}, false, ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(client));
  headers.set("x-samuga-edge-client", client);
  headers.set("x-samuga-edge-signature", toHex(signature));
  return headers;
}

export const SECURITY_HEADERS = {
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
};
