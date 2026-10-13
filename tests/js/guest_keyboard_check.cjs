const assert = require('node:assert/strict');
const {guestKeyboard} = require('../../computer/guest_keyboard.cjs');
(async()=>{
 const events=[], queue=[];
 const keyboard=guestKeyboard(codes=>events.push(...codes),()=>new Promise(resolve=>queue.push(resolve)));
 const first=keyboard.enqueue([29,30,158,157]), second=keyboard.enqueue([48,176]);
 await new Promise(setImmediate);
 assert.deepEqual(events,[29]);
 queue.shift()();await new Promise(setImmediate);
 assert.deepEqual(events,[29,30]);
 keyboard.cancel();
 assert.deepEqual(events,[29,30,157,158]);
 queue.shift()();await first;assert.equal(await second,false);
 assert.deepEqual(events,[29,30,157,158]);
 const next=keyboard.enqueue([28,156]);await new Promise(setImmediate);
 queue.shift()();await new Promise(setImmediate);queue.shift()();assert.equal(await next,true);
 assert.deepEqual(events.slice(-2),[28,156]);
 console.log('PASS: real key order, press interval, privacy cancellation/releases, subsequent input');
})();
