// Authored owner animation only. Keep the entire skin and parent chain intact;
// omit head and neck triangles from rendering (the camera sits in the head), never edit a finger or bone pose.
import { clipRate } from '../room/gait.js';

function trianglesWhere(geometry, keep) {
  const index = geometry.index;
  const count = index ? index.count : keep.length;
  const out = [];
  for (let i = 0; i < count; i += 3) {
    const a = index ? index.getX(i) : i;
    const b = index ? index.getX(i + 1) : i + 1;
    const c = index ? index.getX(i + 2) : i + 2;
    if (keep[a] && keep[b] && keep[c]) out.push(a, b, c);
  }
  return out;
}
// per vertex: its skin weight on the bones whose names match
function boneWeights(geometry, bones, test) {
  const joints = geometry.getAttribute('skinIndex');
  const weights = geometry.getAttribute('skinWeight');
  if (!joints || !weights) return null;
  const hit = bones.map(b => test.test(b.name));
  const out = new Float32Array(joints.count);
  for (let v = 0; v < joints.count; v++) {
    let sum = 0;
    for (let k = 0; k < 4; k++) if (hit[joints.getComponent(v, k)]) sum += weights.getComponent(v, k);
    out[v] = sum;
  }
  return out;
}
// the arms alone: the seated captures at the desk (the rest of the body would sit in a chair the camera never shows)
export function armTriangleIndices(geometry, bones, threshold = .5) {
  const w = boneWeights(geometry, bones, /(?:Left|Right)(?:Arm|ForeArm|Hand)/);
  return w ? trianglesWhere(geometry, Uint8Array.from(w, x => x >= threshold)) : [];
}
// the body seen from its own eyes: everything but the head and the neck (the camera sits in the head; a face, hair or a
// collar seen from inside would fill the view: any skin a quarter weighted to them goes), so looking down shows the
// chest, the arms, the legs and the feet
export function bodyTriangleIndices(geometry, bones, threshold = .25) {
  const w = boneWeights(geometry, bones, /(?:Head|Neck|Eye|Jaw)/);
  return w ? trianglesWhere(geometry, Uint8Array.from(w, x => x < threshold)) : [];
}
// the hood's own meshes (its lining faces inward, around the camera): never part of the first-person body
export const NOT_FROM_THE_EYE = /hood/i;

// A command count is evidence of actual server input. First load establishes a
// baseline rather than replaying a stale command from before the viewer arrived.
export class FirstPersonActionEvidence {
  commands = null;
  typingUntil = 0;
  step(home, computer, now, following) {
    const count = Number(computer?.commands);
    if (Number.isFinite(count)) {
      if (this.commands !== null && count > this.commands && computer?.ready && !computer?.paused)
        this.typingUntil = now + 5;
      this.commands = count;
    }
    if (!following || !home || home.privacy) return 'hidden';
    if (home.walking) return 'walking_capture_required';
    if (home.activity === 'phone') return 'phone_capture_requires_retargeting';
    if (home.place === 'desk' && home.seated >= .99) {
      if (home.activity === 'use_computer' && computer?.ready && !computer?.paused && now < this.typingUntil)
        return 'typing';
      if (['research', 'use_computer', 'play_chess'].includes(home.activity)) return 'mouse_capture_required';
    }
    return 'relaxed_capture_required';
  }
}

// Matching labels are insufficient: animation-only FBXs can have a different
// rest skeleton. Direct playback requires the same local bind transforms.
export function matchingRestSkeleton(ownerBones, captureRoot, tolerance = .0001) {
  for (const bone of ownerBones.values()) {
    const source = captureRoot.getObjectByName(bone.name);
    if (!source || source.parent?.name !== bone.parent?.name) return false;
    if (source.position.distanceTo(bone.position) > tolerance ||
        source.scale.distanceTo(bone.scale) > tolerance ||
        1 - Math.abs(source.quaternion.dot(bone.quaternion)) > tolerance) return false;
  }
  return true;
}

