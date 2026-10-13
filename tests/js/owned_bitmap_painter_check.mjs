import assert from'node:assert/strict';
import{createOwnedBitmapPainter}from'../../web/house/owned_bitmap_painter.mjs';
let time=0,timerId=0,key='desk/browser/frame:1',active=true;
const timers=new Map(),requests=[],decodes=[],paints=[],unavailable=[],errors=[],timeouts=[];
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const bitmap=name=>({name,closes:0,close(){this.closes++;}});
const painter=createOwnedBitmapPainter({getContextKey:()=>key,isActive:()=>active,getURL:k=>'/frame?key='+encodeURIComponent(k),
 setTimer:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,at:time+delay});return id;},clearTimer:id=>timers.delete(id),
 fetchResponse:(url,signal)=>new Promise((resolve,reject)=>requests.push({url,signal,resolve,reject})),
 decode:blob=>new Promise((resolve,reject)=>decodes.push({blob,resolve,reject})),paint:(image,context)=>paints.push({image,context}),
 onUnavailable:(context,response)=>unavailable.push({context,response}),onError:(context,error)=>errors.push({context,error}),onTimeout:context=>timeouts.push(context),
});
async function advance(ms){time+=ms;for(const[id,t]of[...timers])if(t.at<=time&&timers.delete(id))t.fn();await flush();}
const ok=()=>({ok:true,blob:async()=>({jpeg:true})});
const first=painter.update();for(let i=0;i<50;i++)assert.equal(painter.update(),first);assert.equal(requests.length,1,'one fetch per current context even under150ms polling');
requests[0].resolve(ok());await flush();const firstBitmap=bitmap('browser');decodes[0].resolve(firstBitmap);assert.equal(await first,true);assert.equal(paints.length,1);assert.equal(firstBitmap.closes,1);assert.equal(timers.size,0);
const changing=painter.update();requests[1].resolve(ok());await flush();
key='desk/linux/frame:1';active=false;painter.synchronize();assert.ok(requests[1].signal.aborted);assert.equal(await changing,false);
const oldBitmap=bitmap('stale-browser');decodes[1].resolve(oldBitmap);await flush();assert.equal(oldBitmap.closes,1,'late non-abortable decode closes even after switching to Linux');assert.equal(paints.length,1,'browser cannot overwrite new Linux canvas');
key='tv/minecraft/frame:1';active=true;const minecraft=painter.update();key='tv/pong';active=false;painter.synchronize();assert.equal(await minecraft,false);assert.ok(requests[2].signal.aborted);
requests[2].resolve(ok());await flush();assert.equal(decodes.length,2,'stale HTTP is discarded before decode, cannot overwrite Pong/chess');
key='tv/minecraft/frame:2';active=true;const privacy=painter.update();requests[3].resolve(ok());await flush();active=false;painter.synchronize();const privateBitmap=bitmap('private');decodes[2].resolve(privateBitmap);assert.equal(await privacy,false);await flush();assert.equal(privateBitmap.closes,1);assert.equal(paints.length,1,'hidden/privacy/has_frame=false never paints');
// Loss/reentry into same named context must invalidate its previous generation.
active=true;const oldContext=painter.update();requests[4].resolve(ok());await flush();active=false;painter.synchronize();active=true;const replacement=painter.update();const replacedBitmap=bitmap('replaced');decodes[3].resolve(replacedBitmap);await flush();assert.equal(replacedBitmap.closes,1);assert.equal(await oldContext,false);assert.equal(painter.state().busy,true,'old decode cannot release new same-context job');
requests[5].resolve(ok());await flush();const newBitmap=bitmap('new');decodes[4].resolve(newBitmap);assert.equal(await replacement,true);assert.equal(newBitmap.closes,1);assert.equal(paints.at(-1).image,newBitmap);
const failed=painter.update();requests[6].resolve({ok:false,status:404});assert.equal(await failed,false);assert.equal(unavailable.length,1,'fallback callback only for current active owner');
const staleFailure=painter.update();active=false;painter.synchronize();requests[7].resolve({ok:false,status:404});assert.equal(await staleFailure,false);await flush();assert.equal(unavailable.length,1,'stale HTTP fallback must not clear current device canvas');
active=true;const hangingHTTP=painter.update();await advance(10000);assert.equal(await hangingHTTP,false);assert.ok(requests[8].signal.aborted);assert.equal(painter.state().busy,false);assert.equal(timeouts.length,1);
requests[8].resolve(ok());await flush();assert.equal(decodes.length,5,'timed-out HTTP cannot decode later');
const hangingDecode=painter.update();requests[9].resolve(ok());await flush();await advance(10000);assert.equal(await hangingDecode,false);assert.equal(painter.state().busy,false,'non-abortable hung decode cannot hold busy forever');
const next=painter.update();const lateDecode=bitmap('deadline-stale');decodes[5].resolve(lateDecode);await flush();assert.equal(lateDecode.closes,1);assert.equal(painter.state().busy,true,'timed-out decode must not release next request');
requests[10].resolve(ok());await flush();const finalBitmap=bitmap('final');decodes[6].resolve(finalBitmap);assert.equal(await next,true);assert.equal(finalBitmap.closes,1);
const disposed=painter.update();requests[11].resolve(ok());await flush();painter.dispose();assert.equal(await disposed,false);const disposedBitmap=bitmap('disposed');decodes[7].resolve(disposedBitmap);await flush();assert.equal(disposedBitmap.closes,1);assert.equal(timers.size,0);assert.equal(await painter.update(),false);
// Canvas drawing exceptions still release the actual decoded resource.
const throwingBitmap=bitmap('paint-error');const throwing=createOwnedBitmapPainter({getContextKey:()=> 'fixture',isActive:()=>true,getURL:()=>'/fixture',fetchResponse:async()=>ok(),decode:async()=>throwingBitmap,paint:()=>{throw new Error('canvas context gone');},onError:()=>errors.push('paint')});
assert.equal(await throwing.update(),false);assert.equal(throwingBitmap.closes,1);throwing.dispose();
console.log('PASS: one request per ownedcontext; activity/console/has_frame/privacy/hidden ownership; nonabortable stale bitmap.close; samecontext generation reentry; owned-only fallback/error; HTTP+decode deadline freesbusy; late completion cannot release newerjob; dispose/draw-error cleanup; no backend actions');
let dedupFetches=0;const dedupBitmap=bitmap('stable-revision');
const dedup=createOwnedBitmapPainter({getContextKey:()=> 'desk/frame:stable',isActive:()=>true,getURL:()=>'/locked',dedupPaintedKey:true,
 fetchResponse:async()=>{dedupFetches++;return ok();},decode:async()=>dedupBitmap,paint:()=>{}});
