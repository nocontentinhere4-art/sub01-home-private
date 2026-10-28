// Optional house assets named in web/house/assets/optional-manifest.json.
// Each file gets exactly one request per page load and is never retried. A file
// that is missing or unreadable is logged once, keeps its procedural placeholder
// and is named in the House panel. Each get() settles with its single request,
// so a missing file cannot hold the loading counter open.
export const OPTIONAL_MANIFEST_URL = '/house/assets/optional-manifest.json?v=1';
const ASSET_ROOT = '/house/assets/';
const CACHE_KEY = '?v=1';

export function createOptionalAssets({
  loadGltf,
  fetchImpl = url => fetch(url),
  manifestUrl = OPTIONAL_MANIFEST_URL,
  warn = (...args) => console.warn(...args),
} = {}) {
  if (typeof loadGltf !== 'function') throw new TypeError('createOptionalAssets needs loadGltf(url)');
  const records = new Map();
  let noun = 'item';
  const listed = Promise.resolve()
    .then(() => fetchImpl(manifestUrl))
    .then(response => {
      if (!response.ok) throw Error('manifest ' + response.status);
      return response.json();
    })
    .then(json => {
      if (!Array.isArray(json?.assets)) throw Error('manifest lists no assets');
      if (typeof json.noun === 'string') noun = json.noun;
      return json.assets;
    });
  // Each get() reports a manifest failure itself, so this handler only prevents an unhandled rejection.
  listed.catch(() => {});

  function record(id) {
    if (!records.has(id))
      records.set(id, {id, label: id, order: Infinity, status: 'pending', reason: '', promise: null});
    return records.get(id);
  }

  function fail(id, error) {
    const entry = record(id);
    if (entry.status === 'missing') return;  // exactly one warning per asset
    entry.status = 'missing';
    entry.reason = error?.message || String(error);
    warn(`Optional house asset missing: ${entry.label} (${id}): ${entry.reason}. The room keeps its placeholder.`);
  }

  async function fetchAsset(item) {
    const gltf = await loadGltf(ASSET_ROOT + item.glb + CACHE_KEY);
    const response = await fetchImpl(ASSET_ROOT + item.sidecar + CACHE_KEY);
    if (!response.ok) throw Error('sidecar ' + response.status);
    return {sidecar: await response.json(), gltf};
  }

  // Resolves to {sidecar, gltf}; rejects once, after fail() has recorded the asset.
  function get(id) {
    const entry = record(id);
    if (!entry.promise) {
      entry.promise = listed.then(assets => {
        const index = assets.findIndex(item => item.id === id);
        if (index < 0) throw Error('not listed in optional-manifest.json');
        Object.assign(entry, {label: assets[index].label, order: index});
        return fetchAsset(assets[index]);
      }).then(asset => {
        if (entry.status === 'pending') entry.status = 'loaded';
        return asset;
      }, error => {
        fail(id, error);
        throw error;
      });
    }
    return entry.promise;
  }

  function summary() {
    const entries = [...records.values()].sort((a, b) => a.order - b.order);
    return {
      loaded: entries.filter(e => e.status === 'loaded').map(e => e.id),
      missing: entries.filter(e => e.status === 'missing').map(e => ({id: e.id, label: e.label, reason: e.reason})),
      pending: entries.filter(e => e.status === 'pending').map(e => e.id),
    };
  }

  // One line for the House panel, or '' when every requested asset loaded.
  function noteText() {
    const {missing} = summary();
    if (!missing.length) return '';
    return `${missing.length} ${noun}${missing.length === 1 ? '' : 's'} missing: ${missing.map(m => m.label).join(', ')}`;
  }

  return {get, fail, summary, noteText};
}
