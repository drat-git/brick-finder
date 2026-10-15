const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value).toLocaleString('en-US');
const paths = {
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  trash:'<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5"/>',
  brick:'<path d="m3 10 9-5 9 5-9 5-9-5Zm0 0v7l9 5 9-5v-7M12 15v7"/><ellipse cx="9" cy="6" rx="2" ry="1.5"/><ellipse cx="15" cy="9" rx="2" ry="1.5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  shield:'<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z"/><path d="m8 12 3 3 5-6"/>',
  sliders:'<path d="M3 7h7m5 0h6M3 17h3m5 0h10"/><circle cx="12" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  swap:'<path d="M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths[name] || paths.brick}</svg>`;
const photo = (set, extra = '') => `<img src="${escapeHTML(set.image || './favicon.svg')}" alt="${escapeHTML(set.name)}" ${extra} loading="lazy">`;
const state = {catalog:null, collection:new Map(), mode:'exact', minimum:100, sizes:[20,1000], tab:'ready', sort:'match', page:1, results:null, loading:false, searched:false};
let searchTimer, searchRequest, matchRequest, requestVersion = 0, modalVersion = 0, toastTimer, searchItems = [];

async function api(path, body, signal) {
  if (window.brickfinderTransport) return window.brickfinderTransport(path, body, signal);
  const response = await fetch(path, body === undefined ? {signal} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), signal,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}

function toast(message) {
  const node = $('#toast');
  node.textContent = message; node.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => {node.hidden = true;}, 3600);
}

function collectionBody() {
  return Object.fromEntries([...state.collection].map(([code, item]) => [code, item.quantity]));
}

function persist() {
  try {sessionStorage.setItem('brickfinder-redesign-collection', JSON.stringify(collectionBody()));} catch {}
}

function totals() {
  return [...state.collection.values()].reduce((sum, item) => ({copies:sum.copies+item.quantity, pieces:sum.pieces+item.quantity*item.set.parts}), {copies:0,pieces:0});
}

function collectionChanged() {
  requestVersion++; matchRequest?.abort(); state.results = null; state.searched = false; state.loading = false; state.page = 1;
  persist(); renderCollection(); renderToolbar(); renderWelcome();
}

function addSet(set) {
  const existing = state.collection.get(set.code);
  state.collection.set(set.code, {set, quantity:(existing?.quantity || 0)+1});
  collectionChanged(); hideSearch(); $('#set-search').value = '';
  toast(existing ? `Added another copy of ${set.name}.` : `${set.name} added to your collection.`);
}

function renderCollection() {
  const {copies, pieces} = totals();
  $('#collection-count').textContent = copies;
  $('#set-total').textContent = number(copies);
  $('#piece-total').textContent = number(pieces);
  $('#clear-button').hidden = !copies;
  $('#find-button').disabled = !copies || state.loading;
  $('#find-label').textContent = state.loading ? 'Finding your next build…' : 'Find my next build';
  $('#find-arrow').textContent = state.loading ? '⋯' : '↗';
  $('#collection-list').innerHTML = copies ? [...state.collection.values()].map(({set, quantity}) => `
    <article class="owned-row" data-owned="${escapeHTML(set.code)}">
      ${photo(set, `data-set-photo="${escapeHTML(set.code)}"`)}
      <div class="owned-copy"><button class="owned-name" data-set-detail="${escapeHTML(set.code)}">${escapeHTML(set.name)}</button>
        <p class="owned-meta">${number(set.parts)} pieces <span aria-hidden="true">·</span> ${escapeHTML(set.theme)}</p>
        <div class="owned-bottom"><span class="owned-code">${escapeHTML(set.code)}</span>
          <div class="quantity-control" role="group" aria-label="Copies of ${escapeHTML(set.name)}">
            <button data-quantity="${escapeHTML(set.code)}" data-delta="-1" aria-label="Remove one copy of ${escapeHTML(set.name)}">−</button>
            <span aria-label="${quantity} ${quantity === 1 ? 'copy' : 'copies'}">${quantity}</span>
            <button data-quantity="${escapeHTML(set.code)}" data-delta="1" aria-label="Add one copy of ${escapeHTML(set.name)}">+</button>
          </div>
        </div>
      </div>
      <button class="remove-owned" data-remove="${escapeHTML(set.code)}" aria-label="Remove ${escapeHTML(set.name)} from collection">${icon('close')}</button>
    </article>`).join('') : `
    <div class="collection-empty"><span class="empty-brick">${icon('brick')}</span><strong>A little collection. A lot of potential.</strong><p>Search for your first set above,<br>or try an example below.</p></div>`;
}

