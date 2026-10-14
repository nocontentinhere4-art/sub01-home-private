const assert = require('node:assert/strict');
const { createRenderBudget } = require('../../games/minecraft/viewer_readiness.cjs');
let now=0, draws=0, updates=0, controlUpdates=0;
const viewer={scene:{realGeometry:true},camera:{realCamera:true},update(){updates++;}};
const renderer={getContext(){return {VENDOR:1,RENDERER:2,getExtension(){return null;},getParameter(k){return k===1?'actual fixture vendor':'actual fixture renderer';}};},
 render(scene,camera){assert.equal(scene,viewer.scene);assert.equal(camera,viewer.camera);draws++;now+=2;}};
const budget=createRenderBudget(renderer,viewer,{update(){controlUpdates++;}},()=>now);
assert.equal(budget.draw(),true);
for(const t of [10,20,30,40,50,60]){now=t;assert.equal(budget.draw(),false);}
now=67;assert.equal(budget.draw(),true);now=134;assert.equal(budget.draw(),true);
assert.equal(draws,3);assert.equal(updates,3);assert.equal(controlUpdates,3);
const d=budget.diagnostics();assert.equal(d.target_fps,15);assert.equal(d.frames,3);assert.equal(d.attempts,9);
assert.equal(d.draw_duration_ms,2);assert.equal(d.total_draw_ms,6);assert.ok(d.observed_fps<=15);assert.equal(d.vendor,'actual fixture vendor');
now=NaN;assert.equal(budget.draw(),false);assert.equal(draws,3);
const unavailable=createRenderBudget({getContext(){throw Error('context unavailable');},render(){}},viewer,null,()=>0);
assert.equal(unavailable.diagnostics().renderer,null);assert.equal(unavailable.draw(),true);
console.log('Actual draw budget preserves scene/camera and reports measured cadence/context without guessing renderer');
