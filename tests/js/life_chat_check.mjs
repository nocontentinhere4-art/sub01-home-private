// Checks the viewer's chat in web/life.html: what is sent, what is shown, and what a reconnect does. The page's own chat
// script (<script id="chat-js">) runs as it is, against a fake DOM, a fake WebSocket and a fake clock; the static checks
// read the page's markup and its wiring. No browser, no server, no network.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../../web/life.html', import.meta.url), 'utf8');
const block = html.match(/<script id="chat-js">([\s\S]*?)<\/script>/);
assert.ok(block, 'life.html has the chat script block');
const chatSource = block[1];
const page = html.replace(block[0], '');   // the rest of the page: the socket, the desk screen, the scene

// --- static: markup, limits and wiring
for (const id of ['chat', 'f', 'in', 'nick', 'send', 'ack']) assert.ok(html.includes(`id="${id}"`), `#${id} is on the page`);
assert.ok(html.includes('<input id="nick" maxlength="16"'), 'the nickname stops at chat.NICK_MAX');
assert.ok(html.includes('<input id="in" maxlength="280"'), 'the message stops at chat.MAX_LEN');
assert.doesNotMatch(chatSource, /innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function/,
  'the chat script never parses server text as HTML');
for (const old of ['addChat(', 'showReaction(', 'reactionCopies', 'let unanswered', 'unanswered++', 'unanswered--', 'chatLines', 'getElementById("f").onsubmit'])
  assert.ok(!page.includes(old), `old chat code is gone: ${old}`);
for (const call of ['LifeChat.init({', 'LifeChat.attach(ws)', 'LifeChat.opened(sock)', 'LifeChat.closed(sock)',
  'LifeChat.onMessage(sock, m)', 'LifeChat.backlog(m.chat)', 'LifeChat.recent(9)'])
  assert.ok(page.includes(call), `the page is wired: ${call}`);

// --- a tiny fake DOM: children, textContent, scroll fields and listeners; innerHTML is recorded, never honoured
const htmlWrites = [];
class FakeEl {
  constructor(tag){
    Object.assign(this, {tagName: tag.toUpperCase(), className: '', children: [], attrs: {}, listeners: {}, value: '',
      _text: '', _top: 0, clientHeight: 180, focused: false});
  }
  get textContent(){ return this.children.length ? this.children.map(c => c.textContent).join('') : this._text; }
  set textContent(v){ this.children = []; this._text = String(v); }
  get innerHTML(){ return ''; }
  set innerHTML(v){ htmlWrites.push(String(v)); }
  get scrollHeight(){ return this.children.length * 20; }
  get scrollTop(){ return this._top; }
  set scrollTop(v){ this._top = Math.max(0, Math.min(Number(v), this.scrollHeight - this.clientHeight)); }
  appendChild(c){ this.children.push(c); return c; }
  removeChild(c){ this.children.splice(this.children.indexOf(c), 1); return c; }
  setAttribute(k, v){ this.attrs[k] = String(v); }
  getAttribute(k){ return this.attrs[k]; }
  addEventListener(type, fn){ (this.listeners[type] = this.listeners[type] || []).push(fn); }
  fire(type){ for (const fn of this.listeners[type] || []) fn({preventDefault(){}}); }
  focus(){ this.focused = true; }
}
function fakeEnv({nick = null, throwStorage = false} = {}){
  let time = 1_000_000;
  const data = new Map(nick === null ? [] : [['sub01.life.nick', nick]]);
  const storage = throwStorage
    ? {getItem(){ throw new Error('blocked'); }, setItem(){ throw new Error('blocked'); }}
    : {getItem: k => (data.has(k) ? data.get(k) : null), setItem: (k, v) => { data.set(k, String(v)); }};
  const ids = {chat: new FakeEl('div'), f: new FakeEl('form'), in: new FakeEl('input'), nick: new FakeEl('input'),
    send: new FakeEl('button'), ack: new FakeEl('div')};
  const timers = [];
  return {ids, data, storage, now: () => time, every: (ms, fn) => timers.push(fn),
    doc: {getElementById: id => ids[id] || null, createElement: tag => new FakeEl(tag)},
    advance(ms){ time += ms; for (const fn of timers) fn(); }};
}
// a fresh copy of the script per page, so no state carries over between checks
function chatPage(opts){
  const ctx = vm.createContext({});
  vm.runInContext(`${chatSource}\n;globalThis.LifeChat = LifeChat;`, ctx);
  const env = fakeEnv(opts);
  ctx.LifeChat.init({doc: env.doc, storage: env.storage, now: env.now, every: env.every});
  return {chat: ctx.LifeChat, env, ids: env.ids};
}
function socket(readyState = 1){
  return {readyState, sent: [], send(s){ if (this.readyState !== 1) throw new Error('InvalidStateError'); this.sent.push(JSON.parse(s)); }};
}
const shown = ids => ids.chat.children.map(r => r.textContent);
const rowClasses = ids => ids.chat.children.map(r => r.className);

