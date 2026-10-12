import { createWindowView } from '../room/window_view.js?v=home1';

// The legacy room used one window-centred diorama. This two-floor house needs
// one coordinate system per facade, shared by every pane on that facade.
export const FACADE_ORIGINS = Object.freeze({
  west: Object.freeze([-3.94, 1.675, 0]),
  front: Object.freeze([0, 1.675, 3.94]),
});

export function facadeCoordinates(point, facade) {
  const origin = FACADE_ORIGINS[facade];
  if (!origin) throw new Error('Unknown house facade');
  return [facade === 'west' ? -(point[2] - origin[2]) : -(point[0] - origin[0]),
          point[1] - origin[1]];
}

export function photographicIntersection(camera, panePoint, facade, depth) {
  const glass = facadeCoordinates(panePoint, facade);
  const eye = facadeCoordinates(camera, facade);
  const outwardDistance = facade === 'west' ? camera[0] - panePoint[0] : panePoint[2] - camera[2];
  return glass.map((coordinate, i) => coordinate + (coordinate - eye[i]) * depth / outwardDistance);
}

function replaceRequired(source, from, to) {
  if (!source.includes(from)) throw new Error('Window shader contract changed');
  return source.replace(from, to);
}

export function createHouseWindowView(THREE, options, facade) {
  const origin = FACADE_ORIGINS[facade];
  if (!origin) throw new Error('Unknown house facade');
  const view = createWindowView(THREE, options);
  const material = view.material;
  material.uniforms.uFacadeOrigin = {value: new THREE.Vector3(...origin)};
  // No overview-camera horizon lift, zoom or grazing-angle compression.
  // Camera height and lateral movement now describe real metres in the house.
  material.uniforms.uGain.value.set(1, 1);
  material.uniforms.uLift.value.set(0, 0, 0);
  let shader = material.fragmentShader;
  shader = replaceRequired(shader, 'uniform vec2 uSize;', 'uniform vec3 uFacadeOrigin; uniform vec2 uSize;');
  shader = replaceRequired(shader,
    'vec2 g = (vUv - 0.5) * uSize;',
    'vec3 facadeDelta = vWorld - uFacadeOrigin; vec2 g = vec2(dot(facadeDelta, vRight), dot(facadeDelta, vUp));');
  shader = replaceRequired(shader,
    'slope = slope / (1.0 + abs(slope) / vec2(0.55, 0.9));',
    '// Physical ray slope is shared across every pane; do not zoom each window.');
  shader = replaceRequired(shader,
    'if (uv.y <= 0.0 || uv.y >= 1.0) return vec4(0.0);',
    'if (uv.x <= 0.0 || uv.x >= 1.0 || uv.y <= 0.0 || uv.y >= 1.0) return vec4(0.0);');
  material.fragmentShader = shader;
  return view;
}
