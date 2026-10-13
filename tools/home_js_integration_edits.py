"""Proposed home.js hunks, applied to a COPY by tools/build_home_js_integration_patch.py.

Each entry: (id, title, source, anchor, replacement). Anchors must occur exactly
once in the current web/house/home.js.

Design rule: several node checks execute isolated home.js blocks (canWalk,
lighting(), acceptHome) inside fixture scopes, so those blocks gain no new free
identifiers. Behaviour is routed through wrappers that keep the collider names
canWalk already uses, a hoisted hook in lighting() guarded by typeof, and the
frame loop (which picks up every new home state).
"""

EDITS = [
    ("H1", "Balcony collider comes from the visitor door wrapper (#5)", "1dbcf2c visitorDoorAllows",
     'import { balconyAllows, balconyApproach, createBalconyDoor, staticBakeScene } from "./balcony_access.mjs?v=3";\n',
     'import { balconyApproach, createBalconyDoor, staticBakeScene } from "./balcony_access.mjs?v=3";\n'),
    ("H2", "Imports for the new helpers; the leaf colliders are wrapped below (#5, #2, #6, #12, #15)",
     "1dbcf2c, 0eb0514, 55e620f, a14e876, furnishing_detail.mjs, bath_fixture_materials.mjs",
     "import { frontDoorAllows, frontDoorApproach } from './front_door_access.mjs';\n"
     "import { bathroomAllows, bathroomApproach, bathroomDoorPosition } from './bathroom_access.mjs';\n",
     "import { frontDoorApproach } from './front_door_access.mjs';\n"
     "import { bathroomApproach, bathroomDoorPosition } from './bathroom_access.mjs';\n"
     "import { actorVisible, doorState, doorTargets, fixtureLevel, roomLit, visitorDoorAllows } from './house_interactions.mjs';\n"
     "import { createHouseControlsPanel, operatorMutate } from './house_controls_panel.mjs';\n"
     "import { applyHavenSeamDetail, applyQueenBedOak } from './furnishing_detail.mjs';\n"
     "import { createBathFixtureMaterials, installBathFixture } from './bath_fixture_materials.mjs';\n"
     "import { BATH_FALLBACK_CALLS, findReplacedPrimitives, sameCalls } from './replaced_primitives.mjs';\n"),
    ("H2b", "Visitor door wrappers keep canWalk unchanged (#5)", "1dbcf2c visitorDoorAllows",
     "import { createDraftSubmit } from './draft_submit.mjs';\n",
     "import { createDraftSubmit } from './draft_submit.mjs';\n"
     "// Visitor door rules (house_interactions.mjs): a closed or locked door blocks\n"
     "// entry from the house and never traps; older servers keep the plain leaf\n"
     "// collider. canWalk calls these under the original collider names.\n"
     "function visitorDoor(name, x, z, feet, leaf) {\n"
     "  return visitorDoorAllows(name, [camera.position.x, camera.position.z], [x, z], feet,\n"
     "    doorState(homeState?.doors?.[name]), leaf);\n"
     "}\n"
     "function balconyAllows(x, z, feet, openness) { return visitorDoor('balcony', x, z, feet, openness); }\n"
     "function frontDoorAllows(x, z, feet, angle) { return visitorDoor('front', x, z, feet, angle); }\n"
     "function bathroomAllows(x, z, feet, leafCentre) { return visitorDoor('bathroom', x, z, feet, leafCentre); }\n"),
    ("H3", "Sofa seams share the linen weave relief (#6)", "furnishing_detail.mjs applyHavenSeamDetail",
     "havenSofaMaterials.Haven_seams.color.set('#58616a');\n",
     "havenSofaMaterials.Haven_seams.color.set('#58616a');\n"
     "applyHavenSeamDetail(havenSofaMaterials, lite ? 'lite' : 'full');\n"),
    ("H4", "Queen bed wood uses the shared oak maps at metric density (#6)", "furnishing_detail.mjs applyQueenBedOak",
     "    } else {\n"
     "      material.map = M.architectureOak.map;\n"
     "      material.color.set('#e7dcc9');\n"
     "      material.roughness = .82;\n"
     "    }\n",
     "    } else {\n"
     "      applyQueenBedOak(material, object.geometry, M.architectureOak, lite ? 'lite' : 'full');\n"
     "    }\n"),
    ("H5", "Bath vanity/toilet swap, bath ceiling light and oak door leaf (#15)",
     "5d985c5/579b15a generators, bath_fixture_materials.mjs, a14e876 replaced_primitives.mjs",
     "obstacle(-2.9, 2.23, 0.45, 0.72, 1);\n",
     "obstacle(-2.9, 2.23, 0.45, 0.72, 1);\n"
     "// Original bath vanity/toilet, ceiling light and oak door leaf (tools/build_home_bath_*.py).\n"
     "// The primitives above stay unbatched and are hidden only after the matching\n"
     "// GLB + sidecar loaded; any missing asset or mismatch keeps them as they are.\n"
     "const bathMaterials = createBathFixtureMaterials(T, { oak: M.architectureOak, brass: M.brass, metal: M.metal });\n"
     "const bathFallback = {};\n"
     "for (const [name, calls] of Object.entries(BATH_FALLBACK_CALLS)) {\n"
     "  try {\n"
     "    bathFallback[name] = findReplacedPrimitives(scene.children, calls);\n"
     "    for (const mesh of bathFallback[name]) mesh.userData.replaceable = true;\n"
     "  } catch (error) { console.warn('Bath ' + name + ' stays procedural:', error.message); }\n"
     "}\n"
     "let bathLight = null;\n"
     "function loadBathAsset(dir, name) {\n"
     "  return Promise.all([\n"
     "    fetch('/house/assets/' + dir + '/' + name + '.json?v=1').then(r => {\n"
     "      if (!r.ok) throw Error('sidecar ' + r.status);\n"
     "      return r.json();\n"
     "    }),\n"
     "    gltfLoader.loadAsync('/house/assets/' + dir + '/' + name + '.glb?v=1'),\n"
     "  ]);\n"
     "}\n"
     "const bathFixturesReady = Promise.all(Object.keys(BATH_FALLBACK_CALLS).map(name =>\n"
     "  loadBathAsset('bath-fixtures-original', name).then(([sidecar, gltf]) => {\n"
     "    if (!bathFallback[name] || !sameCalls(sidecar.replaces_home_js, BATH_FALLBACK_CALLS[name]))\n"
     "      throw Error('sidecar does not match the home.js fallback');\n"
     "    scene.add(installBathFixture(gltf.scene, sidecar, bathMaterials));\n"
     "    for (const mesh of bathFallback[name]) mesh.visible = false;\n"
     "    document.getElementById('status').dataset['bath' + name[0].toUpperCase() + name.slice(1)] = 'original';\n"
     "    renderer.shadowMap.needsUpdate = true;\n"
     "  }).catch(error => console.warn('Bath ' + name + ' fallback:', error.message))));\n"
     "const bathLightReady = loadBathAsset('bath-light-original', 'bath-light').then(([sidecar, gltf]) => {\n"
     "  const spec = sidecar.light;\n"
     "  if (spec?.type !== 'PointLight' || spec.room !== 'bathroom') throw Error('unexpected light spec');\n"
     "  scene.add(installBathFixture(gltf.scene, sidecar, bathMaterials));\n"
     "  bathLight = new T.PointLight(spec.color, spec.intensity, spec.distance, spec.decay);\n"
     "  bathLight.position.set(...spec.position);\n"
     "  bathLight.userData.fullIntensity = spec.intensity;\n"
     "  scene.add(bathLight);\n"
     "  switchedMaterials.add(bathMaterials.diffuser);\n"
     "  applyRoomLights();\n"
     "}).catch(error => console.warn('Bath light fallback:', error.message));\n"
     "const bathDoorReady = loadBathAsset('bath-door-original', 'bath-door').then(([sidecar, gltf]) => {\n"
     "  if (sidecar.runtime_parent !== 'bathDoor') throw Error('unexpected door parent');\n"
     "  // The slab keeps sliding and colliding; only its look is replaced.\n"
     "  bathDoor.add(installBathFixture(gltf.scene, sidecar, bathMaterials));\n"
     "  bathDoor.material = new T.MeshBasicMaterial({ visible: false });\n"
     "  renderer.shadowMap.needsUpdate = true;\n"
     "}).catch(error => console.warn('Bath door fallback:', error.message));\n"),
    ("H6", "Remove the balcony placeholder chair boxes; the real armchair and its obstacle stay (#11)",
     "tools/home_asset_audit.py 'balcony reading chair'",
     "box(0.65, 0.16, 0.68, -1.2, 3.44, 4.5, M.cream, 0.07);\n"
     "box(0.65, 0.6, 0.16, -1.2, 3.77, 4.8, M.cream, 0.07);\n"
     "for (const x of [-1.45, -0.95])\n"
     "  for (const z of [4.28, 4.7]) beam([x, 3, z], [x, 3.4, z], 0.025, M.wood);\n"
     "obstacle(-1.2, 4.55, 0.72, 0.8, 1);\n",
     "obstacle(-1.2, 4.55, 0.72, 0.8, 1);\n"),
    ("H7", "Per-room light levels on top of the master lamp (#2, #15)", "0eb0514 fixtureLevel/roomLit",
     "let lampOn = true,\n",
     "// Latest home state for per-room lights; the frame loop updates it, lighting()\n"
     "// re-applies it (lighting() first runs before homeState exists).\n"
     "let houseLightState = null, lastLightRooms = null;\n"
     "function applyRoomLights() {\n"
     "  const lit = (light) => fixtureLevel(houseLightState, light.position.toArray(), lampOn);\n"
     "  warm.intensity = 12 * lit(warm);\n"
     "  bedLight.intensity = 3.5 * lit(bedLight);\n"
     "  kitchenWorkLight.intensity = 2.4 * lit(kitchenWorkLight);\n"
     "  ceilingLights.forEach((light) => { light.intensity = 10 * lit(light); });\n"
     "  if (bathLight) bathLight.intensity = bathLight.userData.fullIntensity * lit(bathLight);\n"
     "  for (const material of switchedMaterials)\n"
     "    if (material.userData.switchedRoom)\n"
     "      material.emissiveIntensity = roomLit(houseLightState, material.userData.switchedRoom, lampOn)\n"
     "        ? material.userData.lampEmission : 0;\n"
     "}\n"
     "let lampOn = true,\n"),
    ("H8", "lighting() re-applies the room levels (#2)", "0eb0514",
     "    material.emissiveIntensity = lampOn ? material.userData.lampEmission : 0;\n"
     "  document.getElementById('status').dataset.bedsideEmission",
     "    material.emissiveIntensity = lampOn ? material.userData.lampEmission : 0;\n"
     "  // Hoisted; absent only when a source check runs this block in isolation.\n"
     "  if (typeof applyRoomLights === 'function') applyRoomLights();\n"
     "  document.getElementById('status').dataset.bedsideEmission"),
    ("H9", "Operator door toggles on the door leaves (#5)", "1dbcf2c / a81430f door states",
     "interactions.push(\n"
     "  { object: deskLamp, label: \"E · Switch lamp\", fn: toggleLamp },\n"
     "  { object: bedsideLamp, label: \"E · Switch lamp\", fn: toggleLamp },\n"
     ");\n",
     "interactions.push(\n"
     "  { object: deskLamp, label: \"E · Switch lamp\", fn: toggleLamp },\n"
     "  { object: bedsideLamp, label: \"E · Switch lamp\", fn: toggleLamp },\n"
     ");\n"
     "// Doors open/close on the server (operator); \"auto\" returns them to the character's rules.\n"
     "async function toggleDoor(name) {\n"
     "  const open = homeState?.doors?.[name]?.state === 'open';\n"
     "  await mutate('settings', { doors: { [name]: open ? 'auto' : 'open' } });\n"
     "}\n"
     "interactions.push(\n"
     "  { object: frontDoorGroup, label: \"E · Open / close the front door\", fn: () => toggleDoor('front') },\n"
     "  { object: bathDoor, label: \"E · Open / close the bathroom door\", fn: () => toggleDoor('bathroom') },\n"
     "  { object: balconyDoor.leaf, label: \"E · Open / close the balcony door\", fn: () => toggleDoor('balcony') },\n"
     ");\n"),
    ("H10", "Mount the operator house controls panel in the footer (#12)", "55e620f house_controls_panel.mjs",
     "document.getElementById(\"curtain\").onclick = toggleCurtain;\n",
     "document.getElementById(\"curtain\").onclick = toggleCurtain;\n"
     "const houseControlsBox = document.createElement('details');\n"
     "houseControlsBox.id = 'house-controls';\n"
     "houseControlsBox.append(Object.assign(document.createElement('summary'), { textContent: 'House' }));\n"
     "document.querySelector('footer').append(houseControlsBox);\n"
     "const houseControls = createHouseControlsPanel(houseControlsBox,\n"
     "  { mutate: operatorMutate(fetch, operatorToken), operatorKey: operatorToken });\n"
     "houseControlsBox.addEventListener('toggle', () => houseControls.refreshOperator());\n"),
    ("H11", "Door leaves follow the server door state; new home states feed lights and panel (#5, #2, #12)",
     "1dbcf2c doorTargets, 0eb0514, 55e620f",
     "  const balconyMoving = balconyDoor.update(dt,\n"
     "    balconyApproach([p.x,p.y,p.z]) || balconyApproach(homeState?.position));\n",
     "  if (homeState !== houseLightState) {   // a new home message\n"
     "    houseLightState = homeState;\n"
     "    houseControls.update(homeState);\n"
     "    const rooms = JSON.stringify(homeState?.lights?.rooms ?? null);\n"
     "    if (rooms !== lastLightRooms) {\n"
     "      lastLightRooms = rooms;\n"
     "      applyRoomLights();\n"
     "      if (!lite) renderer.shadowMap.needsUpdate = true;\n"
     "    }\n"
     "  }\n"
     "  // Server doors (opened from the inside for the visitor); older servers: proximity.\n"
     "  const doorWant = doorTargets(homeState, following ? null : [p.x, p.y, p.z], {\n"
     "    front: frontDoorApproach([p.x,p.y,p.z]) || frontDoorApproach(homeState?.position),\n"
     "    bathroom: bathroomApproach([p.x, p.y, p.z]) || bathroomApproach(homeState?.position),\n"
     "    balcony: balconyApproach([p.x,p.y,p.z]) || balconyApproach(homeState?.position),\n"
     "  });\n"
     "  const balconyMoving = balconyDoor.update(dt, doorWant.balcony);\n"),
    ("H12", "Front door target from the server state (#5)", "1dbcf2c doorTargets",
     "  entranceOpen = frontDoorApproach([p.x,p.y,p.z]) || frontDoorApproach(homeState?.position);\n",
     "  entranceOpen = doorWant.front;\n"),
    ("H13", "Bathroom door target from the server state (#5)", "1dbcf2c doorTargets",
     "  const doorOpen = bathroomApproach([p.x, p.y, p.z]) || bathroomApproach(homeState?.position);\n",
     "  const doorOpen = doorWant.bathroom;\n"),
    ("H14", "Wait for the bath assets before startup cleanup and baking (#15)", "asset barrier registry",
     "  sofaReady, coffeeTableReady, kitchenCabinetReady, officeDeskReady, officeShelvesReady, officeChairReady]) {\n",
     "  sofaReady, coffeeTableReady, kitchenCabinetReady, officeDeskReady, officeShelvesReady, officeChairReady,\n"
     "  bathFixturesReady, bathLightReady, bathDoorReady]) {\n"),
    ("H15", "Hide the actor's body while he is away; follow camera unchanged (owner decision 2026-10-13)",
     "owner decision 2026-10-13; 41fa350 actorVisible",
     "  firstPersonBody.step(dt, homeState, computerState, performance.now() / 1000, following && !privacyActive, camera);\n",
     "  // Away (presence \"away\"): no body; the camera still follows homeState.position\n"
     "  // and the body returns on the first frame he is back (step() sets visibility).\n"
     "  firstPersonBody.step(dt, homeState, computerState, performance.now() / 1000,\n"
     "    following && !privacyActive && actorVisible(homeState), camera);\n"),
]
