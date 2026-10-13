import * as T from '../../web/house/vendor/three.module.js';
import {createLowerKitchenCabinet} from '../../web/house/lower_kitchen_cabinet.mjs';
import {RoundedBoxGeometry} from '../../web/house/vendor/RoundedBoxGeometry.js';
import {mergeGeometries} from '../../web/house/vendor/BufferGeometryUtils.js';
export function lowerCabinetFixture() {
  return createLowerKitchenCabinet(T,{RoundedBoxGeometry,mergeGeometries,oak:new T.MeshStandardMaterial(),brass:new T.MeshStandardMaterial()});
}
