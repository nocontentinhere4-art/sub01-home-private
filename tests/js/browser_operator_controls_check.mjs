import assert from'node:assert/strict';
import{createBrowserOperatorControls}from'../../web/house/browser_operator_controls.mjs';
class ImageMock{
 src='';currentSrc='';listeners=new Map();
 addEventListener(name,fn){this.listeners.set(name,fn);}removeEventListener(name){this.listeners.delete(name);}
 load(source=this.src){this.currentSrc=source;this.listeners.get('load')?.();}
 error(){this.listeners.get('error')?.();}
}
const flush=async()=>{for(let i=0;i<6;i++)await Promise.resolve();};
const frames=[],actions=[],feedback=[],statuses=[],refreshes=[],states=[],revoked=[];
let revision='UUID:1',active=true,operator='operator-key',urlNumber=0;
const image=new ImageMock();
const controls=createBrowserOperatorControls({device:'phone',image,getFrameId:()=>revision,isActive:()=>active,getOperatorToken:()=>operator,
 fetchFrame:(url,signal)=>new Promise((resolve,reject)=>frames.push({url,signal,resolve,reject})),
 fetchAction:(body,signal,token)=>new Promise((resolve,reject)=>actions.push({body,signal,token,resolve,reject})),
 createURL:()=>`blob:test-${++urlNumber}`,revokeURL:url=>revoked.push(url),onState:s=>states.push(s),
 onFeedback:m=>feedback.push(m),onStatus:s=>statuses.push(s),onRefreshNeeded:reason=>refreshes.push(reason),
});
assert.equal(await controls.perform('back'),false);assert.equal(actions.length,0,'status alone never authorizes action');
void controls.refresh();assert.equal(frames.length,1);assert.equal(frames[0].url,'/api/screen/phone.jpg?frame_id=UUID%3A1');
void controls.refresh();assert.equal(frames.length,1,'same pending revision does not reload');
frames[0].resolve({status:200,frameId:'UUID:1',blob:{}});await flush();assert.equal(controls.state().enabled,false,'matching JPEG/header still requires Image load');
image.load('blob:old');assert.equal(controls.state().enabled,false,'old Image load cannot bind new blob');
image.load();assert.equal(controls.state().enabled,true);
void controls.refresh();assert.equal(frames.length,1,'loaded same revision stays unchanged');
operator='';assert.equal(await controls.perform('back'),false);assert.equal(actions.length,0,'no operator key blocks action');operator='operator-key';
const firstAction=controls.perform('scroll_down');assert.equal(actions.length,1);assert.deepEqual(actions[0].body,{device:'phone',action:'scroll_down',frame_id:'UUID:1'});
assert.equal(controls.state().enabled,false);assert.equal(await controls.perform('back'),false);assert.equal(actions.length,1,'one inflight action per owner');
actions[0].resolve({status:200,data:{ok:true,message:'Scrolled',status:{frame_id:'UUID:2'}}});assert.equal(await firstAction,true);assert.equal(statuses[0].frame_id,'UUID:2');assert.equal(refreshes.at(-1),'applied');
revision='UUID:2';assert.equal(controls.state().enabled,false,'new status alone cannot bind JPEG');void controls.refresh();assert.ok(revoked.includes('blob:test-1'));
frames[1].resolve({status:200,frameId:'UUID:2',blob:{}});await flush();image.load();assert.equal(controls.state().enabled,true);
const noOp=controls.perform('close_notice');actions[1].resolve({status:200,data:{ok:false,message:'No safe close button on this page',status:{frame_id:'UUID:3'}}});assert.equal(await noOp,false);assert.equal(refreshes.at(-1),'status','non-ok action with fresh status also requests locked screenshot');
const stale=controls.perform('back');actions[2].resolve({status:409,data:{error:'stale'}});assert.equal(await stale,false);assert.equal(controls.state().enabled,false);assert.equal(refreshes.at(-1),'stale');assert.match(feedback.at(-1),/frame changed/);
revision='UUID:4';void controls.refresh();const oldFrame=frames[2];revision='UUID:5';void controls.refresh();assert.ok(oldFrame.signal.aborted);
oldFrame.resolve({status:200,frameId:'UUID:4',blob:{}});await flush();assert.equal(image.src,'blob:test-2','ignored abort cannot assign old frame image');
frames[3].resolve({status:200,frameId:'wrong-header',blob:{}});await flush();assert.equal(controls.state().enabled,false);assert.equal(refreshes.at(-1),'frame-stale');
void controls.refresh();frames[4].resolve({status:409,frameId:null});await flush();assert.equal(controls.state().enabled,false);assert.equal(refreshes.at(-1),'frame-stale');
void controls.refresh();frames[5].resolve({status:200,frameId:'UUID:5',blob:{}});await flush();image.load();
const disappearing=controls.perform('scroll_up'),lastAction=actions.at(-1),written=feedback.length;active=false;controls.deactivate();assert.ok(lastAction.signal.aborted);lastAction.resolve({status:200,data:{ok:true,message:'LATE',status:{frame_id:'UUID:6'}}});assert.equal(await disappearing,false);assert.equal(feedback.length,written,'privacy/appclose prevents late action feedback/status');
active=true;revision='UUID:7';void controls.refresh();const closingFrame=frames.at(-1);controls.dispose();assert.ok(closingFrame.signal.aborted);closingFrame.resolve({status:200,frameId:'UUID:7',blob:{}});await flush();assert.equal(image.listeners.size,0);assert.equal(image.src,'blob:test-3','disposed owner cannot assign later image');
assert.equal(await controls.perform('click_random'),false,'only approved finite actions accepted');
// Another owned image never inherits the first controller's successful load.
const second=new ImageMock();let request2;
const next=createBrowserOperatorControls({device:'desk',image:second,getFrameId:()=>revision,isActive:()=>true,getOperatorToken:()=>operator,
 fetchFrame:(url,signal)=>new Promise(resolve=>{request2={url,signal,resolve};}),createURL:()=> 'blob:newowner',revokeURL:()=>{},fetchAction:async()=>({status:403,data:{}}),onFeedback:m=>feedback.push(m)});
