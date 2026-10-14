const assert=require('node:assert/strict');
const {nativeInput}=require('../../games/minecraft/native_input.cjs');
let clock=0,finish,receipts=[],deactivated=0;
const bot={entity:{position:{toArray:()=>[0,64,0]},yaw:0,pitch:0},
 clearControlStates(){},stopDigging(){},deactivateItem(){deactivated++;},setControlState(){},
 look:async(y,p)=>{bot.entity.yaw=y;bot.entity.pitch=p;},inventory:{items:()=>[{name:'bread'}]},
 equip:async()=>{},consume:()=>new Promise(r=>finish=r)};
class Vec3{constructor(x,y,z){this.x=x;this.y=y;this.z=z;}}
const control=nativeInput({player:()=>bot,isActive:()=>true,isBusy:()=>false,emit:r=>receipts.push(r),Vec3,now:()=>clock});
const base={consumer_id:'a'.repeat(32),focus_event_id:'b'.repeat(32),hold_ms:250,keys:{},look_delta:[0,0]};
(async()=>{
 const task=control.accept({...base,input_id:1,operation:'use'});await new Promise(setImmediate);
 await control.accept({...base,input_id:2,operation:'controls',keys:{forward:true}});
 assert.equal(receipts.at(-1).controller_state.keys.forward,true);
 assert.equal(receipts.at(-1).controller_state.pending_operation,'use'); // Actual consume is in flight.
 finish();await task;
 await control.accept({...base,input_id:3,operation:'controls'});
 assert.equal(receipts.at(-1).controller_state.pending_operation,null);
 const pending=control.accept({...base,input_id:4,operation:'use'});await new Promise(setImmediate);
 await control.accept({...base,input_id:5,operation:'release'});
 assert.deepEqual(receipts.at(-1).controller_state.keys,{});
 assert.equal(receipts.at(-1).controller_state.pending_operation,null);
 finish();await pending;assert.equal(receipts.at(-1).accepted,false);assert.ok(deactivated>0);
 console.log('Worker controller receipts reflect actual applied keys, pending use and release; late cancelled action is rejected');
})();
