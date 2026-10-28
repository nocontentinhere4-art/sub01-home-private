import assert from 'node:assert/strict';
import {createOwnedBitmapPainter} from '../../web/house/owned_bitmap_painter.mjs';
import {createPhoneScreen} from '../../web/house/phone_screen.mjs';
import {drawLifeApp} from '../../web/room_phone.js';
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
// a 2D context that records what is drawn (text, images, rectangles) and accepts the rest of the canvas API
const ctx=()=>{const ops=[];return{ops,
  fillRect:(...a)=>ops.push(['fillRect',...a]),
  fillText:(...a)=>ops.push(['text',a[0]]),
  drawImage:(...a)=>ops.push(['image',a[0]?.name||'page']),
  measureText:s=>({width:String(s).length*8}),
  beginPath(){},arc(){},fill(){},rect(){},roundRect(){},save(){},restore(){},
  set fillStyle(v){},set font(v){},set textAlign(v){},set textBaseline(v){}};};
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

// His life's view (home_phone.life_view as phone_view): the chat app and the order app are the picture while he holds the
// phone, with no browser frame fetched or shown in their place; a short video view leaves the frame as the picture.
const lifeScreen=ctx(),lifePage=ctx();
const lifeCanvas={width:256,height:512,getContext:()=>lifeScreen};
const lifeTexture={needsUpdate:false};
const lifeState={activity:'phone',app:'home',battery:55,frameId:'PHONE:7',title:'stale page',privacy:false,hidden:false,time:'21:10',view:null};
const lifeUrls=[];
const life=createPhoneScreen({canvas:lifeCanvas,texture:lifeTexture,getState:()=>({...lifeState}),
  createPage:(w,h)=>({width:w,height:h,getContext:()=>lifePage}),
  painterFactory:cfg=>createOwnedBitmapPainter({...cfg,
    fetchResponse:async url=>{lifeUrls.push(url);return{ok:true,status:200,blob:async()=>({})};},
    decode:async()=>({name:'frame',width:390,height:844,close(){}})})});
lifeState.view={app:'chat',why:'',lines:[
  {kind:'viewer',t:'21:03',who:'a viewer',text:'hello from chat',re:''},
  {kind:'reaction',t:'21:03',who:'his reaction (a fixed line)',text:'Okay, checking my phone.',re:''},
  {kind:'reply',t:'21:04',who:'his reply (AI-written)',text:'Hi there.',re:'hello from chat'}]};
assert.equal(life.update(),true,'the chat app is the phone\'s picture');await flush();
assert.deepEqual(lifeUrls,[],'the chat app fetches no browser frame, even with a frame id');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='Chat'),'status bar names the chat app');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='hello from chat'),'a viewer message is drawn');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='Okay, checking my phone.'),'his reaction is drawn');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='Hi there.'),'his reply is drawn');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='his reply (AI-written) · 21:04'),'his reply carries its tag');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='to a viewer: “hello from chat”'),'the line it answers is named');
assert.ok(!lifeScreen.ops.some(o=>o[0]==='image'),'no browser frame on the glass');
lifeState.view={app:'order',dish:'ramen',status:'on the way',eta_min:7,step:2,steps:['order placed','being prepared','courier on the way','delivered']};
lifeScreen.ops.length=0;assert.equal(life.update(),true,'the order app while he orders');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='Order'),'status bar names the order');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='Your order: 1 × ramen'),'the dish is drawn');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='7 min'),'the courier ETA is drawn');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='on the way'),'the courier status is drawn');
lifeState.view={app:'short'};
lifeScreen.ops.length=0;life.update();await flush();
assert.deepEqual(lifeUrls,['/api/screen/phone.jpg?frame_id=PHONE%3A7'],'a short video view keeps the browser frame');
lifeState.view={app:'chat',why:'no short video can show right now',lines:[]};
lifeScreen.ops.length=0;assert.equal(life.update(),true);
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='no messages yet'),'an empty chat says so');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='no short video can show right now'),'the honest reason is shown');
lifeState.privacy=true;lifeScreen.ops.length=0;lifeUrls.length=0;
assert.equal(life.update(),false,'privacy: the caller draws its idle screen');await flush();
assert.equal(lifeScreen.ops.length,0,'privacy paints no life view');assert.equal(lifeUrls.length,0);
lifeState.privacy=false;
Object.assign(lifeState,{activity:'order_food',view:{app:'order',dish:'sushi',status:'choosing what to eat',eta_min:null,step:0,steps:['order placed']}});
lifeScreen.ops.length=0;assert.equal(life.update(),true,'order_food shows the order app');
assert.ok(lifeScreen.ops.some(o=>o[0]==='text'&&o[1]==='choosing what to eat'),'choosing is shown until the order goes');
lifeState.view=null;assert.equal(life.update(),false,'no view and no phone: the idle home screen');
life.dispose();

// drawLifeApp: nothing for a short video or no view; a long line wraps over several lines; the bar band is left alone
const none=ctx();
assert.equal(drawLifeApp(none,256,512,{app:'short'},52),false,'a short video is never painted here');
assert.equal(drawLifeApp(none,256,512,null,52),false,'no view paints nothing');
assert.equal(none.ops.length,0);
const long=ctx();
assert.equal(drawLifeApp(long,256,512,{app:'chat',why:'',lines:[{kind:'viewer',t:'21:00',who:'a viewer',text:'word '.repeat(40),re:''}]},52),true);
assert.ok(long.ops.filter(o=>o[0]==='text'&&String(o[1]).includes('word')).length>=2,'a long line wraps');
assert.ok(!long.ops.some(o=>o[0]==='fillRect'&&o[2]<52),'nothing is painted over the status bar band (y < 52)');
console.log('PASS: phone shows its real app and frame by identity; privacy, hidden page and idle never fetch or paint; the chat and order apps are drawn from his life view, never a frame');