// --- the nickname: kept in localStorage, and a blocked storage costs nothing
{
  const {ids} = chatPage({nick: 'ben'});
  assert.equal(ids.nick.value, 'ben', 'the nickname comes back from localStorage');
  assert.equal(chatPage({throwStorage: true}).ids.nick.value, '', 'blocked storage: no nickname, no error');
}

// --- send, ack, the reaction after its message, the countdown
{
  const {chat, env, ids} = chatPage();
  const ws = socket(), sock = chat.attach(ws);
  chat.opened(sock);
  assert.equal(ids.send.getAttribute('aria-disabled'), 'false', 'an open socket with no wait: send is enabled');
  ids.in.value = '  go and buy some bread  '; ids.nick.value = ' anna ';
  ids.f.fire('submit');                                        // Enter in either field comes through here
  assert.deepEqual(ws.sent, [{type: 'chat', text: 'go and buy some bread', nick: 'anna'}]);
  assert.equal(env.data.get('sub01.life.nick'), 'anna', 'the nickname is remembered, cleaned');
  assert.equal(ids.send.textContent, 'sending…');
  ids.f.fire('submit');
  assert.equal(ws.sent.length, 1, 'no second message while the first is unanswered');
  assert.equal(ids.ack.textContent, 'waiting for the answer to your last message');
  chat.onMessage(sock, {type: 'chat_ack', ok: true, queued: false, reaction: 'On my way to buy bread.', impulse: 'activity', t: '10:03'});
  assert.equal(ids.in.value, '', 'a sent message leaves the box');
  assert.equal(ids.ack.textContent, 'sent — it heard you');
  assert.equal(ids.send.textContent, 'wait 10 s');
  assert.equal(ids.send.getAttribute('aria-disabled'), 'true', 'the wait is shown as a disabled button');
  assert.deepEqual(shown(ids), [], 'the reaction waits for its broadcast copy, so it lands after the message');
  chat.onMessage(sock, {type: 'chat', gain: 0.5, text: 'go and buy some bread', t: '10:03'});
  chat.onMessage(sock, {type: 'reaction', text: 'On my way to buy bread.', nick: 'anna', t: '10:03'});
  assert.deepEqual(shown(ids), ['10:03 go and buy some bread', '10:03 SUB-01: On my way to buy bread. — anna']);
  assert.deepEqual(rowClasses(ids), ['ln', 'ln rx'], 'SUB-01 lines have their own style');
  assert.deepEqual(Array.from(chat.recent(9), m => m.text), ['go and buy some bread', 'SUB-01: On my way to buy bread.'], 'the desk screen reads the same lines');
  env.advance(3000); assert.equal(ids.send.textContent, 'wait 7 s');
  env.advance(7000); assert.equal(ids.send.textContent, 'send');
  assert.equal(ids.send.getAttribute('aria-disabled'), 'false');
  assert.equal(shown(ids).length, 2, 'the countdown adds no lines');
  ids.in.value = 'x'.repeat(40); ids.nick.value = 'n'.repeat(30); ids.f.fire('submit');
  assert.equal(ws.sent.at(-1).nick, 'n'.repeat(16), 'a nickname is cut to chat.NICK_MAX');
}

// --- two viewers, the same text in the same minute: each reaction shows once, and both show
{
  const {chat, ids} = chatPage();
  const sock = chat.attach(socket());
  chat.opened(sock);
  ids.in.value = 'buy bread'; ids.nick.value = 'anna'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: true, reaction: 'On my way.', t: '10:05'});
  chat.onMessage(sock, {type: 'reaction', text: 'On my way.', nick: 'ben', t: '10:05'});     // ben's first
  chat.onMessage(sock, {type: 'chat', text: 'buy bread', t: '10:05'});
  chat.onMessage(sock, {type: 'reaction', text: 'On my way.', nick: 'anna', t: '10:05'});
  assert.deepEqual(shown(ids), ['10:05 SUB-01: On my way. — ben', '10:05 buy bread', '10:05 SUB-01: On my way. — anna']);
}

// --- the server blanked our nickname, or sends the ack without one (today's server): still one line
{
  const {chat, ids} = chatPage();
  const sock = chat.attach(socket());
  chat.opened(sock);
  ids.in.value = 'buy bread'; ids.nick.value = 'anna'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: true, reaction: 'On my way.', t: '10:06'});
  chat.onMessage(sock, {type: 'reaction', text: 'On my way.', nick: '', t: '10:06'});
  assert.deepEqual(shown(ids), ['10:06 SUB-01: On my way.'], 'one reaction, one line');
}

