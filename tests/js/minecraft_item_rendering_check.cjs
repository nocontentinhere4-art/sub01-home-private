const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const deps = '../../games/minecraft/node_modules/';
const registry = require(deps+'prismarine-registry')('1.20.1');
const Item = require(deps+'prismarine-item')(registry);
const THREE = require(deps+'three');
const {logItem,entityPacket,installItemRendering} = require('../../games/minecraft/item_rendering.cjs');
const {terrainReady} = require('../../games/minecraft/viewer_readiness.cjs');
const publicPath=path.join(path.dirname(require.resolve(deps+'prismarine-viewer')),'public');
const exists = name=>fs.existsSync(path.join(publicPath,name));
function entity(name,id) {
  const metadata=[];
  metadata[registry.entitiesByName.item.metadataKeys.indexOf('item')]=Item.toNotch(new Item(registry.itemsByName[name].id,1));
  return {name:'item',id,metadata,position:{x:1,y:65,z:2},width:.25,height:.25};
}
const log=entity('oak_log',921); // Test ID is not a production entity identity.
const packet={id:log.id,name:'item',pos:log.position,width:log.width,height:log.height};
const bot={entities:{[log.id]:log},registry,version:'1.20.1'};
const enriched=entityPacket(packet,bot,Item,exists);
assert.equal(enriched.id,packet.id);assert.equal(enriched.pos,packet.pos);
assert.equal(enriched.sub01ItemMetadataReady,true);
assert.equal(entityPacket(packet,{...bot,entities:{921:{...log,metadata:[]}}},Item,exists).sub01ItemMetadataReady,false);
assert.equal(enriched.sub01Item.type,registry.itemsByName.oak_log.id);
assert.equal(enriched.sub01Item.name,'oak_log');assert.equal(enriched.sub01Item.count,1);
assert(exists(enriched.sub01Item.side)&&exists(enriched.sub01Item.top));
assert.equal(logItem(entity('stick',922),registry,Item,'1.20.1',exists),null);
assert.equal(logItem(log,registry,Item,'1.20.1',()=>false),null);
assert.equal(entityPacket({id:log.id,delete:true},bot,Item,exists).delete,true);
const geometry=new THREE.BoxGeometry(.25,.25,.25);geometry.translate(0,.125,0);
const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:0xff00ff}));
mesh.position.set(1,65,2);
const pending=[];
class Loader {load(url,onload,_progress,onerror){pending.push({url,onload,onerror});}}
globalThis.THREE={...THREE,TextureLoader:Loader};
let originalCalls=0;
const viewer={entities:{entities:{921:mesh}},updateEntity(){originalCalls++;}};
installItemRendering(viewer);viewer.updateEntity(enriched);
assert.equal(globalThis.sub01ItemTexturesOutstanding,2);
globalThis.sub01MinecraftViewer={world:{
  loadedChunks:{a:true},sectionsOutstanding:new Set(),material:{map:{image:{width:16}}},
  sectionMeshs:{a:{geometry:{attributes:{position:{count:6}}}}}
}};
assert.equal(terrainReady(),false); // Terrain cannot beat item texture decode.
for(const load of pending)load.onload(new THREE.Texture({width:16,height:16}));
assert.equal(terrainReady(),true);
viewer.updateEntity({...enriched,sub01ItemMetadataReady:false});
assert.equal(terrainReady(),false);
viewer.updateEntity(enriched);assert.equal(terrainReady(),true);
assert.equal(mesh.geometry,geometry);
assert.deepEqual(mesh.position.toArray(),[1,65,2]);assert.equal(originalCalls,3);
assert.equal(globalThis.sub01ItemRenderReceipts[921].status,'textured_registry_log');
assert.equal(mesh.material.length,6);assert.equal(mesh.material[0],mesh.material[1]);assert.equal(mesh.material[2],mesh.material[3]);
assert.notEqual(mesh.material[0].map,mesh.material[2].map);
assert.equal(mesh.material[0].map.magFilter,THREE.NearestFilter);
viewer.updateEntity({...enriched,sub01Item:null});
assert.equal(mesh.material.color.getHex(),0xff00ff);
assert.equal(globalThis.sub01ItemRenderReceipts[921].status,'unsupported_visible_fallback');
assert.equal(mesh.geometry,geometry);assert.deepEqual(mesh.position.toArray(),[1,65,2]);
// Failed real texture fetch keeps the visible fallback and releases readiness.
viewer.updateEntity(enriched);pending.slice(2).forEach(load=>load.onerror());
assert.equal(mesh.material.color.getHex(),0xff00ff);
assert.equal(globalThis.sub01ItemTexturesOutstanding,0);
assert.equal(globalThis.sub01ItemRenderReceipts[921].status,'texture_error_visible_fallback');
console.log('Registry item packet identity, real log assets, texture-ready geometry and unsupported visible fallback passed');