function renderExamples() {
  $('#example-list').innerHTML = state.catalog.examples.map((example, i) => `
    <button class="example-button" data-example="${i}">${photo(example.sets[0])}
      <span><strong>${escapeHTML(example.name)}</strong><small>${escapeHTML(example.theme)} <span aria-hidden="true">·</span> ${example.sets.length} sets</small></span><span class="arrow" aria-hidden="true">↗</span>
    </button>`).join('');
}

function loadExample(index) {
  const example = state.catalog.examples[index];
  if (!example) return;
  state.collection = new Map(example.sets.map(set => [set.code, {set,quantity:1}]));
  collectionChanged();
  toast(`${example.name} loaded. You’re ready to find builds.`);
}

function renderWelcome() {
  const featured = state.catalog?.featured || [];
  const count = totals().copies;
  $('#results-note').hidden = true;
  $('#load-more').hidden = true;
  $('#results').setAttribute('aria-busy', 'false');
  $('#results').innerHTML = `
    <div class="welcome">
      <div class="welcome-stage"><div class="welcome-copy">
        <div class="welcome-kicker"><span></span> A NEW WAY TO PLAY</div>
        <h3>${count ? 'Your collection.<br><em>Reimagined.</em>' : 'Already yours.<br><em>Not built yet.</em>'}</h3>
        <p>${count ? `${number(count)} sets. ${number(totals().pieces)} pieces. Let’s find out what else they can become.` : 'Your next favorite build might already be in your brick box. Let’s find it.'}</p>
        <span class="start-hint">← ${count ? 'Find builds to see your matches' : 'Add a set to get started'}</span>
      </div><div class="welcome-art" aria-hidden="true">
        ${featured.slice(0,2).map(set => `<div class="art-card">${photo(set)}</div>`).join('')}
        <span class="floating-tag">${icon('check')} A little creativity goes a long way.</span>
      </div></div>
      <div class="welcome-steps">
        <div class="step-item"><span class="step-number">01</span><div><strong>Add your sets</strong><p>Tell us what’s in your collection.</p></div></div>
        <div class="step-item"><span class="step-number">02</span><div><strong>Find a new possibility</strong><p>We match the pieces you own.</p></div></div>
        <div class="step-item"><span class="step-number">03</span><div><strong>Make it yours</strong><p>Grab the instructions. Get building.</p></div></div>
      </div>
      <div class="section-label"><h3>A little inspiration</h3><span>REAL SETS. FRESH IDEAS.</span></div>
      <div class="inspiration-grid">${featured.map(set => `
        <button class="inspiration-card" data-featured="${escapeHTML(set.code)}" aria-label="Explore ${escapeHTML(set.name)}">
          <div class="inspiration-image">${photo(set)}</div><div class="inspiration-info"><strong>${escapeHTML(set.name)}</strong><small>${escapeHTML(set.theme)} · ${number(set.parts)} pieces</small><span>Explore set ↗</span></div>
        </button>`).join('')}</div>
      <p class="sample-disclaimer">These are ideas from the catalog, not matches yet. Add your collection to see what you can actually build.</p>
    </div>`;
}

