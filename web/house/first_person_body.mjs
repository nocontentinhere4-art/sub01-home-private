// Authored owner animation only. Keep the entire skin and parent chain intact;
// omit torso/head triangles from rendering, never edit a finger or bone pose.
export function armTriangleIndices(geometry, bones, threshold = .5) {
  const joints = geometry.getAttribute('skinIndex');
  const weights = geometry.getAttribute('skinWeight');
  if (!joints || !weights) return [];
  const arm = bones.map(b => /(?:Left|Right)(?:Arm|ForeArm|Hand)/.test(b.name));
  const keep = new Uint8Array(joints.count);
  for (let v = 0; v < joints.count; v++) {
    let sum = 0;
    for (let k = 0; k < 4; k++) {
      if (arm[joints.getComponent(v, k)]) sum += weights.getComponent(v, k);
    }
    keep[v] = sum >= threshold;
  }
  const index = geometry.index;
  const count = index ? index.count : joints.count;
  const out = [];
  for (let i = 0; i < count; i += 3) {
    const a = index ? index.getX(i) : i;
    const b = index ? index.getX(i + 1) : i + 1;
    const c = index ? index.getX(i + 2) : i + 2;
    if (keep[a] && keep[b] && keep[c]) out.push(a, b, c);
  }
  return out;
}

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

export const FIRST_PERSON_CAPTURES = {
  owner: '/house/assets/first-person/owner.glb',
  typing: { url: '/house/assets/first-person/typing.glb', visualAccepted: false,
    reason: 'Original reference typing contact restored; camera and anatomy visual review required',
    position: [2.039, -.006, -2.323], yaw: Math.PI },
  walking: { url: '/house/assets/first-person/walking.glb', visualAccepted: false,
    reason: 'Reference pose walk awaiting first-person camera and anatomy review', inPlace: true },
  idle: { url: '/house/assets/first-person/walking.glb', visualAccepted: false, holdFirstFrame: true,
    reason: 'Captured base pose awaiting relaxed anatomy and camera review' },
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

export function createFirstPersonBody(T, scene, loader, onStatus = () => {}, captures = FIRST_PERSON_CAPTURES) {
  const group = new T.Group();
  group.name = 'authored-first-person-arms';
  group.visible = false;
  scene.add(group);
  const evidence = new FirstPersonActionEvidence();
  const actions = new Map();
  let mixer, activeAction, ownerRoot, hips, available = false, previous = '';
  const modes = ['typing', 'walking', 'phone', 'idle'];
  const ready = Promise.all([
    loader.loadAsync(captures.owner),
    ...modes.map(mode => loader.loadAsync(captures[mode].url)),
  ]).then(([owner, ...clips]) => {
    let triangles = 0;
    owner.scene.traverse(mesh => {
      if (!mesh.isMesh) return;
      if (!mesh.isSkinnedMesh) { mesh.visible = false; return; }
      const indices = armTriangleIndices(mesh.geometry, mesh.skeleton.bones);
      if (!indices.length) { mesh.visible = false; return; }
      const geometry = mesh.geometry.clone();
      geometry.setIndex(indices);
      geometry.clearGroups();
      mesh.geometry = geometry;
      mesh.frustumCulled = false;
      mesh.castShadow = false;
      mesh.receiveShadow = true;
      triangles += indices.length / 3;
    });
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
    group.add(ownerRoot);
    available = true;
    onStatus({ state: 'loaded-awaiting-review', armTriangles: triangles,
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
    step(dt, home, computer, now, following, camera) {
      const requested = evidence.step(home, computer, now, following);
      const mode = requested === 'typing' ? 'typing' : requested === 'walking_capture_required' ? 'walking' :
        requested === 'phone_capture_requires_retargeting' ? 'phone' : requested === 'relaxed_capture_required' ? 'idle' : null;
      group.visible = !!(available && mode && captures[mode].visualAccepted);
      if (group.visible) {
        const action = actions.get(mode);
        if (activeAction !== action) {
          activeAction?.fadeOut(.24);
          action.reset().setEffectiveWeight(1).fadeIn(.24).play();
          activeAction = action;
        }
        mixer.update(Math.min(dt, .05));
        if (captures[mode].position) {
          group.position.fromArray(captures[mode].position);
          group.rotation.y = captures[mode].yaw || 0;
        }
        if ((mode === 'walking' || mode === 'idle') && camera && hips) {
          // Camera follows the brain's actual route. Root placement compensates
          // the captured hips horizontal anchor without changing any bone pose.
          group.rotation.y = camera.rotation.y + Math.PI;
          group.position.set(0, 0, 0); group.updateMatrixWorld(true);
          const hip = hips.getWorldPosition(new T.Vector3());
          group.position.set(camera.position.x - hip.x,
            camera.position.y - 1.42, camera.position.z - hip.z);
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
