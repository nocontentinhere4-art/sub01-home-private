import assert from 'node:assert/strict';
import {sameVertexPositions} from '../../web/house/bake_shape.mjs';
const original = [0,0,0, 1,1,1, .4,.86,.3, .6,.86,.3];
const changed = [0,0,0, 1,1,1, .4,.70,.3, .6,.70,.3];
assert.equal(sameVertexPositions(original,changed),false); // same count and outer bounds, moved cabinet top
assert.equal(sameVertexPositions(original,[...original.slice(6),...original.slice(0,6),...original.slice(6)]),true); // reordered UV seam duplicates
assert.equal(sameVertexPositions(original,original.map(v=>v+.00001)),true);
assert.equal(sameVertexPositions(original,original.map(v=>v+.02)),false);
assert.equal(sameVertexPositions(original,[NaN,...original.slice(1)]),false);
console.log('PASS: reject interior batch changes; allow UV reordering, seams and export rounding');
