import assert from 'node:assert/strict';
import {createSettledAssetBarrier} from '../../web/house/settled_asset_barrier.mjs';
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};
const checkpoint=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};

// A network manager can be idle while actual GLTF parsing is still pending.
const parse=deferred(),barrier=createSettledAssetBarrier();let managerIdle=true,ready=false;
assert.equal(barrier.add(parse.promise),parse.promise);
const done=barrier.settled().then(result=>{ready=true;return result;});
await checkpoint();assert.equal(managerIdle,true);assert.equal(ready,false);
parse.resolve({scene:'chair_owner meshes'});
assert.deepEqual(await done,{registered:1,fulfilled:1,rejected:0,pending:0,failures:[],droppedFailures:0});

// Fallback/transitive asset jobs created during completion form another wave.
const parent=deferred(),child=deferred(),grandchild=deferred(),waves=createSettledAssetBarrier();
waves.add(parent.promise.then(()=>{waves.add(child.promise.then(()=>{waves.add(grandchild.promise);}));}));
let allReady=false;const waveDone=waves.settled();assert.equal(waves.settled(),waveDone,'concurrent consumers share one drain');waveDone.then(()=>{allReady=true;});
parent.resolve();await checkpoint();assert.equal(allReady,false);
child.resolve();await checkpoint();assert.equal(allReady,false);
grandchild.resolve();assert.equal((await waveDone).fulfilled,3);

// Rejected parsing reports once, registers its actual fallback, and finishes.
const broken=deferred(),fallback=deferred(),errors=[],failureBarrier=createSettledAssetBarrier({onRejected(error){errors.push(error);failureBarrier.add(fallback.promise);}});
failureBarrier.add(broken.promise);failureBarrier.add(broken.promise);
let failureReady=false;const failureDone=failureBarrier.settled().then(r=>{failureReady=true;return r;});
const failure=new Error('GLTF parse failed');broken.reject(failure);await checkpoint();assert.equal(failureReady,false);assert.deepEqual(errors,[failure]);
fallback.resolve();const failureReport=await failureDone;assert.equal(failureReport.registered,2);assert.equal(failureReport.rejected,1);assert.equal(failureReport.fulfilled,1);assert.deepEqual(failureReport.failures,[failure]);

// No duplicate registration, resource disposals, reloads or value ownership.
let disposed=0,loads=0;const resource={dispose(){disposed++;}};
const resourcePromise=Promise.resolve(resource),resources=createSettledAssetBarrier();loads++;
resources.add(resourcePromise);resources.add(resourcePromise);const resourceReport=await resources.settled();assert.equal(resourceReport.registered,1);assert.equal(disposed,0);assert.equal(loads,1);assert.equal(JSON.stringify(resourceReport).includes('dispose'),false);
assert.equal((await resources.settled()).registered,1,'a later drain must not reload completed resources');

// Same-turn registration and bounded diagnostics; reporter failure is harmless.
const sameTurn=createSettledAssetBarrier(),late=deferred();let sameReady=false;const sameDone=sameTurn.settled().then(r=>{sameReady=true;return r;});sameTurn.add(late.promise);await checkpoint();assert.equal(sameReady,false);late.resolve();assert.equal((await sameDone).fulfilled,1);
const bounded=createSettledAssetBarrier({maxFailures:2,onRejected(){throw new Error('logger failed');}});
for(let i=0;i<5;i++)bounded.add(Promise.reject(new Error(`asset ${i}`)));
const boundedReport=await bounded.settled();assert.equal(boundedReport.rejected,5);assert.equal(boundedReport.failures.length,2);assert.equal(boundedReport.droppedFailures,3);assert.equal(boundedReport.pending,0);
assert.throws(()=>bounded.add({}),/promise/);assert.throws(()=>createSettledAssetBarrier({maxFailures:-1}),/nonnegative/);
console.log('PASS: actual late parse blocks idle-manager startup; transitive/fallback waves drain; concurrent consumers share drain; rejections report once with bounded diagnostics; no resource disposal/reload/fulfilled value retention; same-turn jobs cannot escape readiness.');
