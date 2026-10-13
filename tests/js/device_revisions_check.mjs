import assert from 'node:assert/strict';
import {createDeviceRevisions} from '../../web/house/device_revisions.mjs';
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const base={computer:7,desk:'D:1',phone:'P:1',minecraft:'abc',console_game:'minecraft'};
let refreshes=0,privacyCalls=0,release=null;
const tracker=createDeviceRevisions({refresh:()=>{refreshes++;return new Promise(r=>{release=r;});},onPrivacy:()=>privacyCalls++});
// Older server: no devices object, page keeps polling.
assert.deepEqual(tracker.accept(undefined),[]);assert.deepEqual(tracker.accept(null),[]);await flush();assert.equal(refreshes,0);
// First message is the baseline; unchanged messages never refresh.
assert.deepEqual(tracker.accept(base),[]);assert.deepEqual(tracker.accept({...base}),[]);await flush();assert.equal(refreshes,0);
// One change refreshes once; changes during a running refresh coalesce into one more.
assert.deepEqual(tracker.accept({...base,computer:8}),['computer']);await flush();assert.equal(refreshes,1);
tracker.accept({...base,computer:8,minecraft:'def'});tracker.accept({...base,computer:8,minecraft:'ghi',phone:'P:2'});
await flush();assert.equal(refreshes,1,'no overlapping refresh');release();await flush();assert.equal(refreshes,2,'one coalesced follow-up');release();await flush();
console.log('PASS: older servers ignored; baseline and unchanged revisions do not refresh; changes refresh once and coalesce');
// Privacy: one clear, epoch bump, and a request started before entry is recognisably stale.
const before=tracker.epoch;
assert.deepEqual(tracker.accept({privacy:true}),[]);tracker.accept({privacy:true});
assert.equal(privacyCalls,1);assert.equal(tracker.private,true);assert.notEqual(tracker.epoch,before,'pre-privacy response is stale');
await flush();assert.equal(refreshes,2,'no refresh during privacy');
// Exit: everything refreshes once with a new epoch (late responses from inside privacy are stale too).
const inside=tracker.epoch;
assert.deepEqual(tracker.accept({...base,computer:8,minecraft:'ghi',phone:'P:2'}),['computer','desk','phone','minecraft','console_game']);
assert.notEqual(tracker.epoch,inside);await flush();assert.equal(refreshes,3);release();await flush();
assert.deepEqual(tracker.accept({...base,computer:8,minecraft:'ghi',phone:'P:2'}),[]);
console.log('PASS: privacy clears once, bumps the epoch on entry and exit, never refreshes inside, resynchronises after');
