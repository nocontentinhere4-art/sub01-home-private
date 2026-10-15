import test from 'node:test';
import assert from 'node:assert/strict';
import {Quaternion,Vector3,Matrix4} from '../web/house/vendor/three.core.js';
import {relativeHandRotation} from '../tools/retarget_relaxed_hand_motion.mjs';
const rot=(axis,angle)=>new Quaternion().setFromAxisAngle(new Vector3(...axis).normalize(),angle);
const q=v=>new Quaternion().fromArray(v);
const same=(a,b)=>assert(q(a).angleTo(q(b))<1e-7);

test('new relaxed anatomy stays at its own rest when capture is at baseline',()=>{
 const rest=rot([1,2,3],.62).toArray(),baseline=rot([2,-1,1],1.1).toArray();
 same(relativeHandRotation(rest,baseline,baseline,rot([0,1,0],.9).toArray(),rot([1,0,0],-.5).toArray()),rest);
});
test('transfers variation rather than applying the preexisting captured curl twice',()=>{
 const rest=rot([1,0,0],.3),baseline=rot([1,0,0],.7),pose=rot([1,0,0],.8),identity=[0,0,0,1];
 same(relativeHandRotation(rest.toArray(),baseline.toArray(),pose.toArray(),identity,identity),rot([1,0,0],.4).toArray());
});
test('different bone axes preserve the increment in world coordinates, matrix oracle',()=>{
 const rest=rot([1,2,0],.4),base=rot([0,1,1],-.5),delta=rot([1,-2,3],.21);
 const sw=rot([2,1,0],.8),tw=rot([1,0,3],-.9),pose=base.clone().multiply(delta);
 const result=q(relativeHandRotation(rest.toArray(),base.toArray(),pose.toArray(),sw.toArray(),tw.toArray()));
 const actualDelta=rest.clone().invert().multiply(result);
 const matrix=x=>new Matrix4().makeRotationFromQuaternion(x);
 const actual=matrix(tw).multiply(matrix(actualDelta)).multiply(matrix(tw).invert());
 const expected=matrix(sw).multiply(matrix(delta)).multiply(matrix(sw).invert());
 assert(Math.max(...actual.elements.map((x,i)=>Math.abs(x-expected.elements[i])))<1e-12);
});
test('quaternion signs do not reverse either hand motion',()=>{
 for(const side of [-1,1]){
  const rest=rot([0,1,0],side*.3).toArray(),base=rot([1,0,0],side*.6).toArray(),pose=rot([1,0,0],side*.75).toArray(),id=[0,0,0,1];
  same(relativeHandRotation(rest,base,pose,id,id),relativeHandRotation(rest,base.map(x=>-x),pose.map(x=>-x),id,id));
 }
});
test('invalid bone frames cannot silently become identity rotations',()=>{
 const id=[0,0,0,1];
 for(const bad of [[0,0,0,0],[NaN,0,0,1],[0,0,Infinity,1]]){
  assert.throws(()=>relativeHandRotation(bad,id,id,id,id));
  assert.throws(()=>relativeHandRotation(id,id,id,bad,id));
 }
});
