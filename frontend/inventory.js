// Inventory and account controls extend Rebuilt's existing UI and component transport.
let looseTimer, looseVersion=0;
const copyInventories=new Map();

function renderDraftStatus(){
  const session=state.session;
  $('#draft-summary').textContent=session ? `${session.document.name}${session.dirty?' · Unsaved':''}` : 'Opening draft…';
  $('#loose-count').textContent=number((session?.loose||[]).reduce((n,r)=>n+r.quantity,0));
  const issues=session?.issues||[];
  $('#inventory-issues').hidden=!issues.length&&!session?.catalog_changed;
  $('#inventory-issues').textContent=issues.length ? `${issues.length} inventory issues. Open Manage or a set’s details to correct them.` : session?.catalog_changed?'Catalog changed. Review saved copy inventories before saving.':'';
}

function applySession(data,{invalidate=true}={}){
  state.session=data;state.document=data.document;
  state.collection=new Map(data.sets.map(({quantity,...set})=>[set.code,{set,quantity}]));
  state.plan=null;copyInventories.clear();persist();
  if(invalidate){requestVersion++;matchRequest?.abort();state.results=null;state.searched=false;state.loading=false;state.page=1;}
  renderCollection();renderToolbar();if(invalidate)renderWelcome();
  if($('#collection-dialog').open)renderCollectionManager();
  if($('#loose-dialog').open)renderLooseEntries();
}

async function editInventory(body){
  const data=await api('/api/edit',body);
  applySession(data,{invalidate:data.invalidates_results!==false});
  if($('#plan-output'))$('#plan-output').replaceChildren();
  return data;
}

function inventoryError(error,node){
  if(node)node.textContent=error.message;
  toast(error.message);
  if(error.code==='revision_conflict'){
    state.conflict=true;
    if($('#collection-dialog').open)renderCollectionManager();
  }
}

async function navigateDraft(action,decision){
  try{
    const data=await api('/api/navigate',decision?{decision}:{action});
    if(data.pending){
      state.session=data;
      $('#navigation-save').disabled=!data.email;
      $('#navigation-note').textContent=data.email?'':"Sign in to save to the cloud. Cancel to keep editing or sign in.";
      $('#navigation-message').textContent='';
      openDialog($('#navigation-dialog'));return;
    }
    state.session=data;
    $('#navigation-dialog').close();
    if(decision==='cancel'){state.session=data;return;}
    state.conflict=false;
    applySession(data);
    $('#detail-dialog').close();$('#loose-dialog').close();
    if(action?.kind==='logout'||(!data.email&&decision)){
      $('#account-content').replaceChildren();$('#account-dialog').close();
      $('#loose-search').value='';$('#loose-search-results').replaceChildren();
      $('#detail-content').replaceChildren();
    }
  }catch(error){inventoryError(error,$('#navigation-dialog').open?$('#navigation-message'):null);}
}

