import assert from'node:assert/strict';
import fs from'node:fs';
import{createOwnedBitmapPainter}from'../../web/house/owned_bitmap_painter.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
function assignment(name){const a=source.indexOf(`${name} = createOwnedBitmapPainter({`),b=source.indexOf('\n});',a);assert.ok(a>0&&b>a);return source.slice(a,b+4);}
function functionCode(name,next){
 const named=/^(?:async\s+)?function\s+(\w+)/.exec(name)?.[1]||(/^[A-Za-z_]\w*$/.test(name)?name:null);
 const a=named?new RegExp(`(?:async\\s+)?function\\s+${named}\\s*\\(`).exec(source)?.index:source.indexOf(name);
 const b=source.indexOf(next,a);assert.ok(a>0&&b>a,`Missing actual function ${name}`);return source.slice(a,b);
}
const invalidate=functionCode('function invalidateDeviceBitmaps() {','const browserControls =');
const unavailable=functionCode('paintBrowserUnavailable','deskBitmapPainter = createOwnedBitmapPainter({');
const minecraftUnavailable=functionCode('paintMinecraftUnavailable','function drawTV() {');
const update=functionCode('async function updateRealBrowser() {','function acceptHome(state) {');
const privacy=functionCode('function setPrivacy(active) {','function browserFrame(device, parent) {');
const accept=functionCode('function acceptHome(state) {','let lastFullHome = null;');
const visibility=functionCode("document.addEventListener('visibilitychange',",'function notice(text) {');
const screenLights=functionCode('const deviceScreenLights = [];','function invalidateDeviceBitmaps()');
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
const ok=()=>({ok:true,blob:async()=>({jpeg:true})});
function fixture(){
 const draws={tv:[],tvFallback:[],desk:[],fallback:[]},tvContent={kind:'pong',label:'Pong'},expanded={src:'unchanged'},requests=[],decodes=[],configs=[],timers=new Map(),events=new Map();let timerId=0;
 const tvContext={drawImage:(...args)=>{draws.tv.push(args);tvContent.kind='bitmap';},fillRect:(...args)=>{draws.tvFallback.push(['fillRect',...args]);tvContent.kind='cleared';},fillText:(...args)=>{draws.tvFallback.push(['fillText',...args]);tvContent.label=args[0];}};
 const scope={homeState:{activity:'watch_video',privacy:false},privacyActive:false,document:{hidden:false},browserScreen:{frame_id:'BROWSER-UUID:47'},
  tvGame:'minecraft',minecraftState:{has_frame:true},tvTexture:{needsUpdate:false},st:{needsUpdate:false},
  tvCanvas:{getContext:()=>tvContext},
  sx:{fillRect:(...args)=>draws.desk.push(['fillRect',...args]),drawImage:(...args)=>draws.desk.push(['drawImage',...args]),fillText:(...args)=>draws.fallback.push(args)},
  panelBody:{querySelector:()=>expanded},deskBitmapPainter:null,minecraftBitmapPainter:null};
 Object.assign(scope,{keys:{},drag:false,visitorMotion:{reset(){}},lite:false,renderer:{shadowMap:{}},
  closePanel(){},phoneMusicFeed:{stop(){}},browserControls:new Map(),panelKind:'',phoneApp:'home',refreshPanelScreens(){},
  lastConsoleGame:'minecraft',lastFullHome:null,onlineAt:0,brainStage:'awake',upperCabinetDoors:null,lowerCabinetDoors:{setTargets(){}},
  lampOn:true,curtainOpen:false,homeTime:0,lastLightMinute:0,lighting(){},shade(){},drawTV(){},drawPhone(){},drawComputer(){},renderPanel(){}});
 scope.document.body={classList:{toggle(){}}};scope.document.getElementById=()=>({dataset:{}});scope.document.addEventListener=(name,fn)=>events.set(name,fn);
 const factory=config=>{
  configs.push(config);
  return createOwnedBitmapPainter({...config,
   setTimer:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimer:id=>timers.delete(id),
   fetchResponse:(url,signal)=>new Promise((resolve,reject)=>requests.push({url,signal,resolve,reject})),
   decode:blob=>new Promise((resolve,reject)=>decodes.push({blob,resolve,reject})),
  });
 };
 const controls=new Function('scope','createOwnedBitmapPainter',`with(scope){${screenLights}\n${invalidate}\n${unavailable}\n${minecraftUnavailable}\n${assignment('minecraftBitmapPainter')}\n${assignment('deskBitmapPainter')}\n${update}\n${privacy}\n${accept}\n${visibility}\nreturn{minecraftBitmapPainter,deskBitmapPainter,invalidateDeviceBitmaps,updateRealBrowser,setPrivacy,acceptHome};}`)(scope,factory);
 const close=()=>{controls.minecraftBitmapPainter.dispose();controls.deskBitmapPainter.dispose();assert.equal(timers.size,0);};
 return{scope,draws,tvContent,expanded,requests,decodes,configs,controls,events,timers,close};
}
const image=name=>({name,closed:0,close(){this.closed++;}});
// Execute actual factory config callbacks, changing only deferred transport and
// lightweight canvas spies. No copied isActive/getContextKey/paint conditions.
for(const change of[
 f=>{f.scope.tvGame='pong';},f=>{f.scope.tvGame='chess';},f=>{f.scope.minecraftState.has_frame=false;},
 f=>{f.scope.privacyActive=true;},f=>{f.scope.homeState.privacy=true;},f=>{f.scope.document.hidden=true;},
]){
 const f=fixture(),p=f.controls.minecraftBitmapPainter.update();assert.equal(f.requests[0].url,'/api/home/minecraft/frame.jpg');
 f.requests[0].resolve(ok());await flush();assert.equal(f.decodes.length,1);
 change(f);const late=image('old-Minecraft');f.decodes[0].resolve(late);assert.equal(await p,false);
 assert.equal(late.closed,1);assert.equal(f.draws.tv.length,0,'actual TV paint callback must never run after console/privacy/visibility/frame availability change');
 assert.equal(f.scope.tvTexture.needsUpdate,false);assert.equal(f.expanded.src,'unchanged');f.close();
}
for(const change of[
 f=>{f.scope.homeState.activity='use_computer';},f=>{f.scope.privacyActive=true;},
 f=>{f.scope.homeState.privacy=true;},f=>{f.scope.document.hidden=true;},f=>{f.scope.browserScreen.frame_id='BROWSER-UUID:48';},
]){
 const f=fixture(),p=f.controls.deskBitmapPainter.update();
 assert.equal(f.requests[0].url,'/api/screen/desk.jpg?frame_id=BROWSER-UUID%3A47','actual desktop config fetches locked status revision');
 f.requests[0].resolve(ok());await flush();change(f);const late=image('old-browser');f.decodes[0].resolve(late);assert.equal(await p,false);
 assert.equal(late.closed,1);assert.equal(f.draws.desk.length,0,'actual sx callback cannot overwrite Linux/privacy/hidden/current revision');assert.equal(f.scope.st.needsUpdate,false);f.close();
}
// Real mode-invalidation function also prevents leave-return ABA while decode waits.
{
 const f=fixture(),p=f.controls.deskBitmapPainter.update();f.requests[0].resolve(ok());await flush();
 f.controls.acceptHome({activity:'use_computer'});f.controls.acceptHome({activity:'watch_video'});
 const late=image('ABA browser');f.decodes[0].resolve(late);assert.equal(await p,false);await flush();assert.equal(late.closed,1);assert.equal(f.draws.desk.length,0);f.close();
}
for(const transition of[
 f=>{f.controls.acceptHome({activity:'watch_video',console_game:'pong'});f.controls.acceptHome({activity:'watch_video',console_game:'minecraft'});},
 f=>{f.controls.setPrivacy(true);f.controls.setPrivacy(false);},
 f=>{f.scope.document.hidden=true;f.events.get('visibilitychange')();f.scope.document.hidden=false;f.events.get('visibilitychange')();},
]){
 const f=fixture(),p=f.controls.minecraftBitmapPainter.update();f.requests[0].resolve(ok());await flush();
 transition(f);const late=image('mode-return');f.decodes[0].resolve(late);assert.equal(await p,false);await flush();assert.equal(late.closed,1);assert.equal(f.draws.tv.length,0,'actual accepted-home/privacy/visibility source hooks protect leave-return same context');f.close();
}
// Actual config retains live normal painting and continuous MC updates, but desk
// uses successful-revision dedupe until a new backend screenshot ID arrives.
{
 const f=fixture();assert.equal(f.configs[0].dedupPaintedKey,undefined);assert.equal(f.configs[1].dedupPaintedKey,true);
 for(let i=0;i<2;i++){
  const p=f.controls.minecraftBitmapPainter.update();f.requests[i].resolve(ok());await flush();const frame=image('minecraft-'+i);f.decodes[i].resolve(frame);assert.equal(await p,true);assert.equal(frame.closed,1);
 }
 assert.equal(f.draws.tv.length,2);assert.equal(f.expanded.src.startsWith('/api/home/minecraft/frame.jpg?t='),true);
 const desk=f.controls.deskBitmapPainter.update();f.requests[2].resolve(ok());await flush();const frame=image('desk');f.decodes[2].resolve(frame);assert.equal(await desk,true);assert.equal(frame.closed,1);
 assert.equal(await f.controls.deskBitmapPainter.update(),true);assert.equal(f.requests.length,3,'actual desktop config skips already-painted same revision');
 assert.equal(f.draws.desk.filter(r=>r[0]==='drawImage').length,1);f.close();
}
// The actual English unavailable callback may paint only the current browser.
{
 const f=fixture();let p=f.controls.deskBitmapPainter.update();f.requests[0].resolve({ok:false,status:409});assert.equal(await p,false);
 assert.equal(f.draws.fallback[0][0],'Updating his browser page…');
 p=f.controls.deskBitmapPainter.update();f.scope.homeState.activity='use_computer';f.requests[1].resolve({ok:false,status:404});assert.equal(await p,false);assert.equal(f.draws.fallback.length,1,'late unavailable response cannot erase actual terminal');f.close();
}
console.log('PASS actual home.js configs: revisionlocked deskGET and successful-revision dedupe; continuousMC;11activity/game/privacy/hidden/revision/frameavailability late-decode cases never paint actual TV/sx callbacks, all bitmapsclose;actualinvalidateABA;current-only English unavailable fallback; normalpainting/textureupdates preserved');
// Execute current fallback callbacks too: a failed MC image must replace old
// Pong pixels, while a stale failure must preserve the newly selected game.
for(const status of[404,409]){
 const f=fixture(),p=f.controls.minecraftBitmapPainter.update();assert.equal(f.tvContent.kind,'pong');
 f.requests[0].resolve({ok:false,status});assert.equal(await p,false);
 assert.equal(f.tvContent.kind,'cleared');assert.equal(f.tvContent.label,'Waiting for Minecraft…');
 assert.ok(f.draws.tvFallback.some(r=>r[0]==='fillText'&&r[1]==='Minecraft'));assert.equal(f.scope.tvTexture.needsUpdate,true);assert.equal(f.draws.desk.length,0);
 const previous=f.draws.tvFallback.length;f.scope.tvTexture.needsUpdate=false;
 const stale=f.controls.minecraftBitmapPainter.update();f.scope.tvGame='pong';f.tvContent.kind='pong';f.tvContent.label='new Pong';
 f.requests[1].resolve({ok:false,status});assert.equal(await stale,false);assert.equal(f.tvContent.kind,'pong');assert.equal(f.tvContent.label,'new Pong');assert.equal(f.draws.tvFallback.length,previous);assert.equal(f.scope.tvTexture.needsUpdate,false);f.close();
}
for(const device of['minecraft','desk']){
 const f=fixture(),p=device==='minecraft'?f.controls.minecraftBitmapPainter.update():f.controls.deskBitmapPainter.update();
 f.requests[0].reject(new Error('network fixture'));assert.equal(await p,false);
 if(device==='minecraft'){assert.equal(f.tvContent.label,'Minecraft picture unavailable.');assert.equal(f.draws.fallback.length,0);}
 else{assert.equal(f.draws.fallback.at(-1)[0],'Browser picture unavailable.');assert.equal(f.draws.tvFallback.length,0);}
 f.close();
}
for(const device of['minecraft','desk'])for(const lostOwner of[false,true]){
 const f=fixture(),p=device==='minecraft'?f.controls.minecraftBitmapPainter.update():f.controls.deskBitmapPainter.update();
 if(lostOwner){if(device==='minecraft')f.scope.tvGame='chess';else f.scope.homeState.activity='use_computer';}
 assert.equal(f.timers.size,1);[...f.timers.values()][0].fn();assert.equal(await p,false);assert.ok(f.requests[0].signal.aborted);
 if(lostOwner){assert.equal(f.draws.tvFallback.length,0);assert.equal(f.draws.fallback.length,0,'unowned deadline cannot label or clear current device');}
 else if(device==='minecraft'){assert.equal(f.tvContent.label,'Minecraft is taking a moment…');assert.equal(f.draws.fallback.length,0);}
 else{assert.equal(f.draws.fallback.at(-1)[0],'His browser is taking a moment…');assert.equal(f.draws.tvFallback.length,0);}
 f.requests[0].resolve(ok());await flush();assert.equal(f.decodes.length,0);f.close();
}
console.log('PASS actual MC404/409 clears oldPong with EnglishConnecting; stalefailure leaves newPong; actual desk/MC error and deadline labels hit only currentcorrectcanvas; unowned deadlines never clear/label changedgame/Linux');
