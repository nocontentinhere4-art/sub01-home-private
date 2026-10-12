import assert from 'node:assert/strict';
import {FirstPersonLook, shortestAngle} from '../../web/house/first_person_look.mjs';
function run(dt) {
  const look = new FirstPersonLook(Math.PI - .02, 0);
  const target = [.02, 1.65, 1];
  let maxStep = 0;
  for(let t=0;t<2;t+=dt) {
    const previous = look.yaw;
    look.step(dt,[0,1.65,0],target);
    maxStep = Math.max(maxStep,Math.abs(shortestAngle(look.yaw-previous)));
    assert.equal(look.pitch,0);
  }
  assert.ok(maxStep < .05); // cross the +/-pi seam by the short turn
  return look.yaw;
}
assert.ok(Math.abs(shortestAngle(run(1/30)-run(1/60)))<.002);
const look=new FirstPersonLook();
for(let i=0;i<300;i++) {
  const yaw=look.yaw,pitch=look.pitch;
  look.step(1/60,[0,1.65,0],[0,-10,1]);
  assert.ok(Math.abs(shortestAngle(look.yaw-yaw))<=1.8/60+1e-9);
  assert.ok(Math.abs(look.pitch-pitch)<=1.2/60+1e-9);
  assert.ok(look.pitch>=-1.25);
}
const still=[look.yaw,look.pitch];
assert.deepEqual(look.step(.1,[1,1,1],[1,1,1]),still);
console.log('PASS: shortest turns, bounded angular speed, level walking, 30/60 fps agreement and coincident target');