function renderCollectionManager(){
  const s=state.session;if(!s)return;
  const d=s.document;
  $('#collections-content').innerHTML=`<span class="eyebrow">YOUR COLLECTIONS</span><h2 class="modal-title" id="collections-heading">A collection of your own.</h2>
    <p class="detail-explanation">${s.dirty?'Unsaved changes':d.revision?`Saved revision ${d.revision}`:'New draft'} · Save is explicit. Each saved collection stands on its own.</p>
    <form data-rename class="inventory-form"><label class="field-label" for="collection-name">Collection name</label><div class="input-action"><input class="inventory-input" id="collection-name" name="name" value="${escapeHTML(d.name)}" maxlength="100" required><button class="secondary-button">Rename</button></div></form>
    <div class="collection-actions"><button class="secondary-button" data-new>New</button><button class="primary-button" data-save ${s.email?'':'disabled'}>Save</button><button class="secondary-button" data-show-save-as ${s.email?'':'disabled'}>Save as</button><button class="secondary-button" data-delete-saved ${s.email&&d.revision?'':'disabled'}>Delete</button></div>
    <form data-save-as class="inventory-form" hidden><label class="field-label" for="save-as-name">New collection name</label><div class="input-action"><input class="inventory-input" id="save-as-name" name="name" maxlength="100" required value="${escapeHTML(d.name)} copy"><button class="primary-button">Save new collection</button></div></form>
    ${state.conflict?`<div class="inventory-notice"><strong>A newer saved version exists.</strong><p>Your local draft is preserved. Reload the server version or Save as a new collection.</p><button class="secondary-button" data-reload-saved>Reload server version</button><button class="secondary-button" data-show-save-as>Save as</button></div>`:''}
    ${s.issues.length?`<div class="inventory-notice">${s.issues.map(i=>`<p>${escapeHTML(i.record_id)}: ${escapeHTML(i.message)}</p>`).join('')}${d.copies.filter(c=>!state.collection.has(c.set_num)).map(c=>`<p>${escapeHTML(c.label||c.set_num)} <button class="secondary-button" data-copy-remove="${escapeHTML(c.id)}">Remove unknown copy</button></p>`).join('')}</div>`:''}
    <div class="account-summary"><p>${s.email?`Signed in as <strong>${escapeHTML(s.email)}</strong>`:'Guest editing is always available.'}</p>${s.email?'<button class="text-button" data-sign-out>Sign out ↗</button>':`<button class="secondary-button" data-sign-in ${s.cloud_enabled?'':'disabled'}>Sign in / Sign up</button>`}
    <p class="detail-explanation">${s.local_backend?'Local test backend: accounts and saves are temporary. Refreshing requires signing in again.':s.cloud_enabled?'Sign-in lasts for this active session. Refreshing requires signing in again.':'Cloud saving is not configured yet. Add sets, loose parts, and plan builds as a guest.'}</p></div>
    ${s.email?'<section class="detail-pieces"><h3>Saved collections</h3><div id="saved-list">Opening saved collections…</div><button class="text-button" data-refresh-saved>Refresh list ↗</button></section>':''}
    <p class="form-message" id="collection-message" role="status"></p>`;
  if(s.email)refreshSaved();
}

async function refreshSaved(){
  const node=$('#saved-list');if(!node)return;
  try{const data=await api('/api/saved',{});if(!node.isConnected)return;
    node.innerHTML=data.collections.length?`<label class="field-label" for="saved-selection">Choose a collection</label><div class="input-action"><select class="inventory-input" id="saved-selection">${data.collections.map(c=>`<option value="${escapeHTML(c.id)}">${escapeHTML(c.name)} · revision ${c.revision}</option>`).join('')}</select><button class="secondary-button" data-load-saved>Load</button></div>`:'<p class="detail-explanation">No saved collections yet.</p>';
  }catch(error){if(node.isConnected)node.textContent=error.message;}
}

function showAccount(){
  $('#account-content').innerHTML=`<span class="eyebrow">BRING YOUR COLLECTION BACK</span><h2 class="modal-title" id="account-heading">Your bricks, saved.</h2><p class="detail-explanation">${state.session.local_backend?'Local test backend. Use test credentials; emulator saves are temporary.':'Sign in or create an email/password account.'} Your current draft stays here.</p><form id="account-form" class="inventory-form"><label class="field-label" for="account-action">Account action</label><select class="inventory-input" id="account-action"><option value="login">Log in</option><option value="signup">Sign up</option></select><label class="field-label" for="account-email">Email</label><input class="inventory-input" id="account-email" type="email" autocomplete="off" required><label class="field-label" for="account-password">Password</label><input class="inventory-input" id="account-password" type="password" autocomplete="off" minlength="6" required><button class="primary-button" type="submit">Continue ↗</button></form><p class="form-message" id="account-message" role="status"></p><p class="detail-explanation">No verification email is required. Refreshing ends this sign-in.</p>`;
  openDialog($('#account-dialog'));
}

async function saveDraft(asName){
  try{const body=asName===undefined?{}:{as_name:asName};const data=await api('/api/save',body);state.conflict=false;applySession(data);toast('Collection saved.');}
  catch(error){inventoryError(error,$('#collection-message'));}
}

