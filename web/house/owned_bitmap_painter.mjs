// Read-only image delivery to one actual canvas/device context. paint() must be
// synchronous. Mode/privacy/visibility changes call synchronize()/invalidate().
// Never starts actions, changes the backend, or paints an unowned late response.
export function createOwnedBitmapPainter({
  getContextKey,isActive,getURL,paint,onUnavailable=()=>{},onError=()=>{},onTimeout=()=>{},
  fetchResponse=(url,signal)=>fetch(url,{signal,cache:'no-store'}),
  decode=blob=>createImageBitmap(blob),timeoutMs=10000,
  dedupPaintedKey=false,
  setTimer=setTimeout,clearTimer=clearTimeout,
}={}){
  if(![getContextKey,isActive,getURL,paint].every(fn=>typeof fn==='function'))
    throw new TypeError('Owned bitmap painter requires context/activity/URL/paint callbacks');
  if(!Number.isFinite(timeoutMs)||timeoutMs<1000)throw new TypeError('Bitmap deadline must be at least one second');
  let generation=0,job=null,observedKey=null,observedActive=false,disposed=false,paintedKey=null;
  const context=()=>{
    if(disposed)return{key:null,active:false};
    const key=getContextKey();return{key,active:typeof key==='string'&&key.length>0&&!!isActive(key)};
  };
  function cancel(){
    generation++;paintedKey=null;
    const previous=job;job=null;
    if(previous){clearTimer(previous.timer);previous.controller.abort();previous.finish(false);}
  }
  function synchronize(){
    const current=context();
    if(current.key!==observedKey||current.active!==observedActive||!current.active&&job)cancel();
    observedKey=current.key;observedActive=current.active;
    return current;
  }
  function invalidate(){cancel();observedKey=null;observedActive=false;paintedKey=null;}
  function update(){
    const current=synchronize();
    if(!current.active)return Promise.resolve(false);
    if(dedupPaintedKey&&paintedKey===current.key)return Promise.resolve(true);
    if(job)return job.promise; // one fetch/decode for the current owned context
    const token=generation,controller=new AbortController();
    let finish;
    const promise=new Promise(resolve=>{finish=resolve;});
    const task={controller,promise,finish,timer:null,key:current.key};job=task;
    const owns=()=>{
      const latest=context();return!controller.signal.aborted&&job===task&&generation===token&&latest.active&&latest.key===task.key;
    };
    task.timer=setTimer(()=>{
      if(job!==task||generation!==token)return;
      const report=owns();cancel();
      if(report)onTimeout(task.key);
    },timeoutMs);
    // run() catches its own errors even after the public deadline has settled.
    // A non-abortable late ImageBitmap decode still closes its bitmap in finally.
    void(async()=>{
      let bitmap=null;
      try{
        const response=await fetchResponse(getURL(task.key),controller.signal);
        if(!owns())return;
        if(!response.ok){onUnavailable(task.key,response);return;}
        const blob=await response.blob();if(!owns())return;
        bitmap=await decode(blob);if(!owns())return;
        paint(bitmap,task.key);paintedKey=task.key;task.finish(true);
      }catch(error){if(owns())onError(task.key,error);}
      finally{
        if(bitmap)try{bitmap.close();}catch{}
        // An old ignored-abort/decode completion must not release a newer job.
        clearTimer(task.timer);
        if(job===task&&generation===token){job=null;task.finish(false);}
      }
    })();
    return promise;
  }
  return{
    update,synchronize,invalidate,
    state(){const current=context();return{busy:!!job,contextKey:current.key,active:current.active};},
    dispose(){disposed=true;invalidate();},
  };
}
