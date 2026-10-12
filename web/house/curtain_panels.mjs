// Original sewn cloth geometry, informed by MUJI linen pleated curtains and
// IKEA DYTÅG heading-tape linen. Shared material maps, no new image download.
// Reference: https://www.muji.com/jp/ja/store/search/cmdty/リネンカーテン
// https://www.ikea.com/gb/en/p/dytag-curtains-1-pair-beige-with-heading-tape-60607802/

function foldShape(u, v, folds) {
  const wave = Math.PI * 2 * folds * u;
  const lower = 1 - v;
  // Heading tape keeps regular folds; tiny lower ripples soften rigid columns.
  return Math.sin(wave + .065 * Math.sin(u * 17) * lower) *
    (1 + .08 * lower + .035 * Math.sin(u * 13) * lower) +
    .025 * Math.sin(wave * 2 + v * 4) * lower;
}

export function createCurtainPanel(T, material, {
  width = 1.8, height = 2.48, folds = 16, direction = 1, open = false,
  packedRatio = .17, amplitude = .034, segmentsY = 20,
} = {}) {
  if (!(width > 0 && height > 0 && folds >= 4 && amplitude > 0) ||
      ![width, height, folds, amplitude, packedRatio].every(Number.isFinite))
    throw new Error('Invalid curtain dimensions');
  direction = direction < 0 ? -1 : 1;
  folds = Math.round(Math.min(32, folds));
  packedRatio = Math.max(.12, Math.min(.5, packedRatio));
  const nx = folds * 8, ny = Math.max(8, Math.min(32, Math.round(segmentsY)));
  const count = (nx + 1) * (ny + 1), positions = new Float32Array(count * 3);
  const uv = new Float32Array(count * 2), indices = [];
  // Actual rest-cloth length measured along the corrugated surface, in meters.
  const arc = new Float64Array(nx + 1);
  for (let i = 1; i <= nx; i++) {
    const dz = amplitude * (foldShape(i / nx, .5, folds) - foldShape((i - 1) / nx, .5, folds));
    arc[i] = arc[i - 1] + Math.hypot(width / nx, dz);
  }
  const clothLength = arc[nx];
  const sampledLength = (currentWidth, a) => {
    let length = 0;
    for (let i = 1; i <= nx; i++) {
      const dz = a * (foldShape(i / nx, .5, folds) - foldShape((i - 1) / nx, .5, folds));
      length += Math.hypot(currentWidth / nx, dz);
    }
    return length;
  };
  for (let j = 0; j <= ny; j++) {
    for (let i = 0; i <= nx; i++) {
      const id = j * (nx + 1) + i;
      uv[id * 2] = arc[i]; uv[id * 2 + 1] = height * j / ny;
      if (i < nx && j < ny) {
        const next = id + nx + 1;
        indices.push(id, id + 1, next, id + 1, next + 1, next);
      }
    }
  }
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new T.BufferAttribute(uv, 2));
  geometry.setIndex(indices);
  const clothMaterial = material.clone();
  clothMaterial.side = T.DoubleSide;
  // Moving textile receives live light; it must not retain a stale GI/UV2 clone.
  clothMaterial.lightMap = clothMaterial.aoMap = null;
  const mesh = new T.Mesh(geometry, clothMaterial);
  mesh.name = 'Continuous linen curtain';
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.userData.excludeStaticBake = true;
  const group = new T.Group(); group.name = 'Sewn pleated curtain panel';
  group.userData.excludeStaticBake = true; group.add(mesh);
  let target = open ? 1 : 0, amount = target, lastAmount = NaN;

  const deform = () => {
    if (Math.abs(amount - lastAmount) < .000001) return false;
    lastAmount = amount;
    const currentWidth = width * (1 - amount * (1 - packedRatio));
    // Gathering increases pleat depth enough to conserve the actual cloth length.
    let lo = amplitude, hi = amplitude * 2;
    for (let k = 0; k < 14; k++) {
      const mid = (lo + hi) / 2;
      if (sampledLength(currentWidth, mid) < clothLength) lo = mid; else hi = mid;
    }
    const a = (lo + hi) / 2;
    for (let j = 0; j <= ny; j++) {
      const v = j / ny;
      for (let i = 0; i <= nx; i++) {
        const u = i / nx, id = (j * (nx + 1) + i) * 3;
        // Folded bottom hem, side returns and heading band are part of one surface.
        const hem = Math.exp(-Math.pow((v - .017) / .014, 2)) * .002;
        const heading = Math.exp(-Math.pow((v - .975) / .018, 2)) * .0018;
        const sideHem = Math.exp(-Math.pow(u / .006, 2)) * .002 +
          Math.exp(-Math.pow((u - 1) / .006, 2)) * .002;
        const bottomSag = -.009 * Math.sin(Math.PI * u) * (1 - v) ** 7;
        positions[id] = direction * currentWidth * u;
        positions[id + 1] = height * (v - .5) + bottomSag;
        positions[id + 2] = a * foldShape(u, v, folds) + hem + heading + sideHem;
      }
    }
    geometry.attributes.position.needsUpdate = true;
    geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
    return true;
  };
  deform();
  return {
    group, mesh, clothLength,
    setOpen(value, { immediate = false } = {}) {
      target = value ? 1 : 0;
      if (immediate) { amount = target; deform(); }
    },
    update(dt) {
      if (!Number.isFinite(dt) || dt <= 0 || Math.abs(amount - target) < .00001) return false;
      amount += (target - amount) * (1 - Math.exp(-6 * Math.min(.1, dt)));
      if (Math.abs(amount - target) < .00001) amount = target;
      return deform();
    },
    state() { return { open: target > .5, amount, width: width * (1 - amount * (1 - packedRatio)), clothLength }; },
    dispose() { group.remove(mesh); geometry.dispose(); clothMaterial.dispose(); },
  };
}