function physicalCopyMarkup(code){
  const copies=(state.document?.copies||[]).filter(c=>c.set_num===code);
  if(!copies.length)return '';
  return `<section class="detail-pieces" id="physical-copies"><h3>Your physical copies</h3><p>Each copy has its own missing pieces. Keep assembled protects it from planning; recommendations still count its effective inventory.</p>${copies.map(c=>`<details class="copy-editor" data-copy-editor="${escapeHTML(c.id)}"><summary><strong>${escapeHTML(c.label||c.set_num)}</strong><span>${c.keep_assembled?'Protected · ':''}${c.missing.reduce((n,r)=>n+r.quantity,0)} missing</span></summary><p class="copy-id">${escapeHTML(c.id)}</p><form class="inventory-form" data-copy-update="${escapeHTML(c.id)}"><label class="field-label">Copy label<input class="inventory-input" name="label" maxlength="200" value="${escapeHTML(c.label)}"></label><label class="protection-control"><input type="checkbox" name="protected" ${c.keep_assembled?'checked':''}> Keep assembled</label><p class="detail-explanation">Planner only: these pieces still count toward recommendations.</p><button class="secondary-button">Update copy</button></form><div data-copy-parts="${escapeHTML(c.id)}">Open this copy to edit missing pieces.</div>${c.missing.length?`<div class="missing-adjustments">${c.missing.map(r=>`<div><span>${escapeHTML(r.part_id)} · color ${r.color_id} · ${r.quantity} missing</span><button class="text-button" data-missing-remove="${escapeHTML(c.id)}" data-part="${escapeHTML(r.part_id)}" data-color="${r.color_id}">Remove adjustment</button></div>`).join('')}</div>`:''}<button class="text-button danger-button" data-copy-remove="${escapeHTML(c.id)}">Remove this copy</button></details>`).join('')}</section>`;
}

async function loadCopyInventory(id){
  const node=$(`[data-copy-parts="${CSS.escape(id)}"]`);if(!node)return;
  try{const data=copyInventories.get(id)||await api('/api/copy-inventory',{copy_id:id});copyInventories.set(id,data);if(!node.isConnected)return;
    const copy=state.document.copies.find(c=>c.id===id);
    node.innerHTML=`${copy.inventory_version!==data.version?`<div class="inventory-notice">Saved inventory version ${copy.inventory_version}; current ${data.version}. Review adjustments, then <button class="secondary-button" data-accept-version="${id}">Accept current inventory</button>.</div>`:''}<form class="inventory-form" data-copy-missing="${id}"><label class="field-label">Missing part / color<select class="inventory-input" name="part">${data.parts.map(r=>`<option value="${escapeHTML(JSON.stringify([r.part_id,r.color_id]))}">${escapeHTML(r.part_id)} · ${escapeHTML(r.part)} · ${escapeHTML(r.color)} (${r.required} in copy)</option>`).join('')}</select></label><label class="field-label">Missing quantity<input class="inventory-input" type="number" name="quantity" min="0" step="1" required></label><button class="secondary-button">Set missing quantity</button><p class="detail-explanation">Zero removes the adjustment. Missing pieces never create loose parts.</p></form>`;
    syncMissingQuantity(node.querySelector('form'));
  }catch(error){if(node.isConnected)node.textContent=error.message;}
}

function syncMissingQuantity(form){
  const data=copyInventories.get(form.dataset.copyMissing);if(!data)return;
  const [part,color]=JSON.parse(form.elements.part.value),row=data.parts.find(r=>r.part_id===part&&r.color_id===color);
  form.elements.quantity.max=row.required;
  form.elements.quantity.value=Number.isInteger(row.missing)&&row.missing>=0&&row.missing<=row.required?row.missing:0;
}

async function refreshCopyDetails(code,openId){
  const set=state.collection.get(code)?.set;
  if(!set){$('#detail-dialog').close();return;}
  openSet(set);
  const details=$(`[data-copy-editor="${CSS.escape(String(openId))}"]`);if(details)details.open=true;
}

function renderLooseEntries(){
  $('#loose-entries').innerHTML=`<section class="detail-pieces"><h3>Loose pieces in this draft</h3>${state.session.loose.length?state.session.loose.map(r=>`<form class="loose-row" data-loose-total="${escapeHTML(JSON.stringify([r.part_id,r.color_id]))}"><div><strong>${escapeHTML(r.part)}</strong><p>${escapeHTML(r.part_id)} · ${escapeHTML(r.color)}</p></div><label class="field-label">Total quantity<input class="inventory-input" name="quantity" type="number" min="0" step="1" value="${Number.isInteger(r.quantity)&&r.quantity>=0?r.quantity:0}" required></label><button class="secondary-button">Set total</button></form>`).join(''):'<p class="detail-explanation">No loose parts yet.</p>'}<p class="detail-explanation">Editing sets the total. Set zero to remove an entry.</p></section>`;
}

