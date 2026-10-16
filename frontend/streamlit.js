// The preview uses HTTP; Streamlit hosts the same UI through its component API.
(() => {
  const parentUrl = new URLSearchParams(location.search).get('streamlitUrl');
  if (!parentUrl || window.parent === window) return;
  const parentOrigin = new URL(parentUrl).origin;
  const queue = [];
  const session = crypto.randomUUID();
  let ready = false, active = null, sequence = 0;

  function send(type, data) {
    window.parent.postMessage({isStreamlitMessage:true, type, ...data}, parentOrigin);
  }

  function pump() {
    if (!ready || active) return;
    while (queue.length && queue[0].settled) queue.shift();
    active = queue.shift() || null;
    if (!active) return;
    const item = active;
    item.timer = setTimeout(() => {
      if (active !== item) return;
      active = null;
      item.finish(new Error('The app connection timed out. Please try again.'));
      pump();
    }, 30000);
    send('streamlit:setComponentValue', {dataType:'json', value:item.request});
  }

  window.brickfinderTransport = (path, body, signal) => new Promise((resolve, reject) => {
    const item = {request:{id:`${session}-${++sequence}`, path, body}, settled:false};
    const abort = () => item.finish(new DOMException('Request cancelled.', 'AbortError'));
    item.finish = (error, data) => {
      if (item.settled) return;
      item.settled = true;
      if(item.request.body && 'password' in item.request.body) item.request.body.password='';
      signal?.removeEventListener('abort', abort);
      error ? reject(error) : resolve(data);
    };
    if (signal?.aborted) {abort(); return;}
    signal?.addEventListener('abort', abort, {once:true});
    queue.push(item);
    pump();
  });

  window.addEventListener('message', event => {
    if (event.source !== window.parent || event.origin !== parentOrigin || event.data?.type !== 'streamlit:render') return;
    ready = true;
    const response = event.data.args?.response;
    if (active && response?.id === active.request.id) {
      const item = active;
      active = null;
      clearTimeout(item.timer);
      item.finish(response.error ? Object.assign(new Error(response.error),{code:response.code}) : null, response.data);
    }
    pump();
  });

  const resize = () => send('streamlit:setFrameHeight', {height:window.innerHeight});
  window.addEventListener('resize', resize);
  send('streamlit:componentReady', {apiVersion:1});
  resize();
})();
