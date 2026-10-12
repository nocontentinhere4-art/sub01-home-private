import assert from 'node:assert/strict';
import {ShadowRefresh} from '../../web/house/shadow_refresh.mjs';
for (const rate of [30,60]) {
  const cache=new ShadowRefresh();
  for(let i=0;i<rate*3;i++) assert.equal(cache.step(1/rate,false),false);
  assert.equal(cache.count,0);
  for(let i=0;i<rate;i++) cache.step(1/rate,true);
  assert.ok(cache.count<=9 && cache.count>=7);
  const before=cache.count;
  assert.equal(cache.step(1/rate,false),true); // final pose always rendered, even below the rate interval
  assert.equal(cache.count,before+1);
  for(let i=0;i<rate;i++) assert.equal(cache.step(1/rate,false),false);
}
console.log('PASS: quiet doors keep cached shadows; motion is bounded and final poses refresh');
