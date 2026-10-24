import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createOptionalAssets, OPTIONAL_MANIFEST_URL} from '../../web/house/optional_assets.mjs';

// The real committed manifest drives every case; only the network is simulated.
const manifestText = fs.readFileSync(new URL('../../web/house/assets/optional-manifest.json', import.meta.url), 'utf8');
const manifest = JSON.parse(manifestText);
const ids = manifest.assets.map(item => item.id);
assert.deepEqual(ids, ['bath-door', 'toilet', 'vanity', 'bath-light']);
assert.equal(OPTIONAL_MANIFEST_URL, '/house/assets/optional-manifest.json?v=1');

const glbUrl = item => '/house/assets/' + item.glb + '?v=1';
const sidecarUrl = item => '/house/assets/' + item.sidecar + '?v=1';
const byId = id => manifest.assets.find(item => item.id === id);

function world({missing = [], sidecarMissing = [], manifestStatus = 200} = {}) {
  const requests = [], warnings = [];
  const response = (ok, status, body = {}) => ({ok, status, json: async () => body});
  const fetchImpl = async url => {
    requests.push(url);
    if (url === OPTIONAL_MANIFEST_URL) return manifestStatus === 200 ? response(true, 200, manifest) : response(false, manifestStatus);
    const item = manifest.assets.find(entry => sidecarUrl(entry) === url);
    if (!item) throw new Error('unexpected fetch ' + url);
    return sidecarMissing.includes(item.id) ? response(false, 404) : response(true, 200, {id: item.id});
  };
  const loadGltf = async url => {
    requests.push(url);
    const item = manifest.assets.find(entry => glbUrl(entry) === url);
    if (!item) throw new Error('unexpected glb ' + url);
    if (missing.includes(item.id)) throw new Error(`fetch for "${url}" responded with 404: Not Found`);
    return {scene: {id: item.id}};
  };
  const assets = createOptionalAssets({loadGltf, fetchImpl, warn: (...args) => warnings.push(args.join(' '))});
  return {assets, requests, warnings};
}

// A stalled asset would otherwise hang the page's loading counter silently.
async function settledWithin(promises, ms = 2000) {
  let timer;
  const stalled = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('optional assets stalled')), ms); });
  try { return await Promise.race([Promise.allSettled(promises), stalled]); } finally { clearTimeout(timer); }
}

// 1. Every file missing: one request per GLB, no sidecar retries, one warning each, prompt settlement.
{
  const w = world({missing: ids});
  const results = await settledWithin(ids.map(id => w.assets.get(id)));
  assert.ok(results.every(result => result.status === 'rejected'));
  assert.equal(w.warnings.length, 4, 'exactly one console warning per missing asset');
  for (const item of manifest.assets) {
    assert.equal(w.requests.filter(url => url === glbUrl(item)).length, 1, item.id + ' GLB requested once');
    assert.equal(w.requests.filter(url => url === sidecarUrl(item)).length, 0, item.id + ' sidecar skipped after a missing GLB');
  }
  assert.equal(w.requests.length, 1 + 4, 'manifest plus one request per asset');
  assert.equal(w.assets.noteText(), '4 fixtures missing: bathroom door, toilet, vanity, bathroom light');
  assert.deepEqual(w.assets.summary().missing.map(m => m.id), ids);
  assert.deepEqual(w.assets.summary().loaded, []);
  w.assets.fail('toilet', new Error('again'));
  assert.equal(w.warnings.length, 4, 'a repeated failure report does not warn again');
}

// 2. Everything present: no warnings, no note, one GLB and one sidecar per asset.
{
  const w = world({});
  const results = await settledWithin(ids.map(id => w.assets.get(id)));
  assert.ok(results.every(result => result.status === 'fulfilled'));
  assert.deepEqual(results[1].value.sidecar, {id: 'toilet'});
  assert.equal(results[1].value.gltf.scene.id, 'toilet');
  assert.equal(w.warnings.length, 0);
  assert.equal(w.assets.noteText(), '');
  assert.deepEqual(w.assets.summary().loaded, ids);
  assert.equal(w.requests.length, 1 + 2 * 4);
}

// 3. Mixed: a missing sidecar is a missing asset too, and only that one is named.
{
  const w = world({sidecarMissing: ['bath-door']});
  await settledWithin(ids.map(id => w.assets.get(id)));
  assert.equal(w.warnings.length, 1);
  assert.match(w.warnings[0], /bath-door/);
  assert.equal(w.assets.noteText(), '1 fixture missing: bathroom door');
  assert.deepEqual(w.assets.summary().loaded, ['toilet', 'vanity', 'bath-light']);
}

// 4. Manifest unavailable: nothing is requested and each asset is reported once.
{
  const w = world({manifestStatus: 404});
  const results = await settledWithin(ids.map(id => w.assets.get(id)));
  assert.ok(results.every(result => result.status === 'rejected'));
  assert.equal(w.warnings.length, 4);
  assert.match(w.warnings[0], /manifest 404/);
  assert.equal(w.requests.filter(url => url.endsWith('.glb?v=1')).length, 0);
}

// 5. Concurrent callers share one request.
{
  const w = world({});
  const first = w.assets.get('toilet'), second = w.assets.get('toilet');
  assert.equal(first, second);
  await first;
  assert.equal(w.requests.filter(url => url === glbUrl(byId('toilet'))).length, 1);
}

// 6. A failure found after loading (the scene refuses the sidecar) is reported once.
{
  const w = world({});
  await w.assets.get('vanity');
  w.assets.fail('vanity', new Error('sidecar does not match the home.js fallback'));
  w.assets.fail('vanity', new Error('again'));
  assert.equal(w.warnings.length, 1);
  assert.equal(w.assets.noteText(), '1 fixture missing: vanity');
  assert.deepEqual(w.assets.summary().loaded, [], 'a refused asset is no longer reported as loaded');
}

// 7. An id the manifest does not list fails once without touching the network.
{
  const w = world({});
  await assert.rejects(w.assets.get('sink'), /not listed/);
  assert.equal(w.warnings.length, 1);
  assert.equal(w.requests.filter(url => url.includes('sink')).length, 0);
}

assert.throws(() => createOptionalAssets({}), TypeError);
console.log('PASS optional house assets: one request and at most one warning per file; no retries; missing GLBs skip the sidecar; shared callers; apply-time failures reported once; manifest failure reported per asset; the House note lists exactly the missing labels; nothing stalls.');