void next.refresh();assert.equal(next.state().enabled,false);request2.resolve({status:200,frameId:revision,blob:{}});await flush();second.load();assert.equal(next.state().enabled,true);
assert.equal(await next.perform('back'),false);assert.equal(feedback.at(-1),'Operator access is required.');
next.dispose();
console.log('PASS: lockedJPEG+header+actualImage load binding; sameframe dedupe; currentrevision/operator/inflight gates; status-only disable; safe no-op refresh; stale409; ignored-abort screenshot/action ownership; privacy/dispose cleanup; independent device owner; allowed actions/auth403');
// Deadlines cover HTTP AND Image load; stale completions cannot revive either.
let clock=0,timerId=0;const timers=new Map(),deadlineFrames=[],deadlineActions=[],deadlineFeedback=[],deadlineRefresh=[];
const deadlineImage=new ImageMock();let deadlineRevision='DEAD:1',deadlineActive=true;
const deadline=createBrowserOperatorControls({device:'desk',image:deadlineImage,getFrameId:()=>deadlineRevision,isActive:()=>deadlineActive,getOperatorToken:()=>operator,
 setTimer:(fn,delay)=>{const key=++timerId;timers.set(key,{fn,at:clock+delay});return key;},clearTimer:key=>timers.delete(key),
 fetchFrame:(url,signal)=>new Promise(resolve=>deadlineFrames.push({url,signal,resolve})),fetchAction:(body,signal)=>new Promise(resolve=>deadlineActions.push({body,signal,resolve})),
 createURL:()=>`blob:deadline-${++urlNumber}`,revokeURL:()=>{},onFeedback:m=>deadlineFeedback.push(m),onRefreshNeeded:r=>deadlineRefresh.push(r)});
async function tick(ms){clock+=ms;for(const[key,t]of[...timers])if(t.at<=clock&&timers.delete(key))t.fn();await flush();}
void deadline.refresh();await tick(10000);assert.ok(deadlineFrames[0].signal.aborted,'hung frame HTTP aborts');assert.equal(deadline.state().loading,false);assert.equal(deadlineRefresh.at(-1),'frame-timeout');deadlineFrames[0].resolve({status:200,frameId:'DEAD:1',blob:{}});await flush();assert.equal(deadlineImage.src,'','late timed-out frame cannot assign image');
void deadline.refresh();deadlineFrames[1].resolve({status:200,frameId:'DEAD:1',blob:{}});await flush();const noLoadURL=deadlineImage.src;
await tick(10000);assert.equal(deadline.state().enabled,false,'Image load that never fires is bounded');deadlineImage.load(noLoadURL);assert.equal(deadline.state().enabled,false,'timed-out image cannot bind revision');
void deadline.refresh();deadlineFrames[2].resolve({status:200,frameId:'DEAD:1',blob:{}});await flush();deadlineImage.load();assert.equal(timers.size,0,'successful actual Image load clears decode deadline');
const timedAction=deadline.perform('back');assert.equal(deadlineActions.length,1);await tick(15000);assert.ok(deadlineActions[0].signal.aborted);assert.equal(deadlineRefresh.at(-1),'action-timeout');assert.equal(deadline.state().enabled,false);assert.equal(deadlineActions.length,1,'no automatic action replay on timeout');
deadlineActions[0].resolve({status:200,data:{ok:true,message:'LATE'}});assert.equal(await timedAction,false);assert.ok(!deadlineFeedback.includes('LATE'));
void deadline.refresh();deadlineRevision='DEAD:2';void deadline.refresh();assert.ok(deadlineFrames[3].signal.aborted);deadlineFrames[3].resolve({status:200,frameId:'DEAD:1',blob:{}});await flush();assert.equal(timers.size,1,'old ignored-abort completion cannot clear newer deadline');
deadlineActive=false;deadline.deactivate();assert.equal(timers.size,0);assert.ok(deadlineFrames[4].signal.aborted);deadline.dispose();
console.log('PASS:10s frame HTTP+decode deadline;15s action deadline; no automatic action replay; owner-safe abort/late suppression and deadline cleanup');
