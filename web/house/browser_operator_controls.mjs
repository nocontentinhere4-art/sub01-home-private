// Revision-bound controls for an existing isolated browser screenshot. Status
// alone never enables actions: locked JPEG/header and its Image load must agree.
const ACTIONS=new Set(['scroll_up','scroll_down','close_notice','back']);
// Five failed loads of the same frame stop the refresh loop (each failure would otherwise call syncState again).
const FRAME_FAILURE_LIMIT=5,FRAME_STOPPED='Browser picture unavailable after repeated tries. Close and reopen the browser to retry.';
export function createBrowserOperatorControls({
  device,image,getFrameId,isActive,getOperatorToken,onState=()=>{},onFeedback=()=>{},
  onStatus=()=>{},onRefreshNeeded=()=>{},
  frameTimeoutMs=10000,actionTimeoutMs=15000,setTimer=setTimeout,clearTimer=clearTimeout,
  createURL=blob=>URL.createObjectURL(blob),revokeURL=url=>URL.revokeObjectURL(url),
  fetchFrame=async(url,signal)=>{
    const response=await fetch(url,{signal,cache:'no-store'});
    return{status:response.status,frameId:response.headers.get('X-Frame-Id'),
      blob:response.ok?await response.blob():null};
  },
  fetchAction=async(body,signal,token)=>{
    const response=await fetch('/api/home/browser/action',{method:'POST',signal,
      headers:{'Content-Type':'application/json','X-Admin-Token':token},body:JSON.stringify(body)});
    let data={};try{data=await response.json();}catch{}
    return{status:response.status,data};
  },
}={}) {
  if(!['desk','phone'].includes(device)||!image||!getFrameId||!isActive||!getOperatorToken)
    throw new TypeError('Browser controls need a valid owned image/device/context');
  if(![frameTimeoutMs,actionTimeoutMs].every(n=>Number.isFinite(n)&&n>=1000))
    throw new TypeError('Browser request deadlines must be at least one second');
  let loaded=null,pending=null,loading=false,busy=false,request=null,frameRequest=null,
    generation=0,disposed=false,pendingURL=null,ownedURL=null,actionOperator=null,
    frameDeadline=null,actionDeadline=null,frameFailures=0,frameFailureId=null;
  const current=()=>{const id=getFrameId();return typeof id==='string'&&id.length>0?id:null;};
  const active=()=>!disposed&&isActive(image);
  function state(){
    const frameId=current();let reason='';
    if(!active())reason='Browser controls are inactive.';
    else if(!getOperatorToken())reason='Connect as operator to use browser controls.';
    else if(busy)reason='Browser action in progress.';
    else if(loading)reason='Loading current browser frame…';
    else if(frameFailures>=FRAME_FAILURE_LIMIT&&frameId===frameFailureId)reason=FRAME_STOPPED;
    else if(!loaded||loaded!==frameId)reason='Waiting for a current browser frame.';
    return{enabled:!reason,reason,frameId:loaded,loading,busy};
  }
  function emit(){if(!disposed)onState(state());}
  // Counts a failed load of the current frame and shows the state; false once the refresh loop must stop.
  function frameFailed(){frameFailures++;emit();return frameFailures<FRAME_FAILURE_LIMIT;}
  function invalidate(){
    if(frameDeadline!==null)clearTimer(frameDeadline);frameDeadline=null;
    if(actionDeadline!==null)clearTimer(actionDeadline);actionDeadline=null;
    generation++;request?.abort();frameRequest?.abort();request=frameRequest=null;
    actionOperator=null;busy=false;loaded=pending=null;loading=false;pendingURL=null;
    if(ownedURL)revokeURL(ownedURL);ownedURL=null;
  }
  function loadedFrame(){
    if(!active()||!pending||current()!==pending||!pendingURL||
       (image.currentSrc||image.src)!==pendingURL)return;
    if(frameDeadline!==null)clearTimer(frameDeadline);frameDeadline=null;
    loaded=pending;pending=null;pendingURL=null;loading=false;frameFailures=0;emit();
  }
  function failedFrame(){
    if(!active()||!pendingURL||image.src!==pendingURL)return;
    invalidate();emit();
    if(!frameFailed()){onFeedback(FRAME_STOPPED);return;}
    onFeedback('Browser image could not be loaded.');onRefreshNeeded('frame');
  }
  image.addEventListener('load',loadedFrame);image.addEventListener('error',failedFrame);
  async function refresh(){
    if(!active()){invalidate();emit();return;}
    const id=current();
    if(!id){invalidate();emit();return;}
    if(request&&getOperatorToken()!==actionOperator)invalidate();
    if(id!==frameFailureId){frameFailureId=id;frameFailures=0;} // a new frame starts a new count
    if(frameFailures>=FRAME_FAILURE_LIMIT)return; // stopped for this frame; the state already says why
    if(id===loaded&&!loading||id===pending&&loading){emit();return;}
    invalidate();pending=id;loading=true;emit();
    const token=generation,controller=new AbortController();frameRequest=controller;
    // Covers both HTTP retrieval and an Image decode/load that never completes.
    frameDeadline=setTimer(()=>{
      if(generation!==token||pending!==id)return;
      controller.abort();invalidate();
      if(active()){emit();if(frameFailed()){onFeedback('Browser image timed out. Refresh to try again.');onRefreshNeeded('frame-timeout');}else onFeedback(FRAME_STOPPED);}
    },frameTimeoutMs);
    const owns=()=>generation===token&&frameRequest===controller&&active()&&current()===id&&!controller.signal.aborted;
    try{
      const result=await fetchFrame(`/api/screen/${device}.jpg?frame_id=${encodeURIComponent(id)}`,controller.signal);
      if(!owns())return;
      if(result?.status!==200||result.frameId!==id){
        const stale=result?.status===409||result?.status===200;
        invalidate();emit();
        if(!frameFailed()){onFeedback(FRAME_STOPPED);return;}
        onFeedback(stale?'The browser frame changed. Refreshing…':'His browser has no public page to show right now.');
        onRefreshNeeded(stale?'frame-stale':'frame');return;
      }
      ownedURL=createURL(result.blob);pendingURL=ownedURL;
      image.src=pendingURL; // Only its actual load event can bind the revision.
    }catch(error){
      if(owns()){invalidate();emit();onFeedback(frameFailed()?'Browser image connection interrupted.':FRAME_STOPPED);}
    }finally{if(generation===token&&frameRequest===controller)frameRequest=null;}
  }
  async function perform(action){
    if(!ACTIONS.has(action))return false;
    if(!state().enabled){emit();return false;}
    const token=generation,frameId=loaded,operator=getOperatorToken();
    const controller=new AbortController();request=controller;actionOperator=operator;busy=true;emit();
    actionDeadline=setTimer(()=>{
      if(generation!==token||request!==controller)return;
      controller.abort();invalidate();
      // Refreshing status/JPEG is safe; never replay an action after a timeout.
      if(active()){emit();onFeedback('Browser action timed out. Check the page before trying again.');onRefreshNeeded('action-timeout');}
    },actionTimeoutMs);
    const owns=()=>generation===token&&request===controller&&active()&&current()===frameId&&getOperatorToken()===operator&&!controller.signal.aborted;
    try{
      const result=await fetchAction({device,action,frame_id:frameId},controller.signal,operator);
      if(!owns())return false;
      const data=result?.data||{};
      if(result?.status===409&&data.error==='stale'){
        invalidate();emit();onFeedback('The browser frame changed. Refreshing…');onRefreshNeeded('stale');return false;
      }
      if(result?.status===403){onFeedback('Operator access is required.');return false;}
      if(!Number.isInteger(result?.status)||result.status<200||result.status>=300){
        onFeedback(typeof data.message==='string'?data.message:'Browser action could not be applied.');
        onRefreshNeeded('action');return false;
      }
      if(typeof data.message==='string')onFeedback(data.message);
      // Returned status requests another screenshot, but cannot certify it loaded.
      if(data.status)onStatus(data.status);
      if((data.status||data.ok)&&active()&&getOperatorToken()===operator)
        onRefreshNeeded(data.ok?'applied':'status');
      return!!data.ok;
    }catch(error){
      if(owns())onFeedback('Browser connection interrupted. Try again.');return false;
    }finally{
      if(generation===token&&request===controller){
        if(actionDeadline!==null)clearTimer(actionDeadline);actionDeadline=null;
        request=null;actionOperator=null;busy=false;if(active())emit();
      }
    }
  }
  return{
    refresh,perform,state,
    deactivate(){invalidate();emit();},
    dispose(){invalidate();disposed=true;image.removeEventListener('load',loadedFrame);image.removeEventListener('error',failedFrame);},
  };
}
