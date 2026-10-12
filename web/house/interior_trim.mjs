// Original lightweight joinery, fitted to the existing wall faces. One draw
// call; no texture downloads, new physics, or second lighting pass.
export function createInteriorTrim(T, scene) {
  const strips = [
    // Ground-floor perimeter. Leave the entrance opening clear.
    [7.8, 0, -3.895, 'x', 0],
    [7.8, 3.895, 0, 'z', 0],
    [7.8, -3.895, 0, 'z', 0],
    [5.35, -1.275, 3.895, 'x', 0],
    [1.35, 3.275, 3.895, 'x', 0],
    // Loft bedroom perimeter and bathroom wall faces outside the room.
    [3.65, -2.075, -3.895, 'x', 3],
    [7.8, -3.895, 0, 'z', 3],
    [2.95, -2.325, .435, 'x', 3],
    [.35, -.785, .675, 'z', 3],
    [.9, -.785, 2.25, 'z', 3],
  ];
  const material = new T.MeshStandardMaterial({ color: '#c5bba8', roughness: .68 });
  const geometry = new T.BoxGeometry(1, 1, 1);
  const mesh = new T.InstancedMesh(geometry, material, strips.length * 2);
  const transform = new T.Object3D();
  let index = 0;
  for (const [length, x, z, axis, floor] of strips) {
    for (const [height, thickness, center] of [[.078, .018, .045], [.012, .025, .09]]) {
      transform.position.set(x, floor + center, z);
      transform.scale.set(axis === 'x' ? length : thickness, height, axis === 'z' ? length : thickness);
      transform.updateMatrix();
      mesh.setMatrixAt(index++, transform.matrix);
    }
  }
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.name = 'Interior baseboards';
  scene.add(mesh);
  return mesh;
}