async function searchLoose(){
  const query=$('#loose-search').value.trim(),version=++looseVersion;
  if(!query){$('#loose-search-results').replaceChildren();return;}
  try{const data=await api(`/api/parts?q=${encodeURIComponent(query)}`);if(version!==looseVersion)return;
    $('#loose-search-results').innerHTML=data.parts.length?`<form class="inventory-form" data-loose-add><label class="field-label">Part<select class="inventory-input" name="part">${data.parts.map(r=>`<option value="${escapeHTML(r.part_id)}">${escapeHTML(r.part_id)} · ${escapeHTML(r.name)}</option>`).join('')}</select></label><label class="field-label">Color<select class="inventory-input" name="color">${data.colors.map(r=>`<option value="${r.color_id}">${escapeHTML(r.name)} (${r.color_id})</option>`).join('')}</select></label><label class="field-label">Quantity to add<input class="inventory-input" type="number" name="quantity" min="0" step="1" value="1" required></label><button class="primary-button">Add loose parts</button></form>`:'<p class="detail-explanation">No known catalog part matches.</p>';
  }catch(error){inventoryError(error,$('#loose-message'));}
}

async function makePlan(code,button){
  const version=modalVersion;button.disabled=true;button.textContent='Finding a plan…';
  try{const plan=await api('/api/plan',{code,mode:state.results.mode});if(version!==modalVersion)return;state.plan=plan;renderPlan(plan);}
  catch(error){if(version===modalVersion)inventoryError(error,$('#plan-output'));}
  finally{if(button.isConnected){button.disabled=false;button.textContent='Plan this build ↗';}}
}

function renderPlan(plan){
  const output=$('#plan-output');if(!output)return;
  const color=id=>plan.colors[String(id)]||String(id);
  if(plan.status==='error'){output.innerHTML=`<p class="inventory-notice">${escapeHTML(plan.message)}</p>`;return;}
  if(plan.status==='insufficient inventory'){
    output.innerHTML=`<div class="inventory-notice"><strong>A full plan is unavailable.</strong><p>Recommendations include protected copies. Unprotect a copy to make its pieces eligible.</p></div>${pieceTable(plan.shortages.map(r=>({'Part ID':r.part_id,'Required color':r.requested_color===null?'Any':color(r.requested_color),'Missing from eligible sources':r.quantity,'Only in protected copies':r.protected_quantity,'Still missing with protection removed':r.quantity-r.protected_quantity})))}`;return;
  }
  const sources=['loose',...plan.selected_copy_ids];
  output.innerHTML=`<div class="plan-summary"><strong>${plan.minimum_proven?'Minimum dismantling proven.':'Best plan found; minimum not proven.'}</strong><p>Dismantle <b>${plan.dismantling_count}</b> physical ${plan.dismantling_count===1?'copy':'copies'}. ${plan.color_substitutions} color substitutions · ${plan.elapsed_seconds.toFixed(3)}s.</p><p>Advisory only. Pieces are not consumed or reserved.</p></div>${sources.map(source=>{const rows=plan.allocations.filter(r=>r.source_id===source);return rows.length?`<section class="source-picks"><h4>${source==='loose'?'Loose pieces used':`Dismantle ${escapeHTML(plan.source_labels[source])}`}</h4>${source!=='loose'?`<p class="copy-id">${escapeHTML(source)}</p>`:''}${pieceTable(rows.map(r=>({'Part ID':r.part_id,'Requested color':color(r.requested_color),'Supplied color':color(r.supplied_color),'Quantity':r.quantity})))}</section>`:'';}).join('')}`;
}

$('#manage-collections').addEventListener('click',()=>{renderCollectionManager();openDialog($('#collection-dialog'));});
$('#manage-loose').addEventListener('click',()=>{renderLooseEntries();$('#loose-message').textContent='';openDialog($('#loose-dialog'));});
$('#loose-search').addEventListener('input',()=>{clearTimeout(looseTimer);looseVersion++;looseTimer=setTimeout(searchLoose,180);});
$('#account-dialog').addEventListener('close',()=>$('#account-content').replaceChildren());
$('#navigation-dialog').addEventListener('close',()=>{if(state.session?.pending)navigateDraft(null,'cancel');});
$('#navigation-dialog').addEventListener('cancel',event=>{event.preventDefault();navigateDraft(null,'cancel');});
document.addEventListener('toggle',event=>{if(event.target.matches?.('[data-copy-editor]')&&event.target.open)loadCopyInventory(event.target.dataset.copyEditor);},true);
document.addEventListener('change',event=>{const form=event.target.closest('[data-copy-missing]');if(form&&event.target.name==='part')syncMissingQuantity(form);});