assert.equal(await dedup.update(),true);assert.equal(await dedup.update(),true);assert.equal(dedupFetches,1,'desk already painted revision can skip duplicate HTTP/decode');
dedup.invalidate();assert.equal(await dedup.update(),true);assert.equal(dedupFetches,2,'explicit mode/ABA invalidation requires paint again');dedup.dispose();
console.log('PASS optional desktop painted-revision dedupe; default continuous Minecraft frames remain enabled');
let continuousFetches=0;const continuous=createOwnedBitmapPainter({getContextKey:()=> 'minecraft',isActive:()=>true,getURL:()=>'/readonly-minecraft-frame',
 fetchResponse:async()=>{continuousFetches++;return ok();},decode:async()=>bitmap('live-'+continuousFetches),paint:()=>{}});
assert.equal(await continuous.update(),true);assert.equal(await continuous.update(),true);assert.equal(continuousFetches,2,'Minecraft same context continues drawing newer server images');continuous.dispose();
let bodyTimeout;const bodyTimers=new Map();let finishBlob;
const body=createOwnedBitmapPainter({getContextKey:()=> 'desk/body',isActive:()=>true,getURL:()=>'/readonly-frame',
 setTimer:fn=>{bodyTimers.set(1,fn);return 1;},clearTimer:()=>bodyTimers.clear(),
 fetchResponse:async()=>({ok:true,blob:()=>new Promise(resolve=>{finishBlob=resolve;})}),decode:async()=>{throw new Error('Expired body must never reach decoder');},paint:()=>{throw new Error('Expired body must never paint');}});
const bodyRequest=body.update();await flush();bodyTimeout=bodyTimers.get(1);bodyTimeout();assert.equal(await bodyRequest,false);assert.equal(body.state().busy,false);finishBlob({jpeg:true});await flush();body.dispose();
console.log('PASS continuous same-context Minecraft refresh; deadline includes stalled response.blob() body without later decode/paint');
