// Owner-scoped polling of the existing /api/music endpoint. No audio playback,
// paid API, backend writes or late DOM mutation after navigation/privacy.
export function musicTracks(payload,limit=8) {
  const seen=new Set(),result=[];
  const now=payload?.now;
  const rows=[...(now&&typeof now==='object'?[{song:now,isNow:true}]:[]),
    ...(Array.isArray(payload?.today)?payload.today.map(song=>({song,isNow:false})):[])];
  for(const {song,isNow}of rows){
    if(!song||typeof song!=='object')continue;
    const title=typeof song.title==='string'?song.title:'',artist=typeof song.artist==='string'?song.artist:'';
    if(!title&&!artist)continue;
    const id=typeof song.id==='string'&&song.id?song.id:null;
    const url=typeof song.url==='string'?song.url:'';
    const keys=[...(id?[`id:${id}`]:[]),...(url?[`url:${url}`]:[])];
    if(!keys.length)keys.push(`text:${title.trim().toLowerCase()}\n${artist.trim().toLowerCase()}`);
    if(keys.some(key=>seen.has(key)))continue;for(const key of keys)seen.add(key);
    result.push({...song,title,artist,url,isNow});if(result.length>=limit)break;
  }
  return result;
}

export function createLiveMusicFeed({
  fetchMusic=async signal=>{
    const response=await fetch('/api/music',{signal,cache:'no-store'});
    if(!response.ok)throw new Error(`Music request failed (${response.status})`);
    return response.json();
  },
  isActive=()=>true,onTracks=()=>{},onError=()=>{},intervalMs=5000,timeoutMs=10000,
  now=()=>performance.now(),setTimer=setTimeout,clearTimer=clearTimeout,
  createAbort=()=>new AbortController(),
}={}) {
  if(!Number.isFinite(intervalMs)||intervalMs<1000||!Number.isFinite(timeoutMs)||timeoutMs<1000)
    throw new Error('Music feed intervals must be at least one second');
  let owner=null,generation=0,pollTimer=null,deadlineTimer=null,request=null,signature=null,lastStart=-Infinity;
  function cancel(){
    if(pollTimer!==null)clearTimer(pollTimer);pollTimer=null;
    if(deadlineTimer!==null)clearTimer(deadlineTimer);deadlineTimer=null;
    request?.abort();request=null;
  }
  function stop(){generation++;cancel();owner=null;signature=null;}
  const owns=(token,target)=>generation===token&&owner===target&&!!owner&&isActive(target);
  function schedule(token,target){
    if(!owns(token,target)){if(generation===token&&owner===target)stop();return;}
    pollTimer=setTimer(()=>{pollTimer=null;void poll();},Math.max(0,lastStart+intervalMs-now()));
  }
  async function poll(){
    const token=generation,target=owner;
    if(!owns(token,target)){if(owner===target)stop();return;}
    if(request)return;
    if(now()<lastStart+intervalMs){schedule(token,target);return;}
    lastStart=now();const controller=createAbort();request=controller;
    deadlineTimer=setTimer(()=>controller.abort(),timeoutMs);
    try{
      const payload=await fetchMusic(controller.signal);
      if(!owns(token,target)||controller.signal.aborted)return;
      const tracks=musicTracks(payload);
      const next=JSON.stringify(tracks.map(song=>[song.id||'',song.title,song.artist,song.url,song.isNow]));
      if(next!==signature){signature=next;onTracks(target,tracks,payload);}
    }catch(error){
      if(owns(token,target)&&!controller.signal.aborted)onError(target,error);
    }finally{
      // Old ignored-abort responses cannot clear a newer owner's request/timer.
      if(generation===token&&owner===target){
        if(deadlineTimer!==null)clearTimer(deadlineTimer);deadlineTimer=null;
        if(request===controller)request=null;
        schedule(token,target);
      }
    }
  }
  return {
    setOwner(target){
      if(!target||!isActive(target)){stop();return;}
      if(owner===target)return;
      generation++;cancel();owner=target;signature=null;
      // Navigation to a fresh owner may load immediately; repeated live ticks
      // for that same owner never create another fetch or reset the throttle.
      lastStart=-Infinity;void poll();
    },
    stop,
    refresh(){
      if(!owner)return;
      if(!isActive(owner)){stop();return;}
      if(pollTimer!==null)clearTimer(pollTimer);pollTimer=null;void poll();
    },
    get active(){return !!owner&&isActive(owner);},
  };
}
