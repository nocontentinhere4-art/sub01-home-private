import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import {metricCylinderUv} from '../../web/house/material_uv.mjs';
for(const [radius,height] of [[.03,Math.hypot(3,4.25)],[.033,5.7],[.033,2.2]]){
 const geometry=new T.CylinderGeometry(radius,radius,height,10);
 const positions=Array.from(geometry.attributes.position.array);
 const normals=Array.from(geometry.attributes.normal.array);
 const originalIndices=Array.from(geometry.index.array);
 metricCylinderUv(geometry,radius,height,1.83);
 const p=geometry.attributes.position,n=geometry.attributes.normal,uv=geometry.attributes.uv;
 let minU=Infinity,maxU=-Infinity,minV=Infinity,maxV=-Infinity;
 for(let i=0;i<p.count;i++){
  if(Math.abs(n.getY(i))>.9){assert.ok(Math.abs(uv.getX(i)-p.getX(i)/1.83)<1e-7);assert.ok(Math.abs(uv.getY(i)-p.getZ(i)/1.83)<1e-7);}
  else {minU=Math.min(minU,uv.getX(i));maxU=Math.max(maxU,uv.getX(i));minV=Math.min(minV,uv.getY(i));maxV=Math.max(maxV,uv.getY(i));}
 }
 assert.ok(Math.abs(maxU-minU-2*Math.PI*radius/1.83)<1e-6);
 assert.ok(Math.abs(maxV-minV-height/1.83)<1e-6);
 assert.deepEqual(Array.from(p.array),positions);assert.deepEqual(Array.from(n.array),normals);
 assert.deepEqual(Array.from(geometry.index.array),originalIndices,'UV fix must preserve geometry/bake shape');
}
assert.throws(()=>metricCylinderUv(new T.CylinderGeometry(),0,1,1),/positive metres/);
console.log('PASS: source-metric circumferential/axial grain and circular caps, actual stair/loft rail dimensions, unchanged geometry/normals/indices');
