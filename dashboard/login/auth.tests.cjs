'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'auth.js'),'utf8');

// A small DOM boundary double runs the actual client, not a copy of its logic.
function harness(responses,channel='online'){
  const elements=new Map(),calls=[],locations=[],timers=new Map(),saved=new Map();
  const create=id=>({id,dataset:{},value:'',textContent:'',hidden:true,disabled:false,open:false,attributes:new Map(),handlers:{},
    addEventListener(type,fn){this.handlers[type]=fn;},
    setAttribute(k,v){this.attributes.set(k,v);},getAttribute(k){return this.attributes.get(k)||null;},removeAttribute(k){this.attributes.delete(k);},
    focus(){this.focused=true;},scrollIntoView(){},showModal(){this.open=true;},close(){this.open=false;},reset(){},
    querySelector(selector){return element(this.id+selector);}});
  const element=id=>{if(!elements.has(id))elements.set(id,create(id));return elements.get(id);};
  const screens=['login','signup','forgot','access'].map(name=>{const e=element(`[data-screen="${name}"]`);e.dataset.screen=name;e.hidden=name!=='login';return e;});
  const document={body:{dataset:{channel}},documentElement:{},hidden:false,
    querySelector(selector){return element(selector.startsWith('#')?selector.slice(1):selector);},
    querySelectorAll(selector){
      if(selector==='[data-screen]')return screens;
      if(selector.includes('autocomplete="current-password"'))return [element('login-password')];
      return [];
    },
    getElementById(id){return element(id);},addEventListener(){}};
  let serial=0;
  vm.runInNewContext(source,{document,innerWidth:1200,AbortController,Error,Map,Set,Array,String,JSON,
    localStorage:{getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},
    location:{replace:url=>locations.push(url)},window:{addEventListener(){}},
    setTimeout:(fn,ms)=>{timers.set(++serial,{fn,ms});return serial;},clearTimeout:id=>timers.delete(id),
    fetch:async(url,options)=>{calls.push({url,options});const next=responses.shift();if(!next)throw Error('Unexpected request '+url);return {ok:next.status===undefined||next.status<400,status:next.status||200,json:async()=>next.body};}});
  return {element,calls,locations,timers,saved,flush:()=>new Promise(resolve=>setImmediate(resolve)),
    async submit(id){const e=element(id);await e.handlers.submit({preventDefault(){},currentTarget:e});await new Promise(resolve=>setImmediate(resolve));}};
}
const session=access=>({authenticated:true,user:{id:1,username:'viewer'},channel:'online',access,csrf_token:'test-csrf'});

test('a late anonymous session check keeps a password already typed into the login form',async()=>{
  const h=harness([{body:{authenticated:false}}]);
  h.element('login-identifier').value='viewer';
  h.element('login-password').value='test-password';
  await h.flush();
  assert.equal(h.element('login-password').value,'test-password');
  assert.deepEqual(h.locations,[]);
});