document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try{
    if(button.matches('[data-new]'))await navigateDraft({kind:'new'});
    if(button.matches('[data-save]'))await saveDraft();
    if(button.matches('[data-show-save-as]')){const form=$('[data-save-as]');form.hidden=false;form.elements.name.focus();}
    if(button.matches('[data-refresh-saved]'))await refreshSaved();
    if(button.matches('[data-load-saved]'))await navigateDraft({kind:'load',id:$('#saved-selection').value});
    if(button.matches('[data-reload-saved]'))await navigateDraft({kind:'load',id:state.document.id});
    if(button.matches('[data-sign-in]'))showAccount();
    if(button.matches('[data-sign-out]'))await navigateDraft({kind:'logout'});
    if(button.matches('[data-navigation]'))await navigateDraft(null,button.dataset.navigation);
    if(button.matches('[data-delete-saved]'))openDialog($('#delete-saved-dialog'));
    if(button.id==='confirm-delete-saved'){const data=await api('/api/delete',{confirmed:true});applySession(data);$('#delete-saved-dialog').close();toast('Cloud collection deleted. Your local draft remains.');}
    if(button.matches('[data-copy-remove]')){const id=button.dataset.copyRemove,copy=state.document.copies.find(c=>c.id===id);await editInventory({action:'remove_copy',copy_id:id});if($('#detail-dialog').open)await refreshCopyDetails(copy.set_num);}
    if(button.matches('[data-missing-remove]')){const id=button.dataset.missingRemove,copy=state.document.copies.find(c=>c.id===id);await editInventory({action:'remove_missing',copy_id:id,part_id:button.dataset.part,color_id:Number(button.dataset.color)});await refreshCopyDetails(copy.set_num,id);}
    if(button.matches('[data-accept-version]')){const id=button.dataset.acceptVersion,copy=state.document.copies.find(c=>c.id===id);await editInventory({action:'accept_version',copy_id:id});await refreshCopyDetails(copy.set_num,id);}
    if(button.matches('[data-plan-build]'))await makePlan(button.dataset.planBuild,button);
  }catch(error){inventoryError(error,button.id==='confirm-delete-saved'?$('#delete-message'):$('#collection-message'));}
});

document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches('.inventory-form,.loose-row'))return;
  event.preventDefault();const submit=form.querySelector('button[type="submit"],button:not([type])');if(submit)submit.disabled=true;
  try{
    if(form.id==='account-form'){
      const credentials={email:$('#account-email').value,password:$('#account-password').value,signup:$('#account-action').value==='signup'};
      $('#account-password').value='';
      try{const data=await api('/api/auth',credentials);applySession(data,{invalidate:false});$('#account-dialog').close();$('#account-content').replaceChildren();toast('Signed in. Your current draft is preserved.');}
      finally{credentials.password='';}
    }
    if(form.matches('[data-rename]'))await editInventory({action:'rename',name:form.elements.name.value});
    if(form.matches('[data-save-as]'))await saveDraft(form.elements.name.value);
    if(form.matches('[data-copy-update]')){const id=form.dataset.copyUpdate,copy=state.document.copies.find(c=>c.id===id);await editInventory({action:'update_copy',copy_id:id,label:form.elements.label.value,keep_assembled:form.elements.protected.checked});await refreshCopyDetails(copy.set_num,id);}
    if(form.matches('[data-copy-missing]')){const id=form.dataset.copyMissing,copy=state.document.copies.find(c=>c.id===id),[part,color]=JSON.parse(form.elements.part.value);await editInventory({action:'missing',copy_id:id,part_id:part,color_id:color,quantity:Number(form.elements.quantity.value)});await refreshCopyDetails(copy.set_num,id);}
    if(form.matches('[data-loose-add]')){await editInventory({action:'loose_add',part_id:form.elements.part.value,color_id:Number(form.elements.color.value),quantity:Number(form.elements.quantity.value)});toast('Loose pieces added.');}
    if(form.matches('[data-loose-total]')){const [part,color]=JSON.parse(form.dataset.looseTotal);await editInventory({action:'loose_set',part_id:part,color_id:color,quantity:Number(form.elements.quantity.value)});}
  }catch(error){inventoryError(error,form.id==='account-form'?$('#account-message'):form.closest('#loose-dialog')?$('#loose-message'):$('#collection-message'));}
  finally{if(submit?.isConnected)submit.disabled=false;}
});

// Start only after both the original UI and its inventory extension are loaded.
init();
