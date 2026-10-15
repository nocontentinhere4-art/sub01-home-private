const assert=require('node:assert/strict'),fs=require('node:fs'),vmModule=require('node:vm'),{EventEmitter}=require('node:events');
const {inputReceipts}=require('../../computer/input_receipts.cjs');
const {guestKeyboard}=require('../../computer/guest_keyboard.cjs');
(async()=>{
 let wall=1000,mono=10;const out=[];const protocol=inputReceipts(x=>out.push(x),()=>wall,()=>mono,1);
 const envelope={id:'a'.repeat(32),generation:7,deadline_ms:2400};
 const r=protocol.begin({_receipt:envelope});assert(r&&r.valid());
 assert.equal(protocol.begin({_receipt:envelope}),null); // bounded and duplicate refused
 protocol.cancel({id:envelope.id,generation:8});assert(r.valid());
 protocol.cancel({id:envelope.id,generation:7});assert(!r.valid());
 r.finish(true,'GuestKeyboardInjected');assert.equal(out[0].ok,false);
 r.finish(true,'GuestKeyboardInjected');assert.equal(out.length,1);
 assert.equal(protocol.begin({_receipt:{...envelope,deadline_ms:5000}}),null);
 assert.equal(protocol.begin({_receipt:{...envelope,id:'client-input-17'}}),null);
 const legacy=protocol.begin({});assert(legacy.valid());legacy.finish(true,'x');assert.equal(out.length,1);
 const cancelled=protocol.begin({_receipt:{...envelope,id:'f'.repeat(32)}});
 protocol.cancel({id:'f'.repeat(32),generation:7});
 assert.equal(await cancelled.wait(Promise.reject(Error('cancelled release API rejection'))),false);
 cancelled.finish(false,'Rejected');await new Promise(setImmediate);
 // A timed-out packet must not release an already-held key from another packet.
 const keys=[],delays=[];const keyboard=guestKeyboard(c=>keys.push(...c),()=>new Promise(r=>delays.push(r)));
 const held=keyboard.enqueue([29]);await new Promise(setImmediate);delays.shift()();await held;
 let alive=true;const next=keyboard.enqueue([56,30,158,184],()=>alive);
 await new Promise(setImmediate);assert.deepEqual(keys,[29,56]);alive=false;
 delays.shift()();assert.equal(await next,false);
 assert.deepEqual(keys,[29,56,184]); // only OWN Alt released, Ctrl remains held
 keyboard.cancel();assert.deepEqual(keys,[29,56,184,157]);
 // Execute the ACTUAL worker file with a stub v86 API: ACK follows successful
 // keyboard API calls, not stdin/readline delivery or a made-up app-consumption event.
 const input=new EventEmitter(),acks=[],invocations=[];let releaseFirst;let first=true,hangNext=false,rejectNext=false;
 class V86 {
  add_listener(){} run(){} destroy(){}
  keyboard_send_scancodes(c){invocations.push(...c);if(hangNext){hangNext=false;return new Promise(()=>{});}if(rejectNext){rejectNext=false;return Promise.reject(Error('stub API failure'));}if(first){first=false;return new Promise(r=>releaseFirst=r);}return Promise.resolve();}
 }
 const context={require:name=>{
  if(name==='./libv86.cjs')return{V86};
  if(name==='readline')return{createInterface:()=>input};
  if(name==='./vga_framebuffer.cjs')return{attachFramebuffer:()=>null};
  if(name==='./guest_keyboard.cjs')return require('../../computer/guest_keyboard.cjs');
  if(name==='./input_receipts.cjs')return require('../../computer/input_receipts.cjs');
  if(name==='./guest_mouse.cjs')return{guestMouse:()=>()=>{},mouseDiagnostics:()=>({})};
  return require(name);
 },process:{env:{},stdout:{write:s=>acks.push(JSON.parse(s))},stdin:{},on(){}},
 setInterval(){},setTimeout,clearTimeout,Buffer,console,__dirname:require('node:path').resolve(__dirname,'../../computer')};
 vmModule.runInNewContext(fs.readFileSync(require('node:path').resolve(__dirname,'../../computer/worker.cjs'),'utf8'),context);
 input.emit('line',JSON.stringify({type:'vga-keyboard',scancodes:[30,158],_receipt:{id:'b'.repeat(32),generation:8,deadline_ms:Date.now()+1400}}));
 await new Promise(setImmediate);assert.deepEqual(invocations,[30]);assert.equal(acks.length,0);
 releaseFirst();await new Promise(r=>setTimeout(r,80));
 assert.deepEqual(invocations,[30,158]);assert.equal(acks.length,1);
 assert.equal(acks[0].ok,true);assert.equal(acks[0].level,'GuestKeyboardInjected');assert.equal(acks[0].id,'b'.repeat(32));
 assert(acks[0].finished_ms>=acks[0].started_ms);
 // Cancel must interrupt even a hung API Promise and produce a negative ACK;
 // it releases only this operation's key and does not stall the legacy queue.
 hangNext=true;
 input.emit('line',JSON.stringify({type:'vga-keyboard',scancodes:[48,176],_receipt:{id:'c'.repeat(32),generation:9,deadline_ms:Date.now()+1400}}));
 await new Promise(setImmediate);assert.equal(invocations.at(-1),48);assert.equal(acks.length,1);
 input.emit('line',JSON.stringify({type:'graphical-input-cancel',id:'c'.repeat(32),generation:99}));
 await new Promise(setImmediate);assert.equal(acks.length,1);
 input.emit('line',JSON.stringify({type:'graphical-input-cancel',id:'c'.repeat(32),generation:9}));
 await new Promise(r=>setTimeout(r,30));assert.equal(acks[1].ok,false);assert.equal(invocations.at(-1),176);
 rejectNext=true;
 input.emit('line',JSON.stringify({type:'vga-keyboard',scancodes:[46,174],_receipt:{id:'d'.repeat(32),generation:10,deadline_ms:Date.now()+1400}}));
 await new Promise(r=>setTimeout(r,30));
 const negative=acks.find(a=>a.type==='graphical-input-ack'&&a.id==='d'.repeat(32));assert(negative&&!negative.ok);
 hangNext=true;
 input.emit('line',JSON.stringify({type:'vga-keyboard',scancodes:[32,160],_receipt:{id:'e'.repeat(32),generation:11,deadline_ms:Date.now()+50}}));
 await new Promise(r=>setTimeout(r,100));
 const expired=acks.find(a=>a.type==='graphical-input-ack'&&a.id==='e'.repeat(32));assert(expired&&!expired.ok);
 assert.equal(invocations.at(-1),160); // expiry released only its own D key
 console.log('PASS: actual worker-correlated v86 invocation ACK, deadline/cancel identities, no unrelated-key release');
})().catch(e=>{console.error(e);process.exitCode=1;});
