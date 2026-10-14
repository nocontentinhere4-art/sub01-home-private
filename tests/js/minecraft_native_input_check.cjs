const assert=require('node:assert/strict');
const {nativeInput}=require('../../games/minecraft/native_input.cjs');
let clock=0,active=true,clears=0,digs=0;const keys={},receipts=[];
const bot={entity:{position:{toArray:()=>[0,64,0]},yaw:0,pitch:0},
 setControlState:(key,value)=>keys[key]=value,clearControlStates:()=>{clears++;for(const k in keys)keys[k]=false;},
 stopDigging:()=>digs++,look:async(y,p)=>{bot.entity.yaw=y;bot.entity.pitch=p;}};
const control=nativeInput({player:()=>bot,isActive:()=>active,isBusy:()=>false,emit:r=>receipts.push(r),now:()=>clock});
const base={consumer_id:'a'.repeat(32),focus_event_id:'b'.repeat(32),hold_ms:250,operation:'controls',keys:{forward:true},look_delta:[.2,-.1]};
(async()=>{
 await control.accept({...base,input_id:1});assert.equal(keys.forward,true);assert.equal(bot.entity.yaw,.2);assert.equal(receipts.at(-1).accepted,true);
 await control.accept({...base,input_id:1});assert.equal(receipts.at(-1).accepted,false);
 clock=251;control.tick();assert.equal(keys.forward,false);assert.ok(clears&&digs);
 await control.accept({...base,input_id:2});active=false;control.tick();assert.equal(keys.forward,false);
 await control.accept({...base,input_id:3});assert.equal(receipts.at(-1).accepted,false);
 active=true;await control.accept({...base,input_id:4});await control.accept({...base,input_id:5,operation:'release'});assert.equal(keys.forward,false);
 assert.equal(receipts.at(-1).reason,'released');
 console.log('Minecraft native input: real control dispatch, expiry, order, inactive and release checked');
})();
