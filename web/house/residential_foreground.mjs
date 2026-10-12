// Original lightweight Japanese residential frontage, local private house only.
// Geometry stays outside z=6.15; no physics or actor route is changed here.
export function createResidentialForeground(T, scene, { gateOpen = true } = {}) {
  const group = new T.Group();
  group.name = 'SUB-01 residential gate and mailbox';
  group.userData.excludeStaticBake = true;
  const alloy = new T.MeshStandardMaterial({ color: '#65706b', metalness: .55, roughness: .58 });
  const postFinish = new T.MeshStandardMaterial({ color: '#d5d0c2', roughness: .89 });
  const dark = new T.MeshStandardMaterial({ color: '#252c29', metalness: .3, roughness: .62 });
  const steel = new T.MeshStandardMaterial({ color: '#9ba39d', metalness: .8, roughness: .40 });
  const cube = new T.BoxGeometry(1, 1, 1);
  const resources = { materials: [alloy, postFinish, dark, steel], geometries: [cube], textures: [] };
  const makeInstances = (name, rows, material, parent = group) => {
    const mesh = new T.InstancedMesh(cube, material, rows.length);
    const transform = new T.Object3D();
    for (let i = 0; i < rows.length; i++) {
      const [x, y, z, width, height, depth] = rows[i];
      transform.position.set(x, y, z); transform.scale.set(width, height, depth);
      transform.updateMatrix(); mesh.setMatrixAt(i, transform.matrix);
    }
    mesh.name = name;
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.userData.excludeStaticBake = true;
    parent.add(mesh);
    return mesh;
  };

  // Pillars leave the full x=1.4..2.6 passage physically clear.
  makeInstances('Cream gate pillars', [
    [1.28, .56, 6.25, .20, 1.12, .20], [2.72, .56, 6.25, .20, 1.12, .20],
  ], postFinish);
  makeInstances('Metal pillar caps', [
    [1.28, 1.132, 6.25, .212, .024, .212], [2.72, 1.132, 6.25, .212, .024, .212],
  ], alloy);
  const fence = [];
  for (const [left, right] of [[-3.6, 1.18], [2.82, 3.8]]) {
    const width = right - left, x = (left + right) / 2;
    fence.push([x, .25, 6.25, width, .032, .035], [x, .99, 6.25, width, .035, .035]);
    const count = Math.ceil(width / .12);
    for (let i = 0; i <= count; i++)
      fence.push([left + width * i / count, .62, 6.25, .019, .75, .026]);
  }
  makeInstances('Restrained vertical residential fence', fence, alloy);

  const gate = new T.Group();
  gate.name = 'Openable entrance gate';
  gate.position.set(1.40, 0, 6.25);
  gate.userData.excludeStaticBake = true;
  group.add(gate);
  const leaf = [
    [.566, .24, 0, 1.13, .035, .034], [.566, 1.015, 0, 1.13, .035, .034],
    [.017, .628, 0, .034, .79, .034], [1.115, .628, 0, .034, .79, .034],
  ];
  for (let i = 1; i < 10; i++) leaf.push([.035 + i * .108, .628, 0, .018, .75, .026]);
  const leafMesh = makeInstances('Gate leaf', leaf, alloy, gate);
  makeInstances('Gate latch and hinge', [
    [1.092, .84, .029, .018, .102, .03], [.018, .35, -.028, .026, .08, .028],
    [.018, .91, -.028, .026, .08, .028],
  ], dark, gate);

  // Slim standing mailbox to the left of the path; closed slot and lid have depth.
  const mailbox = new T.Group(); mailbox.name = 'SUB-01 mailbox'; group.add(mailbox);
  makeInstances('Mailbox stem', [[.8, .47, 6.2, .045, .94, .045]], alloy, mailbox);
  makeInstances('Mailbox housing', [[.8, 1.055, 6.2, .32, .22, .135]], dark, mailbox);
  makeInstances('Mailbox lid and letter-slot rim', [
    [.8, 1.173, 6.205, .335, .018, .147], [.8, 1.112, 6.271, .258, .014, .012],
    [.8, 1.087, 6.271, .258, .009, .012], [.654, 1.10, 6.271, .011, .042, .012],
    [.946, 1.10, 6.271, .011, .042, .012],
  ], alloy, mailbox);
  // The plate faces the street (+Z), and all visible text is English.
  if (typeof document !== 'undefined') {
    const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 64;
    const context = canvas.getContext('2d');
    context.fillStyle = '#a7aca3'; context.fillRect(0, 0, 256, 64);
    context.fillStyle = '#18201b'; context.textAlign = 'center'; context.textBaseline = 'middle';
    context.font = 'bold 38px sans-serif'; context.fillText('SUB-01', 128, 33);
    const texture = new T.CanvasTexture(canvas); texture.colorSpace = T.SRGBColorSpace;
    const material = new T.MeshStandardMaterial({ map: texture, roughness: .68, metalness: .15 });
    const geometry = new T.PlaneGeometry(.245, .061);
    const plate = new T.Mesh(geometry, material);
    plate.name = 'English SUB-01 address plate'; plate.position.set(.8, 1.025, 6.269);
    plate.userData.excludeStaticBake = true; mailbox.add(plate);
    resources.textures.push(texture); resources.materials.push(material); resources.geometries.push(geometry);
  }
  // Small pavement footings ground the module without adding an image or scene.
  makeInstances('Gate and mailbox footing plates', [
    [1.28, .016, 6.25, .24, .032, .24], [2.72, .016, 6.25, .24, .032, .24],
    [.8, .008, 6.2, .16, .016, .13],
  ], steel);

  let open = Boolean(gateOpen), target = open ? -Math.PI * .53 : 0;
  gate.rotation.y = target;
  scene.add(group);
  return {
    group, gate, gateLeaf: leafMesh, mailbox,
    get isGateOpen() { return open; },
    setGateOpen(value) { open = Boolean(value); target = open ? -Math.PI * .53 : 0; },
    update(dt) {
      const step = Number.isFinite(dt) ? Math.max(0, Math.min(.1, dt)) : 0;
      gate.rotation.y += (target - gate.rotation.y) * (1 - Math.exp(-7 * step));
      if (Math.abs(target - gate.rotation.y) < .0001) gate.rotation.y = target;
    },
    dispose() {
      scene.remove(group);
      group.traverse(object => { if (object.isInstancedMesh) object.dispose(); });
      for (const texture of resources.textures) texture.dispose();
      for (const material of resources.materials) material.dispose();
      for (const geometry of resources.geometries) geometry.dispose();
    },
  };
}