// --- no broadcast copy comes (a congested socket skips it): the ack copy shows after 2 s, and a late copy adds nothing
{
  const {chat, env, ids} = chatPage();
  const sock = chat.attach(socket());
  chat.opened(sock);
  ids.in.value = 'hi'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: true, reaction: 'Hello.', t: '10:07'});
  env.advance(1000); assert.deepEqual(shown(ids), [], 'it waits for the broadcast copy first');
  env.advance(1000); assert.deepEqual(shown(ids), ['10:07 SUB-01: Hello.'], 'and shows alone after 2 s');
  chat.onMessage(sock, {type: 'reaction', text: 'Hello.', nick: '', t: '10:07'});
  assert.equal(shown(ids).length, 1, 'the late broadcast copy does not show twice');
}

// --- after a fallback, the copies that come later are matched on time and nickname: another viewer's copy shows, a
// different minute shows, and only our own copy of the shown minute is dropped
{
  const {chat, env, ids} = chatPage();
  const sock = chat.attach(socket());
  chat.opened(sock);
  ids.in.value = 'buy bread'; ids.nick.value = 'anna'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: true, reaction: 'On my way.', t: '10:05'});
  env.advance(2000);
  assert.deepEqual(shown(ids), ['10:05 SUB-01: On my way. — anna']);
  chat.onMessage(sock, {type: 'reaction', text: 'On my way.', nick: 'ben', t: '10:05'});     // ben's copy: not ours
  chat.onMessage(sock, {type: 'reaction', text: 'On my way.', nick: 'anna', t: '10:06'});    // ours, a minute later
  chat.onMessage(sock, {type: 'reaction', text: 'On my way.', nick: 'anna', t: '10:05'});    // ours: already on screen
  assert.deepEqual(shown(ids), ['10:05 SUB-01: On my way. — anna', '10:05 SUB-01: On my way. — ben', '10:06 SUB-01: On my way. — anna']);
}

// --- refusals: the reason is shown, the text stays in the box, and only a counted message starts a wait
{
  const {chat, env, ids} = chatPage();
  const ws = socket(), sock = chat.attach(ws);
  chat.opened(sock);
  ids.in.value = 'https://example.org'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: false, reason: 'links are not allowed'});
  assert.equal(ids.ack.textContent, 'not sent: links are not allowed');
  assert.equal(ids.ack.className, 'err', 'a refusal is shown in the error colour');
  assert.equal(ids.in.value, 'https://example.org', 'a refused message stays in the box to be edited');
  assert.equal(ids.send.getAttribute('aria-disabled'), 'false', 'a refusal the limit did not count gives no wait');
  ids.in.value = 'go on'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: false, reason: 'one message every 10 s'});   // e.g. sent from another tab
  assert.equal(ids.ack.textContent, 'not sent: one message every 10 s');
  assert.equal(ids.send.textContent, 'wait 10 s');
  env.advance(4000); assert.equal(ids.send.textContent, 'wait 6 s');
  ids.f.fire('submit'); assert.equal(ws.sent.length, 2, 'nothing is sent during the wait');
  env.advance(6000);
  assert.equal(ids.send.textContent, 'send');
  assert.equal(ids.ack.textContent, '', 'the wait message clears when the wait is over');
  ids.in.value = 'same words'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: false, reason: 'duplicate'});
  assert.equal(ids.ack.textContent, 'not sent: that exact text was just said here, say it another way');
  assert.equal(ids.send.textContent, 'wait 10 s', 'a duplicate counted against the limit');
}

// --- not connected: nothing is sent, the text stays; a blank message sends nothing and takes the focus
{
  const {chat, ids} = chatPage();
  const ws = socket(0), sock = chat.attach(ws);
  ids.in.value = 'hello'; ids.f.fire('submit');
  assert.equal(ws.sent.length, 0);
  assert.equal(ids.in.value, 'hello', 'kept while not connected');
  assert.equal(ids.ack.textContent, 'not connected yet: reconnecting…');
  assert.equal(ids.send.textContent, 'connecting');
  ws.readyState = 1; chat.opened(sock);
  assert.equal(ids.send.textContent, 'send');
  ids.in.value = '   '; ids.f.fire('submit');
  assert.equal(ws.sent.length, 0, 'blank text sends nothing');
  assert.equal(ids.in.focused, true, 'and the box takes the focus');
}

