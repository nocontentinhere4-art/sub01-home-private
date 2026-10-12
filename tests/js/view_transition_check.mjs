import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createViewTransition,createViewTransitionOverlay} from '../../web/house/view-transition.mjs';
const paints=[];const overlay={paint:value=>paints.push({...value})};
let swaps=[];const view=createViewTransition({initialMode:'explore',overlay});
const swap=name=>()=>{assert.equal(paints.at(-1).opacity,1,'swap must happen behind fully opaque cover');assert.equal(view.state().phase,'covered');swaps.push(name);};
assert.equal(view.request('follow',swap('follow')),true);
view.step(.1);assert.equal(swaps.length,0);assert.ok(view.state().opacity<1);
view.step(.1);assert.equal(view.state().opacity,1);assert.equal(swaps.length,0,'first opaque frame cannot switch');
view.step(.02);assert.equal(swaps.length,0);view.step(.02);assert.deepEqual(swaps,['follow']);
assert.equal(view.currentMode,'follow');assert.equal(view.state().opacity,1);
view.step(.016);assert.equal(view.state().opacity,1,'post-swap frame still covered');
for(let i=0;i<20;i++)view.step(.02);assert.equal(view.busy,false);
assert.equal(view.request('follow',swap('repeat')),false);assert.deepEqual(swaps,['follow']);
// Cancel/reverse before swap must discard stale target/callback.
view.request('explore',swap('stale'));view.step(.08);
view.request('follow',swap('reverse'));for(let i=0;i<30;i++)view.step(.02);
assert.deepEqual(swaps,['follow']);assert.equal(view.currentMode,'follow');
view.request('explore',swap('cancelled'));view.step(.1);view.cancel();for(let i=0;i<30;i++)view.step(.02);
assert.deepEqual(swaps,['follow']);
view.request('explore',swap('covered-cancel'));view.step(.1);view.step(.1);
assert.equal(view.state().opacity,1);view.cancel();for(let i=0;i<30;i++)view.step(.02);
assert.deepEqual(swaps,['follow'],'cancel after opaque paint still discards unswapped callback');
// Latest request from a swap callback cannot be overwritten by its completion.
view.request('explore',()=>{swaps.push('explore');view.request('follow',swap('fresh'));});
for(let i=0;i<70;i++)view.step(.02);
assert.deepEqual(swaps,['follow','explore','fresh']);assert.equal(view.currentMode,'follow');
// Explore initialization/cancellation must invalidate an older Follow request.
view.request('explore',swap('stale-reset'));view.step(.08);view.reset('follow');
for(let i=0;i<30;i++)view.step(.02);
assert.deepEqual(swaps,['follow','explore','fresh']);assert.equal(view.currentMode,'follow');
// Reduced motion still paints one opaque frame before an immediate camera switch.
const reducedPaint=[];let moved=false;
const reduced=createViewTransition({initialMode:'explore',reducedMotion:true,overlay:{paint:v=>reducedPaint.push({...v})}});
reduced.request('follow',()=>{assert.equal(reducedPaint.at(-1).opacity,1);moved=true;});
assert.equal(moved,false);reduced.step(.04);assert.equal(moved,true);assert.equal(reduced.state().opacity,1);
reduced.step(.016);assert.equal(reduced.state().opacity,1);reduced.step(.016);assert.equal(reduced.busy,false);
// Overlay has no pointer interception and no scene/camera/sensitive content.
const element={style:{},dataset:{},setAttribute(){},remove(){this.removed=true;}};
const dom=createViewTransitionOverlay({createElement:()=>element,body:{append(){}}});
assert.ok(element.style.cssText.includes('pointer-events:none'));assert.ok(element.style.cssText.includes('z-index:10000'));
assert.ok(element.style.cssText.includes('transition:none'),'CSS cannot delay the controller opacity-one cover');
dom.paint({opacity:1,visible:true,label:'Switching view',phase:'covered'});assert.equal(element.textContent,'Switching view');
dom.dispose();assert.equal(element.removed,true);
const source=fs.readFileSync('web/house/view-transition.mjs','utf8');assert.ok(!source.includes('renderer.render('));assert.ok(!source.includes('requestAnimationFrame('));
console.log('PASS: earlier fully opaque paint before swap, covered post-swap frame, idempotence, cancellation/reversal, fresh callback precedence, reduced-motion protection and CSS-only noninteractive overlay');