function renderToolbar() {
  $$('#results-toolbar .result-tabs button').forEach(button => button.classList.remove('active'));
  $(state.tab === 'ready' ? '#complete-tab' : '#almost-tab').classList.add('active');
  $('#completion').value = state.minimum;
  $('#completion-value').textContent = `${state.minimum}%`;
  $('#pieces-min').value = state.sizes[0]; $('#pieces-max').value = state.sizes[1];
  $('#filter-dot').hidden = state.minimum === 100 && state.sizes[0] === 20 && state.sizes[1] === 1000;
  $('#result-count').textContent = state.results ? number(state.results.ready_count) : '—';
  $$('[data-mode]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mode === state.mode)));
  $('#color-description').textContent = state.mode === 'exact' ? 'Same pieces. Same colors. Ready to build.' : 'Same pieces. A different color palette.';
}

function availability(match) {
  if (!match.complete) return `<span class="availability partial">${icon('brick')}${number(match.missing)} ${match.missing === 1 ? 'piece' : 'pieces'} missing</span>`;
  if (match.exact_matched < match.required) return `<span class="availability swaps">${icon('swap')}Complete with color swaps</span>`;
  return `<span class="availability">${icon('check')}Ready to build. Every piece.</span>`;
}

function renderResults() {
  const data = state.results;
  if (!data) {renderWelcome(); return;}
  $('#results').setAttribute('aria-busy', 'false');
  $('#results-note').hidden = false;
  $('#results-note').innerHTML = `<strong>${number(data.total)} ${data.total === 1 ? 'build' : 'builds'} ${state.tab === 'ready' ? 'ready for a fresh start' : 'within reach'}</strong> <span aria-hidden="true">·</span> ${state.mode === 'exact' ? 'Original colors' : 'Flexible colors'} <span aria-hidden="true">·</span> ${state.tab === 'ready' ? '100% of the pieces available' : 'Extra pieces needed'}`;
  if (!data.total) {
    $('#results').innerHTML = `<div class="empty-results"><div class="empty-symbol">${icon('brick')}</div><h3>${state.tab === 'ready' ? 'A few more possibilities await.' : 'No close matches with these filters.'}</h3><p>${state.tab === 'ready' ? 'No complete builds with these settings just yet. Try a different color palette, explore close matches, or add a few more sets.' : 'Try a wider piece range, lower the completion threshold, or add more sets to your collection.'}</p><div class="empty-actions">${state.mode === 'exact' ? '<button class="primary-button" data-try-flexible>Try flexible colors ↗</button>' : ''}${state.tab === 'ready' ? '<button class="secondary-button" data-close-matches>Explore close matches</button>' : '<button class="secondary-button" data-reset-results>Reset filters</button>'}</div></div>`;
  } else {
    $('#results').innerHTML = `<div class="build-grid">${data.matches.map(match => `
      <article class="build-card"><div class="build-photo"><span class="build-category">${escapeHTML(match.theme)}</span>${photo(match)}</div>
        <div class="build-info"><h3>${escapeHTML(match.name)}</h3><p class="build-meta">${escapeHTML(match.code)} <span aria-hidden="true">·</span> ${number(match.required)} pieces</p>
          ${availability(match)}<div class="availability-bar" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, match.percent))}%"></span></div>
          <div class="build-actions"><span>${escapeHTML(match.display_percent.replace('.0%', '%'))} complete</span><button class="view-build" data-build="${escapeHTML(match.code)}" aria-label="View ${escapeHTML(match.name)}">View build ${icon('arrow')}</button></div>
        </div>
      </article>`).join('')}</div>`;
  }
  $('#load-more').hidden = data.matches.length >= data.total;
  renderToolbar();
}

async function findBuilds(scrollToResults = false) {
  if (!state.collection.size) return;
  matchRequest?.abort(); matchRequest = new AbortController(); const version = ++requestVersion;
  state.loading = true; state.searched = true; renderCollection();
  $('#results').setAttribute('aria-busy', 'true'); $('#load-more').hidden = true;
  $('#results-note').hidden = true;
  $('#results').innerHTML = '<div class="loading-state"><span class="loader-brick" aria-hidden="true"><i></i><i></i><i></i><i></i></span><strong>Finding a fresh start for your bricks.</strong><p>Comparing your collection with the catalog…</p></div>';
  try {
    const response = await api('/api/recommend', {collection:collectionBody(), mode:state.mode, minimum:state.minimum, sizes:state.sizes, page:state.page, sort:state.sort, only_partial:state.tab === 'almost'}, matchRequest.signal);
    if (version !== requestVersion) return;
    state.results = response; state.loading = false; renderCollection(); renderResults();
    if (scrollToResults && window.matchMedia('(max-width:720px)').matches) {
      $('#discovery').focus({preventScroll:true});
      $('#discovery').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
    }
  } catch (error) {
    if (error.name === 'AbortError' || version !== requestVersion) return;
    state.loading = false; state.results = null; renderCollection();
    $('#results').setAttribute('aria-busy', 'false');
    $('#results').innerHTML = `<div class="empty-results"><h3>Let’s give that another try.</h3><p>${escapeHTML(error.message)}</p><div class="empty-actions"><button class="primary-button" data-retry>Try again</button></div></div>`;
  }
}

