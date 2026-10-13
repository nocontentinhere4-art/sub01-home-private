import assert from 'node:assert/strict';
import { streetAccessAllows as terraceAllows } from '../../web/house/street_access.mjs';
assert.equal(terraceAllows(2,3.95),true);
assert.equal(terraceAllows(1.5,3.95),false); // cannot cut through the door frame
assert.equal(terraceAllows(2.5,3.95),false);
for (const x of [1,1.5,2,2.5,3]) {
  for (const z of [4.2,4.9,5.5]) assert.equal(terraceAllows(x,z),true);
}
assert.equal(terraceAllows(.8,4.8),false);
assert.equal(terraceAllows(3.2,4.8),false);
assert.equal(terraceAllows(2,5.8),true);
assert.equal(terraceAllows(1.2,5.8),false);
assert.equal(terraceAllows(2,8.61),false);
console.log('Courtyard: doorway and rail edges respected; new street passage open and road bounded.');
