import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as T from '../../web/house/vendor/three.module.js';

const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const start=source.indexOf('document.getElementById("explore").onclick =');
const end=source.indexOf('document.getElementById("lamp").onclick',start);
assert.ok(start>=0 && end>start);
const button={classList:{add(){},remove(){}}}, explore={...button};
const document={getElementById:id=>id==='explore'?explore:button};
const camera={position:new T.Vector3(2,1.23,-1.9)};
const renderer={domElement:{focus(){}}};
const homeState={seated:1,entry_position:[2,1.65,-.75]};
const state=new Function('T','document','homeState','camera','renderer','notice',
  `let following=true, visitorStandTarget=null, targetY=1.23;
   ${source.slice(start,end)}
   return {get:()=>({following,visitorStandTarget,targetY}),
           finishedStanding:()=>{visitorStandTarget=null;targetY=1.65;}};`
)(T,document,homeState,camera,renderer,()=>{});
explore.onclick();
assert.equal(state.get().following,false);
assert.deepEqual(state.get().visitorStandTarget.toArray(),homeState.entry_position,'first exit from Follow still stands up naturally');
state.finishedStanding();
camera.position.set(2,1.65,5.25); // visitor walked to the entrance terrace
homeState.entry_position=[-1.2,4.65,-2.9]; // SUB-01 is now seated upstairs
const before=JSON.stringify({state:state.get(),position:camera.position.toArray()});
explore.onclick();explore.onclick();
assert.equal(JSON.stringify({state:state.get(),position:camera.position.toArray()}),before,
  'repeated Explore must not start an unrestricted flight back to the actor');
console.log('PASS: first Follow→Explore stands up; repeated Explore preserves visitor position, height and completed stand state');
