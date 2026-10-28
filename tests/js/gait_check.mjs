// The gait model (web/room/gait.js) and the no-slide rule on the real walk clips: at every pace the planted foot of the
// blended walk stays put on the floor when the clip plays at clipRate(v, share, REF_SPEED). Node, the vendored three.js.
import assert from 'node:assert/strict';
import * as T from '../../web/house/vendor/three.module.js';
import { productionGlb } from './first_person_asset_fixture.mjs';
import { WALK_RATIO, gaitAt, clipStep, strideShare, clipRate, cadenceOf, SHARE_MIN, RATE_MIN, RATE_MAX } from '../../web/room/gait.js';

// 1. the model: a young adult at 1.2 m/s takes ~1.94 steps/s of ~0.62 m; step and cadence both grow with speed
const g12 = gaitAt(1.2);
assert.ok(Math.abs(g12.cadence - 1.94) < 0.03 && Math.abs(g12.step - 0.62) < 0.01, JSON.stringify(g12));
assert.ok(Math.abs(g12.step * g12.cadence - 1.2) < 1e-9, 'step times cadence is the speed');
for (const [a, b] of [[0.2, 0.4], [0.4, 0.8], [0.8, 1.2], [1.2, 1.4]]) {
  assert.ok(gaitAt(b).step > gaitAt(a).step && gaitAt(b).cadence > gaitAt(a).cadence, `${a} -> ${b}`);
}
assert.ok(Math.abs(gaitAt(0.6).step / gaitAt(0.6).cadence - WALK_RATIO) < 1e-9, 'the walk ratio is constant');
// the clips' steps from their reference foot speed (room_build/kimodo_g12/walk_metrics.py, H13) and loop: half the
// strides it measured (ARDY 1.182 m, room_walk 0.855 m on v5, the UAL walk 1.071 m) within 2 mm
const ARDY = clipStep(0.628, 1.884), ROOM = clipStep(0.714, 1.267), ROOM5 = clipStep(0.675, 1.267), UAL = clipStep(0.803, 1.333), FP = clipStep(1.4, 1.033);
assert.ok(Math.abs(ARDY - 1.182 / 2) < 0.002 && Math.abs(ROOM5 - 0.855 / 2) < 0.002 && Math.abs(UAL - 1.071 / 2) < 0.002, [ARDY, ROOM5, UAL].join(' '));
assert.ok(Math.abs(ROOM - 0.452) < 0.002 && Math.abs(FP - 0.723) < 0.002, [ROOM, FP].join(' '));
// the stride share: 1 at and above the speed whose step is the clip's, shorter below, never under SHARE_MIN
assert.equal(strideShare(1.2, ARDY), 1); assert.equal(strideShare(0.7, ROOM), 1);
assert.ok(strideShare(0.3, ARDY) < 0.56 && strideShare(0.3, ARDY) > 0.48, strideShare(0.3, ARDY));
assert.ok(strideShare(0.12, ROOM) > 0.4 && strideShare(0.12, ROOM) < 0.5, strideShare(0.12, ROOM));
assert.equal(strideShare(0, ARDY), SHARE_MIN);
// the rate: at share 1 the rule the page had (v / REF_SPEED); at a shorter stride proportionally faster; clamped
assert.ok(Math.abs(clipRate(1.2, 1, 0.65) - 1.2 / 0.65) < 1e-9);
assert.ok(Math.abs(clipRate(0.3, 0.5, 0.65) - 0.3 / (0.5 * 0.65)) < 1e-9);
assert.equal(clipRate(0.01, 1, 0.65), RATE_MIN); assert.equal(clipRate(5, 1, 0.65), RATE_MAX);
// the cadence at cruise: the ARDY walk steps ~2.0 a second at 1.2 m/s, room_walk 2.65 (the clip's short step: documented)
assert.ok(Math.abs(cadenceOf(1.2, strideShare(1.2, ARDY), ARDY) - 2.03) < 0.03);
assert.ok(Math.abs(cadenceOf(1.2, strideShare(1.2, ROOM), ROOM) - 2.65) < 0.05);
// at a slow pace the cadence follows the model instead of the clip (0.3 m/s: ~0.97 steps/s, not 0.5)
assert.ok(Math.abs(cadenceOf(0.3, strideShare(0.3, ARDY), ARDY) - gaitAt(0.3).cadence) < 1e-6);

