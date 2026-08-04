const API = "https://samuga-news-bot-production.up.railway.app";
const SITE = "https://samugamedia.com";

function xml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[char]));
}
function cleanText(value, max = 1500) {
  return String(value ?? "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}
function date(value) {
  const parsed = new Date(value || Date.now());
  return Number.isNaN(parsed.getTime()) ? new Date().toUTCString() : parsed.toUTCString();
}
function absolute(value) {
  if (!value) return "";
  try { return new URL(String(value), SITE).href; } catch { return ""; }
}

export async function onRequest() {
  try {
    const response = await fetch(`${API}/api/stories`, {headers:{accept:"application/json"}, cf:{cacheTtl:60,cacheEverything:true}});
    if (!response.ok) throw new Error("stories unavailable");
    const data = await response.json();
    const stories = (Array.isArray(data) ? data : Array.isArray(data?.stories) ? data.stories : [])
      .filter(item => item?.id && item?.title)
      .slice(0, 50);
    const newest = stories[0]?.published_at || stories[0]?.time || Date.now();
    const items = stories.map(item => {
      const link = `${SITE}/article?id=${encodeURIComponent(String(item.id))}`;
      const image = absolute(item.cover_image || item.video_poster);
      const enclosure = image ? `<enclosure url="${xml(image)}" type="image/jpeg"/>` : "";
      return `<item><title>${xml(cleanText(item.title, 300))}</title><link>${xml(link)}</link><guid isPermaLink="true">${xml(link)}</guid><pubDate>${xml(date(item.published_at || item.time))}</pubDate><description>${xml(cleanText(item.summary || item.excerpt || item.title))}</description>${enclosure}</item>`;
    }).join("");
    const body = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Samuga Media</title><link>${SITE}</link><description>Maldives, as it happens. From every island to every screen.</description><language>en-MV</language><lastBuildDate>${xml(date(newest))}</lastBuildDate><ttl>5</ttl>${items}</channel></rss>`;
    return new Response(body, {headers:{"content-type":"application/rss+xml;charset=utf-8","cache-control":"public,max-age=60,s-maxage=120","x-content-type-options":"nosniff"}});
  } catch {
    return new Response('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Samuga Media</title><link>https://samugamedia.com</link><description>Feed temporarily unavailable.</description></channel></rss>', {status:503,headers:{"content-type":"application/rss+xml;charset=utf-8","cache-control":"no-store"}});
  }
}