function changeMode(mode) {
  state.mode = mode; state.page = 1; renderToolbar();
  if (state.searched) findBuilds();
}

function changeTab(tab) {
  state.tab = tab; state.minimum = tab === 'ready' ? 100 : 80; state.page = 1;
  renderToolbar(); if (state.searched) findBuilds();
}

function resetFilters() {
  state.minimum = 100; state.sizes = [20,1000]; state.tab = 'ready'; state.page = 1;
  renderToolbar(); if (state.searched) findBuilds();
}

function hideSearch() {$('#search-results').hidden = true; $('#set-search').setAttribute('aria-expanded', 'false');}

async function search() {
  const query = $('#set-search').value.trim();
  searchRequest?.abort();
  if (!query) {hideSearch(); return;}
  searchRequest = new AbortController();
  $('#search-results').hidden = false; $('#set-search').setAttribute('aria-expanded', 'true');
  $('#search-results').innerHTML = '<p class="search-message">Finding your set…</p>';
  try {
    const data = await api(`/api/search?q=${encodeURIComponent(query)}`, undefined, searchRequest.signal);
    if ($('#set-search').value.trim() !== query) return;
    searchItems = data.sets;
    $('#search-results').innerHTML = searchItems.length ? searchItems.map((set, i) => `<div class="search-row">${photo(set)}<div class="search-copy"><strong>${escapeHTML(set.name)}</strong><small>${escapeHTML(set.code)} · ${number(set.parts)} pieces</small></div><button class="add-search" data-add-search="${i}" aria-label="Add ${escapeHTML(set.name)}">+</button></div>`).join('') : '<p class="search-message">No sets found. Try a set number or a shorter name.</p>';
  } catch (error) {
    if (error.name !== 'AbortError') $('#search-results').innerHTML = `<p class="search-message">${escapeHTML(error.message)}</p>`;
  }
}

function openDialog(dialog) {
  hideSearch(); if (!dialog.open) dialog.showModal();
}

function facts(set, quantity) {
  return `<dl class="set-facts"><div><dt>Set number</dt><dd>${escapeHTML(set.code)}</dd></div><div><dt>Released</dt><dd>${set.year}</dd></div><div><dt>Pieces</dt><dd>${number(set.parts)}</dd></div><div><dt>Theme</dt><dd>${escapeHTML(set.theme)}</dd></div>${quantity ? `<div class="wide"><dt>Your collection</dt><dd>${quantity} ${quantity === 1 ? 'copy' : 'copies'} · ${number(quantity*set.parts)} pieces</dd></div>` : ''}</dl>`;
}

function openSet(set) {
  if (!set) return;
  modalVersion++;
  const quantity = state.collection.get(set.code)?.quantity || 0;
  $('#detail-content').innerHTML = `<div class="modal-eyebrow">${quantity ? 'IN YOUR COLLECTION' : 'A LITTLE INSPIRATION'}</div><h2 class="modal-title">${escapeHTML(set.name)}</h2>
    <div class="detail-layout"><div><div class="detail-photo">${photo(set)}</div><p class="detail-photo-caption">Original set colors shown.</p></div><div class="detail-copy">${facts(set, quantity)}
      ${set.owned_only ? '<p class="detail-explanation">This item contributes its inventoried pieces to your collection, but isn’t offered as a build recommendation.</p>' : ''}
      <button class="primary-button" data-own-set="${escapeHTML(set.code)}">${quantity ? 'Add another copy' : 'I own this set'} ${icon('arrow')}</button>
      <p class="detail-explanation">${quantity ? 'Opening these details doesn’t change your collection or matches.' : 'This is a catalog example. Add the sets you own to check what you can build.'}</p>
      <a class="text-button" href="${escapeHTML(set.instructions)}" target="_blank" rel="noopener noreferrer" style="margin-top:14px">Building instructions ↗</a>
    </div></div>`;
  $('#detail-content').dataset.setCode = set.code;
  openDialog($('#detail-dialog'));
}