test('unlinked account opens Code dialog instead of entering Dashboard',async()=>{
  const h=harness([{body:session('unlinked')}]);await h.flush();
  assert.equal(h.element('join-dialog').open,true);assert.equal(h.element('hub-code').focused,true);assert.deepEqual(h.locations,[]);
});
test('pending account waits without exposing Dashboard and polls in five seconds',async()=>{
  const h=harness([{body:session('pending')}]);await h.flush();
  assert.equal(h.element('[data-screen="access"]').hidden,false);assert.equal(h.element('join-dialog').open,false);
  assert.ok([...h.timers.values()].some(t=>t.ms===5000));assert.deepEqual(h.locations,[]);
});
test('approved and Local admin sessions enter Dashboard',async()=>{
  for(const access of ['approved','admin']){const h=harness([{body:session(access)}]);await h.flush();assert.deepEqual(h.locations,['/']);}
});
test('revoked account cannot use the Code dialog to bypass local approval',async()=>{
  const h=harness([{body:session('revoked')}]);await h.flush();
  assert.equal(h.element('join-dialog').open,false);assert.equal(h.element('access-title').dataset.i18n,'revokedTitle');assert.deepEqual(h.locations,[]);
});
test('Code request carries session CSRF and waits for approval',async()=>{
  const h=harness([{body:session('unlinked')},{body:{ok:true}},{body:session('pending')}]);await h.flush();
  h.element('hub-code').value='ABCD-TEST';await h.submit('join-form');
  assert.equal(h.calls[1].url,'/auth/join');assert.equal(h.calls[1].options.headers['X-GG-CSRF'],'test-csrf');
  assert.equal(JSON.parse(h.calls[1].options.body).code,'ABCD-TEST');assert.equal(h.element('join-dialog').open,false);assert.deepEqual(h.locations,[]);
});
test('empty Code stays in modal and does not call server',async()=>{
  const h=harness([{body:session('unlinked')}]);await h.flush();await h.submit('join-form');
  assert.equal(h.calls.length,1);assert.equal(h.element('hub-code').getAttribute('aria-invalid'),'true');assert.equal(h.element('hub-code-error').hidden,false);
});
test('incorrect Code remains editable with translated inline error',async()=>{
  const h=harness([{body:session('unlinked')},{status:400,body:{detail:'Invalid code'}}]);await h.flush();
  h.element('hub-code').value='BAD';await h.submit('join-form');
  assert.equal(h.element('join-dialog').open,true);assert.equal(h.element('hub-code-error').hidden,false);assert.equal(h.element('hub-code').value,'BAD');assert.deepEqual(h.locations,[]);
});
test('globe toggles shared language and translates existing Code error',async()=>{
  const h=harness([{body:session('unlinked')}]);await h.flush();await h.submit('join-form');
  h.element('language-toggle').handlers.click();assert.equal(h.saved.get('gg-language'),'en');assert.equal(h.element('hub-code-error').textContent,'Enter your mill Code.');
});
test('login uses server session and never persists password or session token',async()=>{
  const h=harness([{body:{authenticated:false}},{body:{ok:true}},{body:session('unlinked')}]);await h.flush();
  h.element('login-identifier').value='viewer';h.element('login-password').value='test-password';await h.submit('login-form');
  const call=h.calls.find(c=>c.url==='/auth/login');
  assert.equal(call.options.headers['X-GG-CSRF'],'1');assert.deepEqual(JSON.parse(call.options.body),{identifier:'viewer',password:'test-password',channel:'online'});
  assert.equal(h.element('login-password').value,'');assert.equal(h.saved.size,0);assert.equal(h.element('join-dialog').open,true);
});
test('signup normalizes supplied phone and username before requesting access',async()=>{
  const h=harness([{body:{authenticated:false}},{body:{ok:true}},{body:session('unlinked')}]);await h.flush();
  h.element('signup-name').value='Test Viewer';h.element('signup-phone').value='+66 81-234-5678';
  h.element('input[name="role"]:checked').value='employee';h.element('signup-username').value='Viewer';
  h.element('signup-password').value='test-password';h.element('signup-confirm').value='test-password';await h.submit('signup-form');
  const call=h.calls.find(c=>c.url==='/auth/signup');assert.ok(call);
  assert.equal(JSON.parse(call.options.body).phone,'0812345678');assert.equal(JSON.parse(call.options.body).username,'viewer');
  assert.equal(h.element('join-dialog').open,true);assert.deepEqual(h.locations,[]);
});
test('rotating Code reopens Code dialog for a previously pending account',async()=>{
  const h=harness([{body:session('pending')},{body:session('unlinked')}]);await h.flush();
  await [...h.timers.values()].find(t=>t.ms===5000).fn();await h.flush();
  assert.equal(h.element('join-dialog').open,true);assert.equal(h.element('access-title').dataset.i18n,'unlinkedTitle');
});
test('approval received by polling opens Dashboard',async()=>{
  const h=harness([{body:session('pending')},{body:session('approved')}]);await h.flush();
  await [...h.timers.values()].find(t=>t.ms===5000).fn();await h.flush();assert.deepEqual(h.locations,['/']);
});
test('Code dialog has its own keyboard-reachable globe and shared language',async()=>{
  const h=harness([{body:session('unlinked')}]);await h.flush();
  assert.equal(h.element('join-dialog').open,true);
  h.element('join-language-toggle').handlers.click();
  assert.equal(h.saved.get('gg-language'),'en');
  assert.equal(h.element('join-language-toggle').getAttribute('aria-label'),'Switch language to Thai');
});
test('status feedback is translated when globe changes language',async()=>{
  const h=harness([{body:session('pending')},{body:session('pending')}]);await h.flush();
  await h.element('access-refresh').handlers.click();await h.flush();
  assert.equal(h.element('access-status').hidden,false);
  h.element('language-toggle').handlers.click();
  assert.equal(h.element('access-status').textContent,'Still awaiting administrator approval.');
});
test('case-sensitive Code fields disable mobile autocapitalization and correction',()=>{
  for(const name of ['local.html','online.html']){
    const html=fs.readFileSync(path.join(__dirname,name),'utf8');
    const input=html.match(/<input[^>]*id="hub-code"[^>]*>/)[0];
    assert.match(input,/autocapitalize="none"/);assert.match(input,/autocorrect="off"/);
    assert.match(html,/<button[^>]*id="join-language-toggle"[^>]*type="button"/);
  }
});
