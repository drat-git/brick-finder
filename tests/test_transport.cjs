const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../frontend/streamlit.js'), 'utf8');

function harness(embedded = true) {
  const listeners = {}, sent = [], timers = new Map();
  const parent = {postMessage:(data, origin) => sent.push({data, origin})};
  const window = {parent, innerHeight:800, addEventListener:(name, callback) => {listeners[name] = callback;}};
  if (!embedded) window.parent = window;
  vm.runInNewContext(source, {window, location:{search:embedded ? '?streamlitUrl=https%3A%2F%2Fbrick.streamlit.app%2F' : ''},
    URLSearchParams, URL, crypto:{randomUUID:() => 'session'}, DOMException,
    setTimeout:callback => {const id=timers.size+1;timers.set(id,callback);return id;},
    clearTimeout:id => timers.delete(id)});
  const render = (response, origin='https://brick.streamlit.app', sender=parent) => listeners.message({source:sender,origin,data:{type:'streamlit:render',args:{response}}});
  return {window, sent, timers, render, requests:() => sent.filter(m => m.data.type==='streamlit:setComponentValue')};
}

test('the HTTP preview keeps using its existing transport', () => {
  const h = harness(false);
  assert.equal(h.window.brickfinderTransport, undefined);
  assert.equal(h.sent.length, 0);
});

test('component requests wait for readiness and resolve only their correlated response', async () => {
  const h = harness();
  const promise = h.window.brickfinderTransport('/api/catalog');
  assert.equal(h.requests().length, 0);
  h.render();
  assert.equal(h.requests().length, 1);
  assert.equal(h.requests()[0].origin, 'https://brick.streamlit.app');
  h.render({id:'stale-response',data:{wrong:true}});
  h.render({id:'session-1',data:{candidates:10116}});
  assert.deepEqual(await promise, {candidates:10116});
  assert.equal(h.timers.size, 0);
});

test('requests are serialized so reruns cannot overwrite pending actions', async () => {
  const h = harness();h.render();
  const first = h.window.brickfinderTransport('/api/search?q=city');
  const second = h.window.brickfinderTransport('/api/recommend', {collection:{'31124-1':1}});
  assert.equal(h.requests().length, 1);
  h.render({id:'session-1',data:{sets:[]}});
  assert.equal(h.requests().length, 2);
  assert.equal(h.requests()[1].data.value.path, '/api/recommend');
  h.render({id:'session-2',data:{total:1}});
  assert.deepEqual(await first, {sets:[]});assert.deepEqual(await second, {total:1});
});

test('cancelled searches reject promptly while later actions still finish', async () => {
  const h = harness();h.render();
  const abort = new AbortController();
  const cancelled = h.window.brickfinderTransport('/api/search?q=c', undefined, abort.signal);
  abort.abort();
  await assert.rejects(cancelled, {name:'AbortError'});
  const next = h.window.brickfinderTransport('/api/search?q=city');
  assert.equal(h.requests().length, 1);
  h.render({id:'session-1',data:{sets:[]}});
  h.render({id:'session-2',data:{sets:['city']}});
  assert.deepEqual(await next, {sets:['city']});
});

test('messages from another window or origin cannot acknowledge requests', async () => {
  const h = harness();
  const result = h.window.brickfinderTransport('/api/catalog');
  h.render(undefined, 'https://other.example');h.render(undefined, 'https://brick.streamlit.app', {});
  assert.equal(h.requests().length, 0);
  h.render();h.render({id:'session-1',data:{ok:true}});
  assert.deepEqual(await result, {ok:true});
});

test('backend errors and connection timeouts let visitors retry', async () => {
  const h = harness();h.render();
  const bad = h.window.brickfinderTransport('/api/recommend', {});
  h.render({id:'session-1',error:'Choose a valid collection.'});
  await assert.rejects(bad, /Choose a valid collection/);
  const timedOut = h.window.brickfinderTransport('/api/catalog');
  [...h.timers.values()][0]();
  await assert.rejects(timedOut, /connection timed out/);
  const retry = h.window.brickfinderTransport('/api/catalog');
  h.render({id:'session-3',data:{ok:true}});
  assert.deepEqual(await retry, {ok:true});
});


test('credential requests are scrubbed after response and conflict codes survive the bridge', async () => {
  const h=harness();h.render();
  const credentials={email:'person@example.com',password:'private-password'};
  const login=h.window.brickfinderTransport('/api/auth',credentials);
  h.render({id:'session-1',data:{email:'person@example.com'}});
  await login;
  assert.equal(credentials.password,'');
  const save=h.window.brickfinderTransport('/api/save',{});
  h.render({id:'session-2',error:'Newer revision exists',code:'revision_conflict'});
  await assert.rejects(save,{code:'revision_conflict'});
});
