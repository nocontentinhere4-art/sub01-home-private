const assert = require('node:assert/strict');
const { viewerBootstrap } = require('../../games/minecraft/viewer_bootstrap.cjs');
function fixture() {
 let active = false, connects = 0, releases = 0, callback, clears = 0;
 const lease = viewerBootstrap({isActive: () => active, connect: () => connects++, release: () => releases++,
  setTimer: (fn, delay) => { assert.equal(delay, 20000); callback = fn; return 7; },
  clearTimer: id => { assert.equal(id, 7); clears++; }});
 return {lease, active: value => {active=value;}, expire: () => callback(),
  stats: () => ({active, connects, releases, clears})};
}
let f=fixture();
assert.equal(f.lease.allowed(),false);
assert.equal(f.lease.request(),true);
assert.equal(f.lease.allowed(),true);
assert.equal(f.stats().active,false,'idle bootstrap never grants autonomous activity');
assert.equal(f.lease.request(),false,'only one initial connection attempt');
f.lease.finish();f.lease.finish();
assert.deepEqual(f.stats(),{active:false,connects:1,releases:1,clears:1});
assert.equal(f.lease.allowed(),false);
assert.equal(f.lease.request(),false,'release does not reopen the initial lease');
f=fixture();f.lease.request();f.expire();
assert.deepEqual(f.stats(),{active:false,connects:1,releases:1,clears:1});
assert.equal(f.lease.allowed(),false,'timeout releases the idle connection independently of renderer success');
f=fixture();f.active(true);assert.equal(f.lease.request(),false);assert.equal(f.stats().connects,0);
f=fixture();f.lease.request();f.active(true);f.lease.finish();
assert.equal(f.stats().releases,0,'an independently authorized normal play handoff retains the real connection');
assert.equal(f.lease.allowed(),false);
console.log('Minecraft one-time idle viewer lease checks passed');
