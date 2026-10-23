import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {onRequest as articleRoute} from "./functions/article.js";
import {onRequest as newsRoute} from "./functions/news/[slug].js";
import {onRequest as legacyStory} from "./functions/story.js";
import {onRequest as feedRoute} from "./functions/feed.xml.js";
import {articlePath, shortPath} from "./functions/_lib/article-links.js";
import {onRequest as articleProxy} from "./functions/api/article.js";

const key = "f".repeat(32), path = shortPath(key);
const fixture = {id:"argus:fixture", title:"Council opens terminal", public_path:path,
 body:"First paragraph.\n\nSecond paragraph.", lang:"en", published_at:"2026-10-23T10:00:00Z",
 related:[{id:"argus:related", title:"Another terminal update", public_path:`/news/update-${"a".repeat(32)}`} ]};
const requests = [];
let status = 200;
globalThis.fetch = async url => {
  requests.push(String(url));
  if (String(url).includes("/api/site-settings")) return Response.json({settings:{}});
  if (String(url).includes("/api/stories")) return Response.json([fixture]);
  return Response.json(status === 200 ? fixture : {error:"unavailable"}, {status});
};
const context = {request:new Request("https://samugamedia.com" + path), params:{code:path.slice(3)}};
let response = await articleRoute(context);
assert.equal(response.status, 200);
const html = await response.text();
assert.ok(requests.some(url=>url.endsWith(`/api/article?public_key=${key}`)));
assert.ok(html.includes(`<link rel="canonical" href="https://samugamedia.com${path}">`));
assert.ok(html.includes(`property="og:url" content="https://samugamedia.com${path}"`));
assert.ok(html.includes(`href="${articlePath(fixture.related[0])}"`));
assert.ok(html.includes('name="samuga-article-id" content="argus:fixture"'));
assert.ok(!html.includes('/article?id=argus'));
assert.ok(html.includes(encodeURIComponent("https://samugamedia.com"+path)));
for (const handler of [articleRoute, legacyStory]) {
  response = await handler({request:new Request("https://samugamedia.com/article?id=argus%3Afixture")});
  assert.equal(response.status, 308);
  assert.equal(response.headers.get("location"), "https://samugamedia.com"+path);
}
response = await newsRoute({...context, request:new Request(`https://samugamedia.com/news/old-title-${key}`), params:{slug:`old-title-${key}`}});
assert.equal(response.status,308);
assert.equal(response.headers.get("location"),"https://samugamedia.com"+path);
requests.length=0;
response = await newsRoute({...context, params:{slug:"invalid"}});
assert.equal(response.status,404); assert.equal(requests.length,0);
for (const upstreamStatus of [404,429,500,503]) {
  status=upstreamStatus; response=await articleRoute(context);
  assert.equal(response.status,upstreamStatus===404?404:503);
  assert.equal(response.headers.get("cache-control"),"no-store");
  const proxy=await articleProxy({request:new Request("https://samugamedia.com/api/article?public_key="+key)});
  assert.equal(proxy.status,upstreamStatus);
  assert.equal(proxy.headers.get("cache-control"),"no-store");
}
status=200;
response=await feedRoute({});
const xml=await response.text();
assert.ok(xml.includes(`<link>https://samugamedia.com${path}</link>`));
assert.ok(xml.includes('<guid isPermaLink="true">https://samugamedia.com/article?id=argus%3Afixture</guid>'),"keep existing feed identity to avoid resending every story");
const sandbox={atob,btoa};
vm.runInNewContext(readFileSync(new URL("./public-article-links.js",import.meta.url),"utf8"),sandbox);
assert.equal(sandbox.SamugaArticleLinks.pathFor(fixture),articlePath(fixture));
for(const bad of ["https://evil.test/news/x","//evil.test/news/x","/news/x?next=evil","javascript:alert(1)"]){
  const item={id:"legacy",public_path:bad};
  assert.equal(sandbox.SamugaArticleLinks.pathFor(item),"/article?id=legacy");
  assert.equal(articlePath(item),"/article?id=legacy");
}
const homepage=readFileSync(new URL("./site-build16-2-1.js",import.meta.url),"utf8");
assert.ok(homepage.includes('public_path:s.public_path||""'));
const colors=vm.runInNewContext(homepage.match(/^const COLORS=.*$/m)[0]+";COLORS");
assert.equal(colors.SPORTS,"#22b450"); assert.equal(colors.POLITICAL,"#bc5b10");
assert.equal(colors.WORLD,"#7043b4"); assert.equal(colors.LOCAL,"#1b70c2");
console.log("PASS: 16.3.3 public routes, canonical/share/feed links, legacy redirects, outages, browser helper and sports-green palette");