// Where the owner's eyes are up the head: the fraction of the way from the Head joint to HeadTop_End (the Mixamo
// skeleton: the Head joint sits at the skull's base, the top 27 cm above it; the eye line ~58 % up, 1.61 m on this body),
// and how far forward of that joint (the face): the camera stands there, clear of the skull and the collar
export const EYE_ON_HEAD = .58;
export const EYE_FORWARD = .12;
export const EYE_FALLBACK = 1.61;
// the server's walking-eye height (home_world.py NODES): the camera it hands the page
export const CAMERA_EYE = 1.65;

export const FIRST_PERSON_CAPTURES = {
  owner: '/house/assets/first-person/owner.glb',
  typing: { url: '/house/assets/first-person/typing.glb', visualAccepted: false,
    reason: 'Original reference typing contact restored; camera and anatomy visual review required',
    position: [2.039, -.006, -2.323], yaw: Math.PI },
  // the walk: the body but the head, standing on the floor under the camera with its eyes at the camera, its cadence from
  // the server's speed (room/gait.js). refSpeed: the capture's authored travel, its planted foot moves back at 1.3-1.4 m/s
  // (1.03 s a loop of two steps: a 0.72 m step), measured in docs/design/natural-motion/2026-10-23
  walking: { url: '/house/assets/first-person/walking.glb', visualAccepted: true, inPlace: true, body: true, refSpeed: 1.4,
    reason: 'Reviewed headless from the eye (docs/design/natural-motion/2026-10-23/fp_walk_*.png): the chest, the swinging arms and the legs with the feet on the floor; cadence from the server speed' },
  // standing: the walk capture's first frame held (a staggered stance; from the eye a body standing on the floor,
  // docs/design/natural-motion/2026-10-23/fp_idle_down.png), on his feet only: never under a seated camera
  idle: { url: '/house/assets/first-person/walking.glb', visualAccepted: true, holdFirstFrame: true, body: true, standingOnly: true,
    reason: 'The captured base pose is the walk\'s first frame held still, shown while he is on his feet; a relaxed standing capture would replace it' },
  phone: { url: '/house/assets/first-person/texting.glb', visualAccepted: false,
    reason: 'One-handed texting: right palm, thumb and real phone contact awaiting measurement and visual review' },
};

// The live server supplies world travel. Remove only captured horizontal hips
// translation to prevent doubled movement and a positional pop at every loop.
// Every authored rotation, vertical step and finger track remains untouched.
export function inPlaceCapture(clip) {
  const copy = clip.clone();
  for (const track of copy.tracks) if (/Hips\.position$/.test(track.name)) {
    for (let i = 0; i < track.values.length; i += 3) {
      track.values[i] = track.values[0];
      track.values[i + 2] = track.values[2];
    }
  }
  return copy;
}

export function capturedBasePose(T, clip) {
  const tracks = clip.tracks.map(track => {
    const size = track.getValueSize();
    const first = Array.from(track.values.slice(0, size));
    return new track.constructor(track.name, [0, 1], [...first, ...first]);
  });
  return new T.AnimationClip(clip.name + '-captured-base', 1, tracks);
}

// the walk capture's playback rate at the server's speed (m/s): the capture keeps its own step (no standing capture to
// shorten the stride toward, so its share is 1) and its cadence is speed / step: 1.67 steps/s at 1.2 m/s, the planted
// foot keeping pace with the floor. No speed (an older server): as recorded
export function walkRate(speed, refSpeed = FIRST_PERSON_CAPTURES.walking.refSpeed) {
  const v = Number(speed);
  return Number.isFinite(v) && v > 0 ? clipRate(v, 1, refSpeed) : 1;
}

