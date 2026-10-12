import assert from 'node:assert/strict';
import fs from 'node:fs';
import {HDRLoader} from '../../web/house/vendor/HDRLoader.js';
import {FloatType} from 'three';
// Generated with Blender Raw HDR from linear image.pixels: bottom left red,
// bottom right green, top left blue, top right yellow. Not a symmetric atlas.
const bytes=fs.readFileSync('tests/fixtures/indirect-corners.hdr');
assert.ok(bytes.equals(fs.readFileSync('web/house/assets/lighting-audit/corners.hdr')),'visible GPU audit must use the same actual Blender fixture');
const parsed=new HDRLoader().setDataType(FloatType).parse(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
assert.equal(parsed.width,16);assert.equal(parsed.height,16);
const sample=(u,v,flip)=>{const x=Math.floor(u*16),y=Math.floor((flip?1-v:v)*16);return Array.from(parsed.data.slice((y*16+x)*4,(y*16+x)*4+3));};
const close=(actual,expected)=>actual.every((v,i)=>Math.abs(v-expected[i])<.005);
assert.ok(close(sample(.25,.25,false),[0,0,1]),'glTF top-left UV must see Blender top-left blue');
assert.ok(close(sample(.75,.25,false),[1,1,0]));
assert.ok(close(sample(.25,.75,false),[1,0,0]));
assert.ok(close(sample(.75,.75,false),[0,1,0]));
assert.ok(!close(sample(.25,.25,true),[0,0,1]),'HDR environment default flips wrong charts for glTF light maps');
const home=fs.readFileSync('web/house/home.js','utf8');
assert.ok(/ao\.flipY\s*=\s*false/.test(home),'day/AO glTF lightmap must override loader image orientation');
assert.ok(/night\.flipY\s*=\s*false/.test(home),'night glTF lightmap must use same corrected orientation');
console.log('PASS: actual Blender Raw asymmetric HDR corners sampled at raw glTF UVs; false orientation matches all four, true reverses charts; day/night runtime overrides present');