function pieceTable(rows) {
  if (!rows.length) return '';
  const columns = Object.keys(rows[0]);
  return `<div class="piece-table-wrap" tabindex="0"><table class="piece-table"><thead><tr>${columns.map(c => `<th scope="col">${escapeHTML(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${columns.map(c => `<td>${escapeHTML(row[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

async function openBuild(code) {
  const match = state.results?.matches.find(m => m.code === code);
  if (!match) return;
  const version = ++modalVersion;
  $('#detail-content').innerHTML = '<div class="loading-state"><strong>Getting your build ready…</strong></div>';
  openDialog($('#detail-dialog'));
  try {
    const data = await api('/api/breakdown', {collection:collectionBody(), code, mode:state.results.mode});
    if (version !== modalVersion) return;
    const m = data.match;
    $('#detail-content').innerHTML = `<div class="modal-eyebrow">${m.complete ? 'YOUR NEXT BUILD' : 'A FEW PIECES AWAY'}</div><h2 class="modal-title">${escapeHTML(m.name)}</h2>
      <div class="detail-layout"><div><div class="detail-photo">${photo(m)}</div><p class="detail-photo-caption">Original set colors shown.</p></div><div class="detail-copy">${facts(m)}${availability(m)}
        <p class="detail-explanation">${number(m.matched)} of ${number(m.required)} required pieces available. ${m.mode === 'flexible' ? `${m.exact_percent.toFixed(1)}% available in the original colors.` : 'Each counted piece matches its original color.'} Every recommendation is a separate build, using the same collection.</p>
        <a class="primary-button" href="${escapeHTML(m.instructions)}" target="_blank" rel="noopener noreferrer">Building instructions ↗</a>
      </div></div>
      <section class="detail-pieces"><h3>${data.shortages.length ? 'The pieces you still need' : 'Every required piece accounted for.'}</h3><p>${data.shortages.length ? `${number(m.missing)} missing pieces are listed below.` : m.mode === 'flexible' && data.substitutions.length ? 'You have all the required part IDs. Use the color swaps below to build with your collection.' : 'Your collection covers the full inventory in the original colors.'}</p>${pieceTable(data.shortages)}</section>
      ${data.substitutions.length ? `<section class="detail-pieces"><h3>A different color palette</h3><p>Original colors are reserved first. Each remaining piece is allocated once in these suggested swaps.</p>${pieceTable(data.substitutions)}</section>` : ''}`;
  } catch (error) {
    if (version === modalVersion) $('#detail-content').innerHTML = `<h2 class="modal-title">Couldn’t open this build.</h2><p class="detail-explanation">${escapeHTML(error.message)}</p><button class="secondary-button" data-build="${escapeHTML(code)}">Try again</button>`;
  }
}

function showHow() {
  $('#info-content').innerHTML = `<span class="eyebrow">LESS SCROLLING. MORE BUILDING.</span><h2>Your bricks have more to give.</h2><div class="how-step"><span>01</span><div><h3>Start with what you own.</h3><p>Search for complete LEGO sets you’re happy to take apart. Add more than one copy if you have it.</p></div></div><div class="how-step"><span>02</span><div><h3>Find what you can build.</h3><p>We combine those inventories and compare them with official sets. Exact colors and fully complete builds are the default.</p></div></div><div class="how-step"><span>03</span><div><h3>Make something new.</h3><p>Explore the piece breakdown and open LEGO’s instructions. Flexible colors open up more options; Almost there shows builds needing extra pieces.</p></div></div><p>Matches use exact part IDs and quantities. Printed parts and mold variants remain distinct. Each suggestion uses the same available collection independently.</p>`;
  openDialog($('#info-dialog'));
}

function showCatalog() {
  const c = state.catalog;
  if (!c) return;
  $('#info-content').innerHTML = `<span class="eyebrow">A WORLD OF POSSIBILITIES</span><h2>The catalog behind your next build.</h2><div class="catalog-summary"><div><strong>${number(c.owned_sets)}</strong><span>selectable owned inventories</span></div><div><strong>${number(c.candidates)}</strong><span>recommendation candidates</span></div></div><p>All themes can qualify. Recommendations are official sets from 2000–2026 with 20–1,000 pieces. Owned inventories have no year or size limit.</p><div class="coverage-list">${c.coverage.category_coverage.map(row => `<div class="coverage-row"><span>${escapeHTML(row.category)}</span><span>${number(row.owned_sets)} owned · ${number(row.candidate_sets)} builds</span></div>`).join('')}</div><p>Bulk parts, books, merchandise, and multipacks contribute validated inventory but aren’t recommended as builds. Synthetic reference records and invalid inventories are excluded. Part IDs remain distinct across DUPLO and specialty systems.</p><p>Catalog prepared ${escapeHTML(c.coverage.built_at.slice(0,10))}. Data and set images: <a href="https://rebrickable.com/downloads/" target="_blank" rel="noopener noreferrer">Rebrickable</a>. Instructions: LEGO. Independent project; not affiliated with LEGO or Rebrickable.</p>`;
  openDialog($('#info-dialog'));
}

document.addEventListener('click', event => {
  const target = event.target.closest('button, [data-set-photo]');
  if (!target) {if (!event.target.closest('.search-area')) hideSearch(); return;}
  if (target.matches('[data-add-search]')) {const set=searchItems[Number(target.dataset.addSearch)];if(set)addSet(set);$('#set-search').focus();}
  if (target.matches('[data-example]')) loadExample(Number(target.dataset.example));
  if (target.matches('[data-remove]')) {state.collection.delete(target.dataset.remove);collectionChanged();}
  if (target.matches('[data-quantity]')) {
    const item=state.collection.get(target.dataset.quantity); if(item){item.quantity+=Number(target.dataset.delta);if(item.quantity<1)state.collection.delete(target.dataset.quantity);collectionChanged();const next=$$('[data-quantity]').find(b=>b.dataset.quantity===target.dataset.quantity&&b.dataset.delta===target.dataset.delta);(next||$('#set-search')).focus({preventScroll:true});}
  }
  if (target.matches('[data-set-detail], [data-set-photo]')) openSet(state.collection.get(target.dataset.setDetail || target.dataset.setPhoto)?.set);
  if (target.matches('[data-featured]')) openSet(state.catalog.featured.find(s => s.code === target.dataset.featured));
  if (target.matches('[data-own-set]')) {
    const set=state.collection.get(target.dataset.ownSet)?.set || state.catalog.featured.find(s => s.code === target.dataset.ownSet);
    if(set){addSet(set);$('#detail-dialog').close();}
  }
  if (target.matches('[data-build]')) openBuild(target.dataset.build);
  if (target.matches('[data-mode]')) changeMode(target.dataset.mode);
  if (target.matches('[data-try-flexible]')) changeMode('flexible');
  if (target.matches('[data-close-matches]')) changeTab('almost');
  if (target.matches('[data-reset-results]')) resetFilters();
  if (target.matches('[data-retry]')) findBuilds();
  if (target.matches('[data-close-dialog]')) target.closest('dialog').close();
});

$('#find-button').addEventListener('click', () => {state.page=1;findBuilds(true);});
$('#edit-collection').addEventListener('click', () => {
  $('#set-search').focus({preventScroll:true});
  $('.collection-panel').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
});
$('#set-search').addEventListener('input', () => {clearTimeout(searchTimer); searchItems=[];searchRequest?.abort();if(!$('#set-search').value.trim())hideSearch();else searchTimer=setTimeout(search,180);});
$('#set-search').addEventListener('keydown', event => {
  if(event.key==='Escape'){hideSearch();$('#set-search').blur();}
  if(event.key==='ArrowDown'&&!$('#search-results').hidden){event.preventDefault();$('#search-results button')?.focus();}
  if(event.key==='Enter'&&searchItems.length&&!$('#search-results').hidden){event.preventDefault();addSet(searchItems[0]);}
});
document.addEventListener('keydown', event => {
  if(event.key==='/'&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('dialog[open]')){event.preventDefault();$('#set-search').focus();}
});
$('#clear-button').addEventListener('click', () => openDialog($('#clear-dialog')));
$('#confirm-clear').addEventListener('click', () => {state.collection.clear();$('#clear-dialog').close();collectionChanged();toast('A fresh start. Your collection is clear.');});
$('#complete-tab').addEventListener('click', () => changeTab('ready'));
$('#almost-tab').addEventListener('click', () => changeTab('almost'));
$('#filters-button').addEventListener('click', () => {$('#filters-panel').hidden=!$('#filters-panel').hidden;$('#filters-button').setAttribute('aria-expanded',String(!$('#filters-panel').hidden));});
$('#completion').addEventListener('input', () => {$('#completion-value').textContent=`${$('#completion').value}%`;});
$('#completion').addEventListener('change', () => {state.minimum=Number($('#completion').value);state.tab=state.minimum===100?'ready':'almost';state.page=1;renderToolbar();if(state.searched)findBuilds();});
for(const id of ['pieces-min','pieces-max']) $(`#${id}`).addEventListener('change', () => {
  const min=Number($('#pieces-min').value),max=Number($('#pieces-max').value);
  if(!Number.isInteger(min)||!Number.isInteger(max)||min<20||max>1000||min>max){toast('Choose a piece range between 20 and 1,000.');renderToolbar();return;}
  state.sizes=[min,max];state.page=1;renderToolbar();if(state.searched)findBuilds();
});
$('#reset-filters').addEventListener('click', resetFilters);
$('#sort').addEventListener('change', () => {state.sort=$('#sort').value;state.page=1;if(state.searched)findBuilds();});
$('#load-more').addEventListener('click', () => {state.page++;findBuilds();});
$('#how-button').addEventListener('click', showHow);
$('#catalog-button').addEventListener('click', showCatalog);
$$('dialog').forEach(dialog => {
  dialog.addEventListener('click', event => {if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  dialog.addEventListener('close', () => {modalVersion++;});
});
document.addEventListener('error', event => {if(event.target.tagName==='IMG'&&!event.target.src.endsWith('/favicon.svg')){event.target.src='./favicon.svg';event.target.alt='Set photo unavailable';}},true);

async function init() {
  if (location.protocol === 'file:') {
    document.body.innerHTML = `<main class="empty-results"><span class="eyebrow">BRICK FINDER</span><h1>Open the running preview.</h1><p>This HTML file needs the local app server to load the catalog and find builds.</p><div class="empty-actions"><a class="primary-button" href="http://127.0.0.1:8502/">Open Brick Finder ↗</a></div></main>`;
    return;
  }
  $('#search-icon').innerHTML=icon('search');$('#privacy-icon').innerHTML=icon('shield');$('#stamp-icon').innerHTML=icon('brick');$('#filter-icon').innerHTML=icon('sliders');$('#clear-button').innerHTML=icon('trash');
  $$('.dialog-close').forEach(button => {button.innerHTML=icon('close');});
  renderCollection();renderToolbar();
  try {
    state.catalog=await api('/api/catalog');
    $('#catalog-count').textContent=`${number(state.catalog.candidates)} builds to discover`;
    let saved;try{saved=JSON.parse(sessionStorage.getItem('brickfinder-redesign-collection')||'{}');}catch{saved={};}
    if(Object.keys(saved||{}).length){try{const restored=await api('/api/collection',{collection:saved});state.collection=new Map(restored.sets.map(({quantity,...set})=>[set.code,{set,quantity}]));}catch{try{sessionStorage.removeItem('brickfinder-redesign-collection');}catch{}}}
    renderExamples();renderCollection();renderWelcome();
  } catch(error) {
    $('#catalog-count').textContent='Catalog unavailable';
    $('#results').innerHTML=`<div class="empty-results"><h3>Let’s get the catalog open.</h3><p>${escapeHTML(error.message)}</p><div class="empty-actions"><button class="primary-button" onclick="location.reload()">Try again</button></div></div>`;
  }
}
init();
