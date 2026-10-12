import assert from 'node:assert/strict';
import { terraceAllows } from '../../web/house/terrace_space.mjs';
assert.equal(terraceAllows(2,3.95),true);
assert.equal(terraceAllows(1.5,3.95),false); // cannot cut through the door frame
assert.equal(terraceAllows(2.5,3.95),false);
for (const x of [1,1.5,2,2.5,3]) {
  for (const z of [4.2,4.9,5.5]) assert.equal(terraceAllows(x,z),true);
}
assert.equal(terraceAllows(.8,4.8),false);
assert.equal(terraceAllows(3.2,4.8),false);
assert.equal(terraceAllows(2,5.8),false);
console.log('Terrace: full width walkable; doorway frame and rail edges respected.');
