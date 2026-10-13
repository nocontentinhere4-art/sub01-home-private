import assert from 'node:assert/strict';
import {createOwnedBitmapPainter} from '../../web/house/owned_bitmap_painter.mjs';
import {createPhoneScreen} from '../../web/house/phone_screen.mjs';
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const ctx=()=>{const ops=[];return{ops,fillRect:(...a)=>ops.push(['fillRect',...a]),fillText:(...a)=>ops.push(['text',a[0]]),drawImage:(...a)=>ops.push(['image',a[0]?.name||'page']),set fillStyle(v){},set font(v){},set textAlign(v){}};};
const screen=ctx(),pageCtx=ctx();
const canvas={width:256,height:512,getContext:()=>screen};
const texture={needsUpdate:false};
const state={activity:'phone',app:'page',battery:80,frameId:'PHONE:1',title:'Anime news',privacy:false,hidden:false,time:'21:04'};
const urls=[];let decodes=0;
const phone=createPhoneScreen({canvas,texture,getState:()=>({...state}),
  createPage:(w,h)=>({width:w,height:h,getContext:()=>pageCtx}),
  painterFactory:cfg=>createOwnedBitmapPainter({...cfg,
    fetchResponse:async url=>{urls.push(url);return{ok:true,status:200,blob:async()=>({})};},
    decode:async()=>{decodes++;return{name:'frame',width:390,height:844,close(){}};}})});
assert.equal(phone.update(),true);await flush();
assert.deepEqual(urls,['/api/screen/phone.jpg?frame_id=PHONE%3A1'],'frame identity in the request');
assert.ok(pageCtx.ops.some(o=>o[0]==='image'&&o[1]==='frame'),'real frame painted');
assert.ok(screen.ops.some(o=>o[0]==='text'&&o[1]==='Anime news'),'status bar shows the real page title');
assert.ok(screen.ops.some(o=>o[0]==='image'&&o[1]==='page'));assert.equal(texture.needsUpdate,true);
phone.update();await flush();assert.equal(urls.length,1,'same frame is not downloaded twice');
// A new identity keeps the previous page on screen until the new one paints.
let resolveNext;const slow=createPhoneScreen({canvas,texture,getState:()=>({...state}),
  createPage:(w,h)=>({width:w,height:h,getContext:()=>pageCtx}),
  painterFactory:cfg=>createOwnedBitmapPainter({...cfg,
    fetchResponse:async()=>({ok:true,status:200,blob:async()=>({})}),
    decode:()=>new Promise(r=>{resolveNext=()=>r({name:'frame',width:390,height:844,close(){}});})})});
slow.update();await flush();resolveNext();await flush();
state.frameId='PHONE:2';screen.ops.length=0;slow.update();await flush();
assert.ok(screen.ops.some(o=>o[0]==='image'&&o[1]==='page'),'old page stays while the new frame loads');
assert.ok(!screen.ops.some(o=>o[0]==='text'&&o[1]==='Loading…'),'no loading flicker between pages');
resolveNext();await flush();slow.invalidate();screen.ops.length=0;state.frameId='PHONE:3';slow.update();
assert.ok(!screen.ops.some(o=>o[0]==='image'&&o[1]==='page'),'after invalidate (privacy/activity) the old page is gone');
slow.dispose();state.frameId='PHONE:1';
state.frameId='PHONE:2';phone.update();await flush();assert.equal(urls.length,2,'new frame identity fetches once');
for(const change of[s=>{s.privacy=true;},s=>{s.hidden=true;},s=>{s.activity='sleep';}]){
  const before=urls.length;Object.assign(state,{privacy:false,hidden:false,activity:'phone'});change(state);
  screen.ops.length=0;texture.needsUpdate=false;
  assert.equal(phone.update(),false,'caller draws the idle screen');await flush();
  assert.equal(urls.length,before,'privacy/hidden/idle never fetch');assert.equal(screen.ops.length,0,'and never paint');
}
Object.assign(state,{privacy:false,hidden:false,activity:'phone',frameId:null,app:'music'});
screen.ops.length=0;assert.equal(phone.update(),true);
assert.ok(screen.ops.some(o=>o[0]==='text'&&o[1]==='Music'),'app without a frame shows its real app name');
phone.dispose();
console.log('PASS: phone shows its real app and frame by identity; privacy, hidden page and idle never fetch or paint');
