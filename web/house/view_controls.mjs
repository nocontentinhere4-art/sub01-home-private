const key = 'sub01-home-view';
export const defaultViewControls = Object.freeze({fov:64,sensitivity:1});
export function normalizeViewControls(value) {
  const bounded = (v,min,max,fallback) => typeof v === 'number' && Number.isFinite(v) ? Math.max(min,Math.min(max,v)) : fallback;
  return {fov:bounded(value?.fov,50,90,64), sensitivity:bounded(value?.sensitivity,.5,2,1)};
}
export function loadViewControls(storage) {
  try { return normalizeViewControls(JSON.parse(storage.getItem(key))); }
  catch { return {...defaultViewControls}; }
}
export function saveViewControls(storage,value) {
  const result=normalizeViewControls(value);
  try { storage.setItem(key,JSON.stringify(result)); } catch { /* usable for this view if storage is unavailable */ }
  return result;
}