export function createFirstPersonBody(T, scene, loader, onStatus = () => {}, captures = FIRST_PERSON_CAPTURES) {
  const group = new T.Group();
  group.name = 'authored-first-person-arms';
  group.visible = false;
  scene.add(group);
  const evidence = new FirstPersonActionEvidence();
  const actions = new Map();
  const parts = [];                                     // the skinned meshes: {mesh, body} (the arms alone, or the body but the head)
  let mixer, activeAction, ownerRoot, hips, head, eyeHeight = EYE_FALLBACK, available = false, previous = '';
  const modes = ['typing', 'walking', 'phone', 'idle'];
  const ready = Promise.all([
    loader.loadAsync(captures.owner),
    ...modes.map(mode => loader.loadAsync(captures[mode].url)),
  ]).then(([owner, ...clips]) => {
    let triangles = 0, bodyTriangles = 0;
    const skinned = [];
    owner.scene.traverse(mesh => {
      if (!mesh.isMesh) return;
      if (!mesh.isSkinnedMesh) { mesh.visible = false; return; }
      skinned.push(mesh);
    });
    for (const mesh of skinned) {
      const arms = armTriangleIndices(mesh.geometry, mesh.skeleton.bones);
      const body = NOT_FROM_THE_EYE.test(mesh.name) ? [] : bodyTriangleIndices(mesh.geometry, mesh.skeleton.bones);
      mesh.frustumCulled = false;
      mesh.castShadow = false;
      mesh.receiveShadow = true;
      // the same skin twice, each a sibling bound to the one skeleton: the arms for the seated captures, the body for
      // the walk; a mode shows one of them (no bone, weight or bind matrix changes)
      if (body.length) {
        const bodyMesh = mesh.clone();
        const geometry = mesh.geometry.clone();
        geometry.setIndex(body);
        geometry.clearGroups();
        bodyMesh.geometry = geometry;
        bodyMesh.name = mesh.name + '_body';
        bodyMesh.bind(mesh.skeleton, mesh.bindMatrix);
        bodyMesh.visible = false;
        mesh.parent.add(bodyMesh);
        parts.push({ mesh: bodyMesh, body: true });
        bodyTriangles += body.length / 3;
      }
      if (!arms.length) { mesh.visible = false; continue; }
      const geometry = mesh.geometry.clone();
      geometry.setIndex(arms);
      geometry.clearGroups();
      mesh.geometry = geometry;
      mesh.visible = false;
      parts.push({ mesh, body: false });
      triangles += arms.length / 3;
    }
    if (!triangles) throw new Error('Owner skin has no weighted arm triangles');
    const bones = new Map();
    owner.scene.traverse(o => { if (o.isBone) bones.set(o.name, o); });
    mixer = new T.AnimationMixer(owner.scene);
    for (let i = 0; i < modes.length; i++) {
      const capture = clips[i], mode = modes[i], clip = capture.animations[0];
      if (!matchingRestSkeleton(bones, capture.scene))
        throw new Error(mode + ' capture rest skeleton requires retargeting');
      if (!clip || !clip.tracks.every(track => bones.has(track.name.slice(0, track.name.lastIndexOf('.')))))
        throw new Error(mode + ' capture does not match the complete owner skeleton');
      const playable = captures[mode].holdFirstFrame ? capturedBasePose(T, clip) : captures[mode].inPlace ? inPlaceCapture(clip) : clip;
      actions.set(mode, mixer.clipAction(playable));
    }
    ownerRoot = owner.scene;
    hips = [...bones.values()].find(b => /Hips$/.test(b.name));
    head = [...bones.values()].find(b => /Head$/.test(b.name));
    const top = [...bones.values()].find(b => /HeadTop_End$/.test(b.name));
    owner.scene.updateMatrixWorld(true);
    if (head && top) {                                  // the eye line on the rest pose: between the Head joint and the skull's top
      const hy = head.getWorldPosition(new T.Vector3()).y, ty = top.getWorldPosition(new T.Vector3()).y;
      if (ty > hy) eyeHeight = hy + EYE_ON_HEAD * (ty - hy);
    }
    group.add(ownerRoot);
    available = true;
    onStatus({ state: 'loaded-awaiting-review', armTriangles: triangles, bodyTriangles, eyeHeight: +eyeHeight.toFixed(3),
      accepted: modes.filter(mode => captures[mode].visualAccepted),
      gates: Object.fromEntries(modes.map(mode => [mode, captures[mode].reason])),
      mouse: 'Authored mouse capture missing' });
    return true;
  }).catch(error => {
    onStatus({ state: 'unavailable', reason: error.message });
    return false;
  });
  return {
    ready,
    group,
    get eyeHeight() { return eyeHeight; },
    // floorAt(x, z): the page's floor height under a point (null: unknown); the body stands on it
    step(dt, home, computer, now, following, camera, floorAt) {
      const requested = evidence.step(home, computer, now, following);
      const onFeet = !(home?.seated > 0) && home?.place !== 'desk';   // (a seated camera is lower: a standing body would rise into it)
      const mode = requested === 'typing' ? 'typing' : requested === 'walking_capture_required' ? 'walking' :
        requested === 'phone_capture_requires_retargeting' ? 'phone' :
        requested === 'relaxed_capture_required' && (onFeet || !captures.idle.standingOnly) ? 'idle' : null;
      group.visible = !!(available && mode && captures[mode].visualAccepted);
      if (group.visible) {
        const action = actions.get(mode);
        const body = !!captures[mode].body;
        for (const p of parts) p.mesh.visible = p.body === body;
        if (activeAction !== action) {
          activeAction?.fadeOut(.24);
          action.reset().setEffectiveWeight(1).fadeIn(.24).play();
          activeAction = action;
        }
        if (mode === 'walking') action.timeScale = walkRate(home?.speed, captures.walking.refSpeed);   // the cadence from his speed
        mixer.update(Math.min(dt, .05));
        if (captures[mode].position) {
          group.position.fromArray(captures[mode].position);
          group.rotation.y = captures[mode].yaw || 0;
          group.scale.setScalar(1);
        }
        if ((mode === 'walking' || mode === 'idle') && camera && hips) {
          // The camera follows the brain's actual route; the body stands under it, facing where the camera looks: its feet
          // on the floor there (the page's floorAt; else the camera's eye height down), its eyes at the camera (a uniform
          // scale of the whole group, 0.9-1.15: the server walks at 1.65 m eye height, this body's eyes are 1.61 m up) and
          // its eye point (EYE_FORWARD ahead of the Head joint, the face) under the camera. Root placement only: no bone
          // pose changes
          const yaw = camera.rotation.y + Math.PI;
          group.rotation.y = yaw;
          const floor = typeof floorAt === 'function' ? floorAt(camera.position.x, camera.position.z) : null;
          const base = Number.isFinite(floor) ? floor : camera.position.y - CAMERA_EYE;
          const scale = Math.min(1.15, Math.max(.9, (camera.position.y - base) / eyeHeight));
          group.scale.setScalar(scale);
          group.position.set(0, base, 0); group.updateMatrixWorld(true);
          const under = (head || hips).getWorldPosition(new T.Vector3());
          under.x += Math.sin(yaw) * EYE_FORWARD * scale; under.z += Math.cos(yaw) * EYE_FORWARD * scale;   // (the body faces +z in its own frame)
          group.position.set(camera.position.x - under.x, base, camera.position.z - under.z);
        }
      } else if (activeAction) {
        activeAction.stop(); activeAction = null;
      }
      const state = group.visible ? mode : mode ? mode + '_review_required' : requested;
      if (state !== previous) onStatus({ state, visible: group.visible,
        reason: mode ? captures[mode].reason : 'No verified relaxed or mouse capture',
        authored: group.visible });
      previous = state;
    },
  };
}
