/* Operator reconciliation only. This module has no send/retry/delete endpoint. */
(() => {
  const node=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const isAdmin=()=>typeof user!=='undefined' && ['admin','super_admin'].includes(user?.role);
  let loading=false, selection=null;
  function render(items) {
    return items.map(item=>{
      const key=String(item.delivery_key||''),resolvable=['unknown','rejected'].includes(item.state)&&/^[a-f0-9]{64}$/.test(key);
      const article=String(item.publication_id||'').match(/^article:(.+):(en|dv)$/);
      const story=article?` <a class="text-button" href="https://samugamedia.com/article?id=${escape(encodeURIComponent(article[1]))}" target="_blank" rel="noopener noreferrer">Open website story (if published)</a>`:'';
      return `<article class="delivery-attention-item"><strong>${escape(item.state)} · Telegram</strong><p>${escape(item.publication_id)}${story}</p><p>Channel ${escape(item.channel_id)} · ${escape(item.reason||'Awaiting outcome')} · ${escape(item.attempt_count)} attempt(s)</p><code>${escape(key)}</code>${resolvable?`<div class="button-row"><button type="button" class="secondary" data-delivery-key="${key}" data-delivery-action="confirm_sent">Record verified post</button><button type="button" class="secondary" data-delivery-key="${key}" data-delivery-action="cancel">Stop further attempts</button></div>`:'<p>No resolution action while this send is active or waiting for its rate-limit delay.</p>'}</article>`;
    }).join('');
  }
  async function load() {
    const panel=node('deliveryAttentionPanel');if(!panel)return;
    panel.hidden=!isAdmin();
    if(!isAdmin()||loading)return;
    loading=true;node('deliveryAttentionState').textContent='Checking durable delivery records…';
    try {
      const data=await api('/api/admin/publication-deliveries');
      if(!isAdmin()){panel.hidden=true;return;}
      const items=Array.isArray(data.items)?data.items:[];
      node('deliveryAttentionList').innerHTML=render(items);
      node('deliveryAttentionState').textContent=items.length?`${items.length} attention item(s), newest first (up to 50).`:'No Telegram news-card deliveries currently need attention.';
    } catch(error) {
      node('deliveryAttentionList').textContent='';
      node('deliveryAttentionState').textContent='Could not verify deliveries: '+String(error.message||'Request failed');
    } finally {loading=false;}
  }
  function open(key,action) {
    if(!isAdmin()||!/^[a-f0-9]{64}$/.test(key)||!['confirm_sent','cancel'].includes(action))return;
    selection={key,action};node('deliveryResolutionForm').reset();node('deliveryResolutionError').textContent='';
    const confirming=action==='confirm_sent';
    node('deliveryResolutionTitle').textContent=confirming?'Record a verified existing post':'Stop further delivery attempts';
    node('deliveryResolutionExplanation').textContent=confirming?'First verify the actual post and channel. This records its existing message ID; it does not publish another post.':'This stops future attempts for this intent. It does not delete a public post, and an uncertain post may already exist.';
    node('deliveryMessageField').hidden=node('deliveryVerifiedField').hidden=!confirming;
    node('deliveryMessageId').required=node('deliveryVerified').required=confirming;
    node('deliveryResolutionDialog').showModal();
  }
  function payload(action,note,messageId,verified) {
    if(!['confirm_sent','cancel'].includes(action)||String(note||'').trim().length<10)throw new Error('Enter a resolution note of at least 10 characters.');
    const data={action,note:String(note).trim()};
    if(action==='confirm_sent') {
      const mid=Number(messageId);
      if(!/^[1-9][0-9]*$/.test(String(messageId))||!Number.isSafeInteger(mid)||mid<=0||verified!==true)throw new Error('Check the actual channel post and enter its positive message ID.');
      data.message_id=mid;data.verified=true;
    }
    return data;
  }
  async function submit(event) {
    event.preventDefault();const button=node('saveDeliveryResolution');
    if(!isAdmin()||!selection||button.disabled)return;
    const selected={...selection};
    try {
      const data=payload(selected.action,node('deliveryResolutionNote').value,node('deliveryMessageId').value,node('deliveryVerified').checked);
      button.disabled=true;node('deliveryResolutionError').textContent='';
      await api(`/api/admin/publication-deliveries/${selected.key}/resolve`,{method:'POST',body:JSON.stringify(data)});
      node('deliveryResolutionDialog').close();selection=null;await load();
    } catch(error) {node('deliveryResolutionError').textContent=String(error.message||'Resolution could not be verified. Refresh before trying again.');}
    finally {button.disabled=false;}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    node('refreshDeliveryAttention')?.addEventListener('click',load);
    node('deliveryAttentionList')?.addEventListener('click',event=>{const button=event.target.closest('[data-delivery-action]');if(button)open(button.dataset.deliveryKey,button.dataset.deliveryAction);});
    node('deliveryResolutionForm')?.addEventListener('submit',submit);
    node('closeDeliveryResolution')?.addEventListener('click',()=>{node('deliveryResolutionDialog').close();selection=null;});
  });
  window.SamugaDeliveryAttention=Object.freeze({load,render,payload});
})();
