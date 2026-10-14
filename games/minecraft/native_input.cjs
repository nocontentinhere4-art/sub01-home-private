// Bounded controls on the actual Mineflayer player; never changes its position directly.
const CONTROL_NAMES = ['forward','back','left','right','jump','sneak','sprint'];
function nativeInput({player,isActive,isBusy,emit,Vec3,now=Date.now}) {
  let owner=null,counter=0,expires=0,generation=0,pending=false;
  const pose = p => p?.entity ? {position:p.entity.position.toArray(),yaw:p.entity.yaw,pitch:p.entity.pitch} : null;
  function stop() { expires=0; generation++; const p=player();p?.clearControlStates();p?.stopDigging(); }
  function tick() { if(expires && (now()>=expires || !isActive())) stop(); }
  async function accept(m) {
    const p=player(), key=`${m.consumer_id}:${m.focus_event_id}`, before=pose(p);
    const ack=(accepted,reason) => emit({type:'input_receipt',input_id:m.input_id,consumer_id:m.consumer_id,
      focus_event_id:m.focus_event_id,accepted,reason,before,after:pose(p)});
    if(!/^[0-9a-f]{32}:[0-9a-f]{32}$/.test(key)||!Number.isSafeInteger(m.input_id)||m.input_id<1) return ack(false,'identity/order');
    if(owner!==key) { if(expires>now())return ack(false,'another focus owns controls'); stop();owner=key;counter=0; }
    if(m.input_id<=counter)return ack(false,'stale input');
    if(!['controls','mine','place','release','cancel'].includes(m.operation))return ack(false,'operation');
    if(m.operation==='release'||m.operation==='cancel') {counter=m.input_id;stop();return ack(true,'released');}
    if(!isActive()||!p?.entity||isBusy()||(pending&&m.operation!=='controls'))return ack(false,'player unavailable/busy');
    const keys=m.keys||{}, look=m.look_delta||[0,0];
    if(m.hold_ms!==250||Object.keys(keys).some(k=>!CONTROL_NAMES.includes(k)||typeof keys[k]!=='boolean') ||
       !Array.isArray(look)||look.length!==2||look.some(v=>!Number.isFinite(v)||Math.abs(v)>.35))return ack(false,'limits');
    counter=m.input_id; expires=now()+250;
    if(m.operation==='controls') {
      for(const k of CONTROL_NAMES)p.setControlState(k,keys[k]===true);
      if(look.some(v=>v!==0)) await p.look(p.entity.yaw+look[0],Math.max(-Math.PI/2,Math.min(Math.PI/2,p.entity.pitch+look[1])),true);
      return ack(true,'controls applied');
    }
    // Real view ray. Mineflayer blockAtCursor currently rejects zero yaw/pitch.
    const e=p.entity,dir=new Vec3(-Math.sin(e.yaw)*Math.cos(e.pitch),Math.sin(e.pitch),-Math.cos(e.yaw)*Math.cos(e.pitch));
    const block=p.world.raycast(e.position.offset(0,e.eyeHeight||1.62,0),dir,4.5);
    if(!block||block.name==='air')return ack(false,'no reachable cursor block');
    const own=++generation;pending=true;let timer;
    try {
      let task;
      if(m.operation==='mine') {if(!p.canDigBlock(block))return ack(false,'block not diggable');task=p.dig(block);}
      else {
        const face=[[0,-1,0],[0,1,0],[0,0,-1],[0,0,1],[-1,0,0],[1,0,0]][block.face];
        const item=p.inventory.items().find(i=>/(_log|_planks|^dirt$|^cobblestone$)/.test(i.name));
        if(!face||!item)return ack(false,'no placeable inventory/cursor face');
        const target=block.position.plus(new Vec3(...face)), existing=p.blockAt(target);
        if(!existing||!['air','cave_air','void_air'].includes(existing.name)||
           (Math.abs(target.x+.5-e.position.x)<.8 && Math.abs(target.z+.5-e.position.z)<.8 && target.y<e.position.y+1.8 && target.y+1>e.position.y))return ack(false,'placement occupied');
        await p.equip(item,'hand');if(own!==generation||!isActive())return ack(false,'cancelled');
        task=p.placeBlock(block,new Vec3(...face));
      }
      // Holding control messages renew the deadline; absence cancels digging.
      await Promise.race([task,new Promise((_,reject)=>{timer=setTimeout(()=>{p.stopDigging();reject(new Error('task timeout'));},6000);})]);
      return ack(own===generation&&isActive(),own===generation?'completed':'cancelled');
    } catch(e) {return ack(false,String(e.message).slice(0,120));}
    finally {clearTimeout(timer);pending=false;}
  }
  return {accept,stop,tick};
}
module.exports={nativeInput};