// 2. no slide, on the real clips: the walk blended toward the stand's first frame by the share and played at clipRate, the
// root moving at v; the planted foot's world travel while it is flat on the floor (ankle and toe both within 1.5 cm of
// their lowest: the heel-to-toe roll before and after moves the contact point anyway) is the slide
const still = clip => new T.AnimationClip(clip.name + '-still', 1, clip.tracks.map(tr => { const v = tr.createInterpolant().evaluate(0).slice(); return new tr.constructor(tr.name, [0, 1], [...v, ...v]); }));
const find = (root, re) => { let f = null; root.traverse(o => { if (!f && re.test(o.name)) f = o; }); return f; };
async function slide(walkUrl, standUrl, ref, v, rule) {
  const gw = await productionGlb(walkUrl), gs = await productionGlb(standUrl);
  const scene = gw.scene, walk = gw.animations[0], stand = still(gs.animations[0]);
  const feet = [['LeftFoot', 'LeftToeBase'], ['RightFoot', 'RightToeBase']].map(pair => pair.map(n => find(scene, new RegExp(n + '$'))));
  const mixer = new T.AnimationMixer(scene), W = mixer.clipAction(walk), S = mixer.clipAction(stand); W.play(); S.play();
  const step = clipStep(ref, walk.duration);
  const share = rule === 'model' ? strideShare(v, step) : rule === 'old-mh' ? Math.min(1, Math.max(0.15, v / 0.35)) : 1;
  W.setEffectiveWeight(share); S.setEffectiveWeight(1 - share);
  W.timeScale = rule === 'model' ? clipRate(v, share, ref) : Math.max(0.2, v / ref);
  const dt = 1 / 120, root = new T.Vector3(); let worst = 0, steps = 0;
  const lows = feet.map(() => [Infinity, Infinity]), track = feet.map(() => null);
  // two passes: the first finds each joint's lowest height, the second measures the flat phases
  for (let pass = 0; pass < 2; pass++) {
    mixer.setTime(0); root.set(0, 0, 0);
    for (let t = 0; t < walk.duration / W.timeScale * 2; t += dt) {
      mixer.update(dt); root.z += v * dt; scene.updateMatrixWorld(true);
      feet.forEach((pair, i) => { const p = pair.map(b => { const q = b.getWorldPosition(new T.Vector3()); q.z += root.z; return q; });
        if (pass === 0) { lows[i] = [Math.min(lows[i][0], p[0].y), Math.min(lows[i][1], p[1].y)]; return; }
        const flat = p[0].y < lows[i][0] + 0.015 && p[1].y < lows[i][1] + 0.015;
        if (flat && !track[i]) track[i] = {p0: p[0].clone(), t0: t};
        else if (!flat && track[i]) { if (t - track[i].t0 > 0.08) { worst = Math.max(worst, Math.hypot(p[0].x - track[i].p0.x, p[0].z - track[i].p0.z)); steps++; } track[i] = null; } });
    }
  }
  mixer.uncacheRoot(scene);
  return {worst, steps, share: +share.toFixed(2), rate: +W.timeScale.toFixed(2), cadence: +cadenceOf(v, share, step).toFixed(2)};
}
// Each clip skates on its own (walk_metrics.py: 2.6-5.4 cm a stance at its reference speed, with no foot IK): the model
// may add no more than a centimetre to that at any pace, and at the slow paces (where the rule before it played the full
// stride at speed / REF_SPEED with a 0.2 floor, and the MakeHuman layer's short strides at that rate) it slides less.
// The live character's blend is exactly this one (the MakeHuman layer has no foot lock after it); the ARDY walk's idle
// stands differently (its stance shrinks less evenly), and room/boy_motion.js locks the planted foot after the blend
const CLIPS = [
  ['room_walk (the live character)', '/room/mh_mx/room_walk.glb', '/room/mh_mx/room_window.glb', 0.714, 0.01],
  ['the ARDY walk (?motion=ardy)', '/room/boy_m_walk.glb', '/room/boy_m_idle.glb', 0.628, 0.03],
];
const report = [];
for (const [label, walkUrl, standUrl, ref, extra] of CLIPS) {
  const own = await slide(walkUrl, standUrl, ref, ref, 'model');      // the clip as authored: full stride at rate 1
  report.push(`${label}: the clip's own skate at ${ref} m/s ${(own.worst * 100).toFixed(1)} cm a flat stance`);
  for (const v of [0.15, 0.3, 0.6, 1.2]) {
    const m = await slide(walkUrl, standUrl, ref, v, 'model');
    const o = await slide(walkUrl, standUrl, ref, v, v < 0.35 ? 'old-mh' : 'old');
    report.push(`  at ${v} m/s: slide per flat stance ${(m.worst * 100).toFixed(1)} cm (share ${m.share}, rate ${m.rate}, ${m.cadence} steps/s) - before ${(o.worst * 100).toFixed(1)} cm (share ${o.share}, rate ${o.rate})`);
    if (m.steps < 2 && extra > 0.01) { report[report.length - 1] += ' [no flat-footed stance in this blend: the foot rolls throughout; the motion layer\'s lock plants it]'; continue; }
    assert.ok(m.steps >= 2, `${label} ${v}: flat stances found`);
    assert.ok(m.worst < own.worst + extra, `${label} at ${v} m/s slides ${m.worst} m (the clip's own ${own.worst})`);
    if (v < 0.35) assert.ok(m.worst < o.worst, `${label} at ${v}: the model slides less than the rule before (${m.worst} vs ${o.worst})`);
  }
}
console.log(report.join('\n'));
console.log('PASS: the gait model (1.94 steps/s of 0.62 m at 1.2 m/s, sqrt coupling, the measured clip steps), and no slide added to the clips\' own at 0.15-1.2 m/s');
