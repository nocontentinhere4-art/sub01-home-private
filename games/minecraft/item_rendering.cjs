// Decode genuine item metadata with the existing registry; unsupported items stay visible.
function logItem(entity, registry, Item, version, textureExists) {
  if (!entity || entity.name !== 'item' || !/^\d+\.\d+(?:\.\d+)?$/.test(version)) return null;
  const keys = registry.entitiesByName.item?.metadataKeys || [];
  const index = keys.indexOf('item');
  if (index < 0 || !entity.metadata || entity.metadata[index] == null) return null;
  let item;
  try { item = Item.fromNotch(entity.metadata[index]); } catch { return null; }
  if (!item || !Number.isInteger(item.type) || !Number.isInteger(item.count) || item.count < 1 ||
      !registry.items[item.type] || registry.items[item.type].name !== item.name ||
      !/^[a-z0-9_]+_log$/.test(item.name) || !registry.blocksByName[item.name]) return null;
  const side = `textures/${version}/blocks/${item.name}.png`;
  const top = `textures/${version}/blocks/${item.name}_top.png`;
  if (!textureExists(side) || !textureExists(top)) return null;
  return { model: 'log_block', type: item.type, name: item.name, count: item.count, side, top };
}

function entityPacket(packet, bot, Item, textureExists) {
  if (packet.delete) return packet;
  const entity = bot.entities[packet.id];
  if (entity?.name !== 'item') return packet;
  const index = bot.registry.entitiesByName.item?.metadataKeys?.indexOf('item') ?? -1;
  return { ...packet, sub01ItemMetadataReady: index >= 0 && entity.metadata?.[index] != null,
    sub01Item: logItem(entity, bot.registry, Item, bot.version, textureExists) };
}

// Runs inside the existing viewer bundle; keeps the actual scene mesh/id/position.
function installItemRendering(viewer) {
  const THREE = globalThis.THREE;
  const original = viewer.updateEntity.bind(viewer);
  globalThis.sub01ItemTexturesOutstanding = 0;
  globalThis.sub01ItemRenderReceipts = {};
  globalThis.sub01PendingItemMetadata = new Set();
  viewer.updateEntity = function(packet) {
    original(packet);
    if (packet.delete) { delete globalThis.sub01ItemRenderReceipts[packet.id]; globalThis.sub01PendingItemMetadata.delete(packet.id); return; }
    if (!Object.prototype.hasOwnProperty.call(packet, 'sub01Item')) return;
    const mesh = viewer.entities.entities[packet.id];
    if (!mesh) return;
    if (packet.sub01ItemMetadataReady === false) {
      globalThis.sub01PendingItemMetadata.add(packet.id);
      globalThis.sub01ItemRenderReceipts[packet.id]={id:packet.id,status:'awaiting_actual_item_metadata'};
      return;
    }
    globalThis.sub01PendingItemMetadata.delete(packet.id);
    const item = packet.sub01Item;
    const dispose = material => {
      for (const m of new Set(Array.isArray(material) ? material : [material])) {
        m.map?.dispose(); m.dispose();
      }
    };
    if (!item || item.model !== 'log_block' || !/^[a-z0-9_]+_log$/.test(item.name) ||
        !/^textures\/\d+\.\d+(?:\.\d+)?\/blocks\/[a-z0-9_]+_log\.png$/.test(item.side) ||
        item.top !== item.side.replace(/\.png$/, '_top.png')) {
      if (mesh.userData.sub01ItemKey) {
        dispose(mesh.material); mesh.material = new THREE.MeshBasicMaterial({color:0xff00ff});
        mesh.userData.sub01ItemKey = null;
      }
      globalThis.sub01ItemRenderReceipts[packet.id] = {id:packet.id,status:'unsupported_visible_fallback'};
      return;
    }
    const key = item.type + ':' + item.side;
    if (mesh.userData.sub01ItemKey === key) {
      const receipt = mesh.userData.sub01ItemReceipt;
      if (receipt) { receipt.count = item.count; globalThis.sub01ItemRenderReceipts[packet.id]=receipt; }
      return;
    }
    mesh.userData.sub01ItemKey = key;
    const receipt = {id:packet.id,type:item.type,name:item.name,count:item.count,status:'loading_real_textures'};
    globalThis.sub01ItemRenderReceipts[packet.id] = receipt;
    mesh.userData.sub01ItemReceipt = receipt;
    globalThis.sub01ItemTexturesOutstanding += 2;
    const textures = [], loader = new THREE.TextureLoader();
    let settled = 0, failed = false;
    function done(index, texture) {
      textures[index] = texture; settled++; globalThis.sub01ItemTexturesOutstanding--;
      if (settled !== 2) return;
      if (failed || viewer.entities.entities[packet.id] !== mesh || mesh.userData.sub01ItemKey !== key) {
        for (const t of textures) t?.dispose();
        if (globalThis.sub01ItemRenderReceipts[packet.id] === receipt) receipt.status = failed ? 'texture_error_visible_fallback' : 'superseded';
        return;
      }
      for (const texture of textures) { texture.magFilter=THREE.NearestFilter; texture.minFilter=THREE.NearestFilter; }
      const side = new THREE.MeshLambertMaterial({map:textures[0]});
      const top = new THREE.MeshLambertMaterial({map:textures[1]});
      dispose(mesh.material);
      mesh.material = [side,side,top,top,side,side];
      receipt.status = 'textured_registry_log';
    }
    [item.side,item.top].forEach((url,index) => loader.load(url,
      texture => done(index,texture), undefined,
      () => { failed=true; done(index,null); }));
  };
}
module.exports = { logItem, entityPacket, installItemRendering };
