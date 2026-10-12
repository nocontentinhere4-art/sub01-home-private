import assert from 'node:assert/strict';
import {BoxGeometry} from '../../web/house/vendor/three.module.js';
import {metricBoxUv} from '../../web/house/material_uv.mjs';
for (const width of [.65, 3.05]) {
  const geometry = new BoxGeometry(width, .76, .035);
  const original = geometry.attributes.position.array.slice();
  metricBoxUv(geometry, .8);
  const position=geometry.attributes.position, normal=geometry.attributes.normal, uv=geometry.attributes.uv;
  const front=[];
  for(let i=0;i<position.count;i++) if(normal.getZ(i)>.99) front.push(uv.getX(i));
  assert.ok(Math.abs(Math.max(...front)-Math.min(...front)-width/.8)<1e-6);
  assert.deepEqual(position.array,original); // collision/bake world shape is unchanged
}
console.log('PASS: grain scales in metres across cabinet sizes; geometry positions preserved');