// --- reconnect: the hello's backlog shows only what is new, the reactions on screen stay, the old socket's count is gone
{
  const {chat, env, ids} = chatPage();
  const ws1 = socket(), s1 = chat.attach(ws1);
  chat.opened(s1);
  chat.backlog([{t: '10:01', text: 'c1'}, {t: '10:02', text: 'c2'}, {t: '10:03', text: 'c3'}]);
  chat.onMessage(s1, {type: 'chat', t: '10:04', text: 'c4'});
  chat.onMessage(s1, {type: 'reaction', text: 'Hi.', nick: 'ben', t: '10:04'});
  ids.in.value = 'unanswered'; ids.f.fire('submit');             // no chat_ack comes before the socket drops
  chat.closed(s1);
  assert.equal(ids.ack.textContent, 'connection dropped: your last message may not have been sent');
  const ws2 = socket(), s2 = chat.attach(ws2);
  chat.opened(s2);
  assert.equal(ids.ack.textContent, '', 'the connection note clears on reconnect');
  assert.equal(ids.send.textContent, 'wait 10 s', 'the page still waits: the server counts per viewer, not per socket');
  env.advance(10000);
  ids.in.value = 'after the wait'; ids.f.fire('submit');
  assert.deepEqual(ws2.sent, [{type: 'chat', text: 'after the wait', nick: ''}], 'the new socket starts with nothing unanswered');
  chat.backlog([{t: '10:02', text: 'c2'}, {t: '10:03', text: 'c3'}, {t: '10:04', text: 'c4'}, {t: '10:05', text: 'c5'}]);
  assert.deepEqual(shown(ids), ['10:01 c1', '10:02 c2', '10:03 c3', '10:04 c4', '10:04 SUB-01: Hi. — ben', '10:05 c5']);
  chat.backlog([{t: '10:02', text: 'c2'}, {t: '10:03', text: 'c3'}, {t: '10:04', text: 'c4'}, {t: '10:05', text: 'c5'}]);
  assert.equal(shown(ids).length, 6, 'the same hello again adds nothing');
}

// --- the log keeps 40 lines; a viewer reading older lines keeps their place; at the bottom the log follows
{
  const {chat, ids} = chatPage();
  const sock = chat.attach(socket());
  chat.opened(sock);
  chat.backlog(Array.from({length: 60}, (_, i) => ({t: '09:00', text: `m${i + 1}`})));
  assert.equal(ids.chat.children.length, 40, 'the page keeps 40 lines');
  assert.equal(chat.recent(100).length, 40, 'and so does the model the desk screen reads');
  assert.equal(shown(ids)[0], '09:00 m21', 'the oldest lines go first');
  assert.equal(ids.chat.scrollTop, ids.chat.scrollHeight - ids.chat.clientHeight, 'at the bottom: it follows the newest line');
  ids.chat.scrollTop = 100;
  chat.onMessage(sock, {type: 'chat', t: '09:01', text: 'm61'});
  assert.equal(ids.chat.scrollTop, 100, 'a new line does not move a viewer reading above');
  assert.equal(ids.chat.children.length, 40);
  ids.chat.scrollTop = ids.chat.scrollHeight;
  chat.onMessage(sock, {type: 'chat', t: '09:02', text: 'm62'});
  assert.equal(ids.chat.scrollTop, ids.chat.scrollHeight - ids.chat.clientHeight, 'back at the bottom: it follows again');
}

// --- server text is shown as text: no markup is parsed, every line is a div of spans
{
  const {chat, ids} = chatPage();
  const sock = chat.attach(socket());
  chat.opened(sock);
  const evil = '<img src=x onerror="alert(1)"><b>bold</b>';
  chat.onMessage(sock, {type: 'chat', t: '<i>10:10</i>', text: evil});
  chat.backlog([{t: '10:11', text: '<script>x()</script>'}]);
  ids.in.value = '<u>me</u>'; ids.nick.value = '<i>nick</i>'; ids.f.fire('submit');
  chat.onMessage(sock, {type: 'chat_ack', ok: false, reason: '<img src=x>'});
  chat.onMessage(sock, {type: 'reaction', text: '<b>hi</b>', nick: '<i>n</i>', t: '10:12'});
  assert.deepEqual(shown(ids), ['<i>10:10</i> ' + evil, '10:11 <script>x()</script>', '10:12 SUB-01: <b>hi</b> — <i>n</i>']);
  assert.equal(ids.ack.textContent, 'not sent: <img src=x>');
  assert.ok(ids.chat.children.every(row => row.tagName === 'DIV' && row.children.every(s => s.tagName === 'SPAN')));
  assert.deepEqual(htmlWrites, [], 'innerHTML is never set');
}

console.log('PASS: nickname kept and cleaned; send on Enter; one message in flight; 10 s countdown with a disabled button; ' +
  'reaction after its message, shown once (two viewers, the same text and minute, both shown); ack copy as fallback; ' +
  'refusal reasons shown and the text kept; wait counted only for limit/duplicate; reconnect with no repeated lines and ' +
  'a fresh unanswered count; 40-line cap; auto-scroll only at the bottom; server text never parsed as HTML');
