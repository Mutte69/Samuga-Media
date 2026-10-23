import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {shortPath,keyFromPath,articlePath} from "./functions/_lib/article-links.js";
import {onRequest} from "./functions/n/[code].js";
const sandbox={atob,btoa};
vm.runInNewContext(readFileSync(new URL("./public-article-links.js",import.meta.url),"utf8"),sandbox);
for(let i=0;i<1000;i++){
  const key=createHash("md5").update(`ހަބަރު-${i}`).digest("hex"), path=shortPath(key);
  assert.equal(path.length,25);assert.equal(keyFromPath(path),key);
  const article={id:`argus:${i}`,public_path:`/news/old-headline-${key}`};
  assert.equal(articlePath(article),path);assert.equal(sandbox.SamugaArticleLinks.pathFor(article),path);
}
let calls=0;
const key="e53d193ecfd3f85d2f399449cca33294",path=shortPath(key);
globalThis.fetch=async url=>{calls++;return String(url).includes("site-settings")?Response.json({settings:{}}):Response.json({id:"fixture",public_path:`/news/old-title-${key}`,title:"Test",body:"Test body"})};
let response=await onRequest({request:new Request("https://samugamedia.com"+path),params:{code:path.slice(3)}});
assert.equal(response.status,200);assert.ok((await response.text()).includes(`href="https://samugamedia.com${path}"`));
for(const code of ["A".repeat(21)+"B","bad", "A".repeat(23),"..", "A".repeat(22)+"?x"]){
  calls=0;response=await onRequest({request:new Request("https://samugamedia.com/n/invalid"),params:{code}});
  assert.equal(response.status,404);assert.equal(calls,0);
}
console.log("PASS: 1,000 compact-link roundtrips, browser/edge parity, legacy normalization, route and invalid-code rejection");
