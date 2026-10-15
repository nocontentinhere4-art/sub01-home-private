import test from 'node:test';
import assert from 'node:assert/strict';
import {Matrix4,Quaternion,Vector3} from '../web/house/vendor/three.core.js';
import {affineDirectionRotation} from '../tools/refine_serialized_phalange_affine.mjs';

test('capture direction survives an actual anisotropic parent instead of a scalar approximation',()=>{
 const parent=new Matrix4().makeScale(2,1,.5),wanted=new Vector3(1,1,1).normalize();
 const q=affineDirectionRotation(parent,new Quaternion(),[1,1,1],[1,0,0],wanted);
 const actual=new Vector3(1,0,0).applyQuaternion(q).transformDirection(parent);
 assert(actual.angleTo(wanted)<1e-7);
 const scalarGuess=new Vector3(1,0,0).applyQuaternion(new Quaternion().setFromUnitVectors(new Vector3(1,0,0),wanted)).transformDirection(parent);
 assert(scalarGuess.angleTo(wanted)>.3);
});

test('already aligned directions retain existing captured twist',()=>{
 const q=new Quaternion().setFromAxisAngle(new Vector3(1,0,0),.7),parent=new Matrix4();
 assert(q.angleTo(affineDirectionRotation(parent,q,[1,1,1],[1,0,0],new Vector3(1,0,0)))<1e-7);
});
