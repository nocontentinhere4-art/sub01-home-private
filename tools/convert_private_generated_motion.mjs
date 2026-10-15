// Use the external CozyClay SOMA converter without vendoring its AGPL source.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const args=process.argv.slice(2);
assert.equal(args.length,4,'Usage: COZY_PACKAGE SOURCE_SOMA.npz OUT_CSKEL.npz VERIFIED_FPS');
const [cozy,source,out]=args.slice(0,3).map(p=>path.resolve(p)),fps=Number(args[3]);
assert(Number.isInteger(fps)&&fps>=1&&fps<=120,'Explicit verified generation FPS required');
const from=p=>import(pathToFileURL(path.join(cozy,p)).href);
const {readKimodoMotion}=await from('tools/kimodo/read-npz.mjs');
const {soma77ToCskel27Motion}=await from('tools/kimodo/soma77-to-cskel27.mjs');
const {writeNpz,motionArraysToNpzMembers}=await from('tools/ardy/npz.mjs');
const input=readKimodoMotion(source);assert(input.fps===null||input.fps===fps,'Generation FPS conflicts');
const motion=soma77ToCskel27Motion({...input,fps});
assert(motion.frames===input.frames&&motion.fps===fps);
writeNpz(out,motionArraysToNpzMembers(motion));
const {decodeMotionNpz}=await from('src/ardy/npz.js');
const checked=await decodeMotionNpz(fs.readFileSync(out));assert(checked.frames===input.frames&&checked.fps===fps);
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const report={schema:'sub01.generated-motion-cozy-interchange.v1',sourceSha256:hash(source),outputSha256:hash(out),frames:checked.frames,fps,
 sourceJoints:77,targetJoints:27,externalConverter:'CozyClay tools/kimodo/soma77-to-cskel27.mjs',
 nativeImported:false,handMotionGenerated:false,contactAccepted:false,
 limitations:['Body-only converter leaves finger articulation to a separate recorded/contact layer','World travel must be owned by physical navigation, not applied unchecked from generated roots']};
fs.writeFileSync(out+'.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
