import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createDeviceRevisions} from '../../web/house/device_revisions.mjs';
const source=fs.readFileSync(new URL('../../web/house/home.js',import.meta.url),'utf8');
const a=source.indexOf('let lastFullHome = null;'),b=source.indexOf('let socket, reconnectTimer',a);
assert.ok(a>0&&b>a,'actual syncState block');
const block=source.slice(a,b);
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return{promise,resolve};};
function fixture(){
  const fetches=[],calls={invalidate:0,accept:0,browser:0};
  const scope={createDeviceRevisions,
    fetch:url=>{const d=deferred();fetches.push({url,...d});return d.promise;},
    notice(){},acceptHome(){calls.accept++;},drawChess(){},drawComputer(){},refreshPanelScreens(){},
    updateRealBrowser:async()=>{calls.browser++;},invalidateDeviceBitmaps(){calls.invalidate++;},
    st:{},screenCanvas:{},homeState:{activity:'phone'},
    browserScreen:{frame_id:'OLD'},phoneBrowserScreen:{frame_id:'OLD-P'},computerState:{output:'old'},
    minecraftState:{has_frame:true},browserState:null,chessState:null,homeTime:0,brainStage:'awake'};
  const api=new Function('scope',`with(scope){${block}\nreturn{deviceRevisions,syncState};}`)(scope);
  const json=body=>({ok:true,json:async()=>body});
  const state={home:{activity:'phone'},computer:{output:'secret page'},browser:null,
    browser_screen:{frame_id:'LIVE-D'},phone_browser_screen:{frame_id:'LIVE-P'},minecraft:{has_frame:true},time:1,stage:'awake'};
  return{scope,api,fetches,calls,json,state};
}
// A full-state response requested before privacy entry is dropped; device state is cleared once.
{
  const f=fixture();f.api.deviceRevisions.accept({computer:1,desk:'D',phone:'P',minecraft:'m',console_game:'pong'});
  const pending=f.api.syncState();
  f.api.deviceRevisions.accept({privacy:true});
  assert.equal(f.scope.browserScreen,null);assert.equal(f.scope.phoneBrowserScreen,null);
  assert.equal(f.scope.computerState.output,'');assert.equal(f.scope.minecraftState.has_frame,false);assert.equal(f.calls.invalidate,1);
  f.fetches[0].resolve(f.json(f.state));await flush();f.fetches[1].resolve(f.json({}));await pending;
  assert.equal(f.scope.browserScreen,null,'late pre-privacy response must not repopulate the desk');
  assert.equal(f.scope.phoneBrowserScreen,null);assert.equal(f.scope.computerState.output,'');
  assert.equal(f.calls.accept,0);assert.equal(f.calls.browser,0,'no paint request from a stale response');
}
// After privacy exit the change-triggered refresh applies a fresh response normally.
{
  const f=fixture();f.api.deviceRevisions.accept({privacy:true});
  f.api.deviceRevisions.accept({computer:2,desk:'D2',phone:'P2',minecraft:'m2',console_game:'pong'});
  await flush();assert.equal(f.fetches.length,1,'exit triggers one refresh');
  f.fetches[0].resolve(f.json(f.state));await flush();f.fetches[1].resolve(f.json({}));await flush();await flush();
  assert.equal(f.scope.phoneBrowserScreen.frame_id,'LIVE-P');assert.equal(f.calls.accept,1);
}
// Older server: no devices key, normal polling response applies.
{
  const f=fixture();f.api.deviceRevisions.accept(undefined);
  const p=f.api.syncState();f.fetches[0].resolve(f.json(f.state));await flush();f.fetches[1].resolve(f.json({}));await p;
  assert.equal(f.scope.browserScreen.frame_id,'LIVE-D');
}
console.log('PASS actual home.js syncState: pre-privacy responses dropped, device state cleared once, exit refresh applies, older servers keep polling');
