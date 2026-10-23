import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const elements=new Map(),events=new Map();
function node(id) {
  if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',value:'',checked:false,disabled:false,hidden:false,
    addEventListener:(name,fn)=>events.set(id+':'+name,fn),reset(){},showModal(){this.open=true},close(){this.open=false}});
  return elements.get(id);
}
let ready,calls=[];
const context={window:{},user:{role:'editor'},document:{getElementById:node,addEventListener:(name,fn)=>{ready=fn}},api:async(...args)=>{calls.push(args);return {items:[]}}};
vm.runInNewContext(readFileSync(new URL('./delivery-attention.js',import.meta.url),'utf8'),context);
ready();const ui=context.window.SamugaDeliveryAttention,key='a'.repeat(64);
await ui.load();assert.equal(calls.length,0);assert.equal(node('deliveryAttentionPanel').hidden,true);
context.user={role:'admin'};await ui.load();assert.equal(calls.length,1);assert.match(node('deliveryAttentionState').textContent,/No Telegram/);
for(const state of ['unknown','rejected','sending','retryable']) {
  const html=ui.render([{state,delivery_key:key,publication_id:'<img src=x onerror=evil()>',channel_id:'<script>',reason:'"bad"',attempt_count:1}]);
  assert.ok(!html.includes('<img')&&!html.includes('<script>'));assert.ok(html.includes('&lt;img'));
  assert.equal(html.includes('data-delivery-action'),['unknown','rejected'].includes(state));
}
for(const args of [['confirm_sent','Verified actual post','3',false],['confirm_sent','Verified actual post','0',true],['confirm_sent','Verified actual post','1e3',true],['confirm_sent','Verified actual post','9007199254740993',true],['cancel','short','',false],['retry','Not an allowed action','',false]])assert.throws(()=>ui.payload(...args));
assert.deepEqual(JSON.parse(JSON.stringify(ui.payload('confirm_sent','Verified actual post','123',true))),{action:'confirm_sent',note:'Verified actual post',message_id:123,verified:true});
assert.deepEqual(JSON.parse(JSON.stringify(ui.payload('cancel','Stop uncertain attempt','',false))),{action:'cancel',note:'Stop uncertain attempt'});
const click=(action)=>events.get('deliveryAttentionList:click')({target:{closest:()=>({dataset:{deliveryKey:key,deliveryAction:action}})}});
click('confirm_sent');assert.equal(node('deliveryResolutionDialog').open,true);assert.equal(node('deliveryVerified').required,true);
node('deliveryResolutionNote').value='Verified actual channel post';node('deliveryMessageId').value='123';node('deliveryVerified').checked=true;
calls=[];await events.get('deliveryResolutionForm:submit')({preventDefault(){}});
assert.equal(calls[0][0],'/api/admin/publication-deliveries/'+key+'/resolve');assert.equal(calls[0][1].method,'POST');assert.equal(node('deliveryResolutionDialog').open,false);
click('cancel');assert.equal(node('deliveryMessageField').hidden,true);assert.equal(node('deliveryVerified').required,false);
context.api=async()=>{throw new Error('Delivery changed; refresh')};
await events.get('deliveryResolutionForm:submit')({preventDefault(){}});assert.equal(node('deliveryResolutionDialog').open,true);assert.match(node('deliveryResolutionError').textContent,/Delivery changed/);
await ui.load();assert.match(node('deliveryAttentionState').textContent,/Could not verify/);assert.equal(node('deliveryAttentionList').textContent,'');
assert.ok(!/api\([^)]*\/(?:retry|send|delete)/.test(readFileSync(new URL('./delivery-attention.js',import.meta.url),'utf8')));
console.log('PASS: admin role gating, escaped states, verified receipts, no-send cancellation, conflict handling and fail-visible load errors');
