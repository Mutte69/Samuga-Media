import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {articlePath,numberFromPath,shortPath} from './functions/_lib/article-links.js';
import {onRequest} from './functions/n/[code].js';
const sandbox={atob,btoa};
vm.runInNewContext(readFileSync(new URL('./public-article-links.js',import.meta.url),'utf8'),sandbox);
for(const code of ['1','12345','9223372036854775807']) {
  const article={id:'private-provider-id',public_path:'/n/'+code,title:'Example',body:'Body'};
  assert.equal(articlePath(article),article.public_path);
  assert.equal(sandbox.SamugaArticleLinks.pathFor(article),article.public_path);
  let requested='';
  globalThis.fetch=async url=>String(url).includes('site-settings')?Response.json({settings:{}}):(requested=String(url),Response.json(article));
  const response=await onRequest({request:new Request('https://samugamedia.com/n/'+code),params:{code}});
  assert.equal(response.status,200);assert.ok(requested.includes('number='+code));
  assert.ok((await response.text()).includes('https://samugamedia.com/n/'+code));
}
for(const code of ['0','01','-1','9223372036854775808','1e3','12?next=x','12345678901234567890']) {
  assert.equal(numberFromPath('/n/'+code),'');
  globalThis.fetch=()=>{throw new Error('invalid input must not reach backend')};
  assert.equal((await onRequest({request:new Request('https://samugamedia.com/n/test'),params:{code}})).status,404);
}
const old=shortPath('a89e1f1eb7c07d80a4eae0c1bafc2031');
globalThis.fetch=async url=>Response.json(String(url).includes('site-settings')?{settings:{}}:{id:'fixture',public_path:'/n/12345'});
const redirected=await onRequest({request:new Request('https://samugamedia.com'+old),params:{code:old.slice(3)}});
assert.equal(redirected.status,308);assert.equal(redirected.headers.get('location'),'https://samugamedia.com/n/12345');
console.log('PASS: numbered browser/edge parity, BIGINT boundaries, validation and old-link permanent redirect');
