// Runtime materials for the original loft bath fixtures built by
// tools/build_home_bath_fixtures.py. The GLBs carry geometry and metric UVs
// only; every mesh is mapped by name onto shared house materials, so no new
// bitmaps are introduced. Oak reuses the clean CC0 home_oak_veneer finish.
export const BATH_FIXTURE_MESH_ROLES = Object.freeze({
  Vanity_oak: 'oak',
  Vanity_ceramic: 'ceramic',
  Vanity_brass: 'brass',
  Toilet_ceramic: 'ceramic',
  Toilet_seat: 'seat',
  Toilet_metal: 'metal',
  BathLight_oak: 'oak',
  BathLight_diffuser: 'diffuser',
  Door_oak: 'oak',
  Door_brass: 'brass',
});

// Vitreous china: warm white base close to the house M.white tone, low
// roughness glaze with a thin clearcoat. Satin seat stays visibly softer.
export const GLAZED_CERAMIC = Object.freeze({color: '#f2eee5', roughness: .18, clearcoat: .55, clearcoatRoughness: .08});
export const SATIN_SEAT = Object.freeze({color: '#ebe6db', roughness: .42});
// Opal ceiling diffuser (tools/build_home_bath_light.py). lampEmission follows the
// bathroom room light like the other switched fixtures (userData.lampEmission).
export const BATH_LIGHT_DIFFUSER = Object.freeze({color: '#f7f2e8', emissive: '#ffe9c4', lampEmission: 1.1, roughness: .55});

export function createBathFixtureMaterials(T, {oak, brass, metal}) {
  if (!oak || !brass || !metal) throw new Error('Bath fixtures need the shared oak, brass and metal materials');
  const ceramic = new T.MeshPhysicalMaterial({
    color: new T.Color(GLAZED_CERAMIC.color), roughness: GLAZED_CERAMIC.roughness, metalness: 0,
    clearcoat: GLAZED_CERAMIC.clearcoat, clearcoatRoughness: GLAZED_CERAMIC.clearcoatRoughness,
  });
  ceramic.userData.bathFixture = 'glazed-ceramic';
  const seat = new T.MeshStandardMaterial({color: new T.Color(SATIN_SEAT.color), roughness: SATIN_SEAT.roughness, metalness: 0});
  seat.userData.bathFixture = 'satin-seat';
  const diffuser = new T.MeshStandardMaterial({
    color: new T.Color(BATH_LIGHT_DIFFUSER.color), emissive: new T.Color(BATH_LIGHT_DIFFUSER.emissive),
    emissiveIntensity: BATH_LIGHT_DIFFUSER.lampEmission, roughness: BATH_LIGHT_DIFFUSER.roughness, metalness: 0,
  });
  diffuser.userData.lampEmission = BATH_LIGHT_DIFFUSER.lampEmission;
  diffuser.userData.switchedRoom = 'bathroom';
  return {oak, ceramic, seat, brass, metal, diffuser};
}

function finiteVector(value, length) {
  return Array.isArray(value) && value.length === length && value.every(Number.isFinite);
}

// Place a loaded fixture exactly as its sidecar declares (no runtime rescale),
// assign shared materials by mesh name and reject unknown or missing parts.
export function installBathFixture(root, sidecar, materials) {
  if (!finiteVector(sidecar?.runtime_origin_m, 3) || !Number.isFinite(sidecar?.runtime_yaw_radians))
    throw new Error('Bath fixture sidecar lacks a finite runtime origin/yaw');
  root.position.set(...sidecar.runtime_origin_m);
  root.rotation.set(0, sidecar.runtime_yaw_radians, 0);
  root.scale.set(1, 1, 1);
  const seen = new Set();
  root.traverse(object => {
    if (!object.isMesh) return;
    const role = BATH_FIXTURE_MESH_ROLES[object.name];
    if (!role || !materials[role]) throw new Error('Unexpected bath fixture mesh: ' + object.name);
    object.material = materials[role];
    object.castShadow = object.receiveShadow = true;
    seen.add(object.name);
  });
  for (const name of sidecar.mesh_roles || [])
    if (!seen.has(name)) throw new Error('Bath fixture mesh missing: ' + name);
  root.updateMatrixWorld(true);
  return root;
}
