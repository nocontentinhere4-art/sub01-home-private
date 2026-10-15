// Explicit source revision contract; no automatic fallback to an unpinned rest.
import assert from 'node:assert/strict';
export const ORIGINAL_PORTABLE_REST_SHA='209df19300ab56d7b08667e930bb06deef818edb1cf04dbff71aec9a08c64152';
export function verifyRestRevision(actualSha, expectedSha=null, packet=null){
 const pinned=expectedSha||ORIGINAL_PORTABLE_REST_SHA;
 assert(/^[a-f0-9]{64}$/.test(pinned),'A full expected source SHA is required');
 assert.equal(actualSha,pinned,'Expected rest SHA must match actual serialized source');
 if(expectedSha){
  assert(packet,'Explicit rest revisions require their verified source packet');
  assert.equal(packet.schema,'sub01.portable-cuff-photo-tinted-sheen.v1');
  assert.equal(packet.afterSha256,pinned,'Revision packet identifies a different source');
  assert.equal(packet.binaryGeometryExact,true,'Revision packet does not preserve geometry');
 }
 return pinned;
}
