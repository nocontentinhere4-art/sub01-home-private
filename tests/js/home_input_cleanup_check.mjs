import assert from 'node:assert/strict';
import fs from 'node:fs';
import {HeldControls} from '../../web/house/held_controls.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');

// Exercise actual panel/privacy functions against an already-held input and draft.
const held=new HeldControls(), panel={hidden:false}, body={draft:'unfinished phone text',replaceChildren(){this.draft=null;}}, motion={resets:0,reset(){this.resets++;}};
const start=source.indexOf('function closePanel()'), end=source.indexOf('function browserFrame(',start);
const hooks=new Function('pongHeld','panel','panelBody','visitorMotion','document','renderer',`
  let keys={w:true},drag=true,privacyActive=false,panelKind='pong';const lite=false;
  ${source.slice(start,end)}
  return {closePanel,setPrivacy,state:()=>({keys,drag,privacyActive,panelKind})};
`)(held,panel,body,motion,{body:{classList:{toggle(){}}}},{shadowMap:{}});
held.set('ArrowUp',-1);held.acknowledge(held.version);
hooks.setPrivacy(true);
assert.equal(held.direction,0);assert.equal(held.changed,true);
assert.equal(body.draft,null);assert.equal(panel.hidden,true);
assert.deepEqual(hooks.state().keys,{});assert.equal(hooks.state().drag,false);
assert.equal(motion.resets,1);

// Use the actual keyboard listeners: censorship blocks input, and a retained
// OS repeat after it ends cannot restart walking without a fresh key press.
const keyboardStart=source.indexOf('addEventListener("keydown",'),keyboardEnd=source.indexOf('renderer.domElement.addEventListener("pointerdown",',keyboardStart);
const listeners={};
const keyboard=new Function('addEventListener','pongHeld',`
  let keys={},drag=false,privacyActive=true,panelKind='',tvGame='pong',following=false;const viewTransition={busy:false};
  const closePanel=()=>{},refreshAim=()=>{},aimed=null;
  ${source.slice(keyboardStart,keyboardEnd)}
  return {setPrivacy:value=>privacyActive=value,keys:()=>keys};
`)((name,handler)=>listeners[name]=handler,held);
const keyEvent=(repeat=false)=>({key:'w',repeat,target:{matches:()=>false},preventDefault(){}});
listeners.keydown(keyEvent());assert.deepEqual(keyboard.keys(),{});
keyboard.setPrivacy(false);
listeners.keydown(keyEvent(true));assert.deepEqual(keyboard.keys(),{});
listeners.keyup(keyEvent());listeners.keydown(keyEvent());assert.equal(keyboard.keys().w,true);
const touchStart=source.indexOf('document.querySelectorAll("[data-key]").forEach('),touchEnd=source.indexOf('const visitorMotion =',touchStart);
const pad={dataset:{key:'w'},setPointerCapture(){}};
const touch=new Function('document',`
  let keys={},privacyActive=true,panelKind='',following=false;const viewTransition={busy:false};
  ${source.slice(touchStart,touchEnd)}
  return {setPrivacy:value=>privacyActive=value,keys:()=>keys};
`)({querySelectorAll:()=>[pad]});
pad.onpointerdown({preventDefault(){},pointerId:1});assert.deepEqual(touch.keys(),{});
touch.setPrivacy(false);pad.onpointerdown({preventDefault(){},pointerId:2});assert.equal(touch.keys().w,true);
pad.onpointerup();assert.equal(touch.keys().w,false);

// Actual accessible/pointer button callbacks own their release through HeldControls.
const controlStart=source.indexOf('function pongControlButton('),controlEnd=source.indexOf('async function pongInput(',controlStart);
const makeControl=new Function('pongHeld','button',source.slice(controlStart,controlEnd)+';return pongControlButton;')(
  held,()=>({setAttribute(){},setPointerCapture(){}}));
const control=makeControl('Up',-1),event={pointerId:4,preventDefault(){}};
control.onpointerdown(event);assert.equal(held.direction,-1);
control.onlostpointercapture(event);assert.equal(held.direction,0);
control.onclick({detail:0});assert.equal(held.direction,-1);
hooks.closePanel();assert.equal(held.direction,0);assert.equal(held.changed,true);

// A hung real sender aborts and releases its in-flight guard, allowing neutral retry.
const senderStart=source.indexOf('async function pongInput('),senderEnd=source.indexOf('setInterval(async () => {',senderStart);
let clock=1000;const timers=[],requests=[];
const fetchMock=(url,options)=>{
  requests.push(JSON.parse(options.body));
  return requests.length===1 ? new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted')))) : Promise.resolve({ok:true});
};
const sender=new Function('fetch','AbortController','setTimeout','clearTimeout','Date',`
  let pongSending=false,lastPongInput=0;
  ${source.slice(senderStart,senderEnd)}
  return {pongInput,busy:()=>pongSending};
`)(fetchMock,AbortController,callback=>{timers.push({callback,cleared:false});return timers.length-1;},id=>{timers[id].cleared=true;},{now:()=>clock});
const hanging=sender.pongInput(-1);assert.equal(sender.busy(),true);
timers[0].callback();assert.equal(await hanging,false);assert.equal(sender.busy(),false);
clock+=110;assert.equal(await sender.pongInput(0),true);
assert.deepEqual(requests,[{direction:-1},{direction:0}]);
assert(timers.every(timer=>timer.cleared));
console.log('PASS: actual privacy draft/keyboard/drag cleanup, pointer and accessible release, hung sender abort and neutral retry');
