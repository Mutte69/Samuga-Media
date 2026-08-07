import assert from "node:assert/strict";
import { onRequest as articleRoute } from "./functions/article.js";
import { onRequest as storyRoute } from "./functions/story.js";
import { onRequest as chatRoute } from "./functions/api/chat.js";
import { onRequest as settingsRoute } from "./functions/api/site-settings.js";

let passed = 0;
const test = async (name, fn) => {
  await fn();
  passed += 1;
  console.log(`PASS | ${name}`);
};

const articleFixture = {
  id: "test-article",
  title: "Test Maldives Story",
  body: "First paragraph.\n\nSecond paragraph.",
  category: "LOCAL",
  lang: "en",
  published_at: "2026-08-04T12:00:00+05:00",
  author: {name: "Samuga Media", role: "Newsroom"},
  related: [],
};

async function testArticleHandler(handler, path) {
  globalThis.fetch = async (url) => {
    const target = String(url);
    if (target.includes("/api/article")) {
      return new Response(JSON.stringify(articleFixture), {status: 200, headers: {"content-type":"application/json"}});
    }
    if (target.includes("/api/site-settings")) {
      return new Response(JSON.stringify({settings:{community_url:"https://t.me/samugacommunity"}}), {status: 200, headers: {"content-type":"application/json"}});
    }
    throw new Error(`Unexpected URL ${target}`);
  };
  const response = await handler({request: new Request(`https://samugamedia.com/${path}?id=test-article`)});
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /data-samuga-build="16\.3\.1"/);
  assert.match(html, /settings-sticky-header/);
  assert.match(html, /samuga-v3-shell-16-2-1\.js/);
  assert.match(html, /website-settings-runtime-16-2-1\.js/);
  assert.match(html, /website-settings-runtime-16-2-1\.css/);
  assert.match(html, /href="\/about"/);
  assert.doesNotMatch(html, /href="\/about\.html"/);
  assert.doesNotMatch(html, /samuga-v3-shell-16-0-1\.js/);
  assert.equal(response.headers.get("x-samuga-function"), "article-build16.3.1");
}

await test("dynamic /article route renders the current public shell", async () => testArticleHandler(articleRoute, "article"));
await test("dynamic /story route renders the current public shell", async () => testArticleHandler(storyRoute, "story"));

await test("chat proxy rejects non-POST requests", async () => {
  const response = await chatRoute({request: new Request("https://samugamedia.com/api/chat")});
  assert.equal(response.status, 405);
  assert.match(await response.text(), /Method not allowed/);
});

await test("chat proxy forwards a valid JSON request and preserves status", async () => {
  let forwarded = null;
  globalThis.fetch = async (url, options) => {
    forwarded = {url: String(url), options};
    return new Response(JSON.stringify({reply:"Working"}), {status: 200, headers: {"content-type":"application/json"}});
  };
  const request = new Request("https://samugamedia.com/api/chat", {
    method: "POST",
    headers: {"content-type":"application/json"},
    body: JSON.stringify({message:"Latest news", lang:"en", surface:"dedicated-page"}),
  });
  const response = await chatRoute({request});
  assert.equal(response.status, 200);
  assert.match(forwarded.url, /samuga-news-bot-production\.up\.railway\.app\/api\/chat/);
  assert.equal(JSON.parse(forwarded.options.body).surface, "dedicated-page");
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), {reply:"Working"});
});

await test("chat proxy safely rejects malformed JSON", async () => {
  const request = new Request("https://samugamedia.com/api/chat", {
    method: "POST", headers: {"content-type":"application/json"}, body: "not-json",
  });
  const response = await chatRoute({request});
  assert.equal(response.status, 400);
});

await test("site-settings proxy forwards query parameters without caching", async () => {
  let requested = "";
  globalThis.fetch = async (url) => {
    requested = String(url);
    return new Response(JSON.stringify({settings:{ai_enabled:true}}), {status:200});
  };
  const response = await settingsRoute({request: new Request("https://samugamedia.com/api/site-settings?fresh=1")});
  assert.equal(response.status, 200);
  assert.match(requested, /\?fresh=1$/);
  assert.equal(response.headers.get("cache-control"), "no-store,max-age=0");
});

await test("site-settings proxy rejects writes on the public endpoint", async () => {
  const response = await settingsRoute({request: new Request("https://samugamedia.com/api/site-settings", {method:"POST"})});
  assert.equal(response.status, 405);
});

console.log(`RESULT: ${passed} FUNCTION CONTRACT TESTS PASSED`);
