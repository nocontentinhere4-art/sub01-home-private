// A device is usable only when it is within reach and visible along the gaze ray.
export function reachableInteraction(ray, interactions, scene, reach = 2) {
  const previousFar = ray.far;
  const owner = (object) => {
    for (let current = object; current; current = current.parent) {
      const interaction = interactions.find((item) => item.object === current);
      if (interaction) return interaction;
    }
    return null;
  };
  const visible = (object) => {
    for (let current = object; current; current = current.parent)
      if (!current.visible) return false;
    return true;
  };
  try {
    ray.far = Math.max(reach, ...interactions.map((item) => item.reach ?? reach));
    const hit = ray.intersectObjects(
      interactions.map((item) => item.object).filter(visible), true,
    ).find((candidate) => visible(candidate.object) &&
      candidate.distance <= (owner(candidate.object)?.reach ?? reach));
    if (!hit) return null;
    const interaction = owner(hit.object);
    ray.far = Math.max(0, hit.distance - 0.002);
    const surfaces = [];
    scene.traverseVisible((object) => {
      if (object.isMesh) surfaces.push(object);
    });
    const blocked = ray.intersectObjects(surfaces, false).some((cover) => {
      if (owner(cover.object) === interaction) return false;
      const material = Array.isArray(cover.object.material)
        ? cover.object.material[cover.face?.materialIndex || 0]
        : cover.object.material;
      // Glass and transparent contact-shadow decals do not hide the device.
      return material?.visible !== false && !material?.transparent;
    });
    return blocked ? null : interaction;
  } finally {
    ray.far = previousFar;
  }
}
