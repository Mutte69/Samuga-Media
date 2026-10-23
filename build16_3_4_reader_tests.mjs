import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {onRequest} from "./functions/article.js";
import {shortPath} from "./functions/_lib/article-links.js";
const read=name=>readFileSync(new URL(name,import.meta.url),"utf8");
const pages=["index.html","article.html","about.html","advertising.html","contact.html","corrections-policy.html","editorial-policy.html","privacy-policy.html","terms.html","ask-samuga-ai.html"];
function checkTheme(html){
  assert.ok(html.includes('data-theme="light"'),"no-JavaScript default must be light");
  assert.ok(html.includes("samuga-reader-16-3-4.css"));
  const script=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(x=>x[1]).find(x=>x.includes("samuga-theme"));
  assert.ok(script);
  for(const saved of [null,"dark","light","system","invalid"]){
    const document={documentElement:{dataset:{}}};
    vm.runInNewContext(script,{document,localStorage:{getItem:key=>key==="samuga-theme"?saved:null},matchMedia:()=>{throw new Error("OS theme must not control reader default")}});
    assert.equal(document.documentElement.dataset.theme,saved==="dark"?"dark":"light");
  }
  const document={documentElement:{dataset:{}}};
  vm.runInNewContext(script,{document,localStorage:{getItem:()=>{throw new Error("storage blocked")}}});
  assert.equal(document.documentElement.dataset.theme,"light");
}
pages.forEach(file=>checkTheme(read(file)));
const path=shortPath("a".repeat(32));
for(const lang of ["en","dv"]){
  globalThis.fetch=async url=>String(url).includes("site-settings")?Response.json({settings:{default_theme:"dark"}}):Response.json({id:"fixture",public_path:path,title:lang==="en"?"Test story":"ހަބަރު",body:"First paragraph.\n\nSecond paragraph.",lang});
  const response=await onRequest({request:new Request("https://samugamedia.com"+path),params:{code:path.slice(3)}});
  assert.equal(response.status,200); checkTheme(await response.text());
}
// Runtime settings cannot silently re-enable dark mode for a new reader.
assert.ok(!read("website-settings-runtime-16-2-1.js").includes('dataset.theme=s.default_theme'));
assert.ok(!read("site-build16-2-1.js").includes('dataset.theme=siteSettings.default_theme'));
assert.ok(!read("site-common-build16-0-1.js").includes('dataset.theme=settings.default_theme'));
const homepage=read("index.html");
for(const category of ["all","LOCAL","POLITICAL","WORLD","SPORTS","BREAKING"])assert.ok(homepage.includes(`data-cat="${category}"`));
assert.ok(read("site-build16-2-1.js").includes('x.setAttribute("aria-pressed",String(on))'));
console.log("PASS: 16.3.4 white-first theme (72 head-script cases), EN/DV SSR, category controls and settings precedence");
