// Device request helpers shared by the house page.
import { createOwnedBitmapPainter } from "./owned_bitmap_painter.mjs?v=1";

// Minecraft TV frames: the owned painter keeps polling for live play, but a
// conditional request (If-None-Match on the frame identity) returns an empty
// 304 while the picture is unchanged, e.g. a paused game. The validator is
// sent only while the TV canvas still shows that exact frame; any invalidate,
// inactive context or unavailable/error/timeout paint forgets it.
export function createMinecraftFrameFeed({
  getContextKey, onUnavailable = () => {}, onError = () => {}, onTimeout = () => {}, paint,
  fetch: fetchImpl = (url, init) => fetch(url, init), painterFactory = createOwnedBitmapPainter, ...rest
}) {
  let shown = null, pending = null;
  const forget = () => { shown = null; pending = null; };
  const painter = painterFactory({
    ...rest,
    getContextKey: () => { const key = getContextKey(); if (!key) forget(); return key; },
    fetchResponse: async (url, signal) => {
      const headers = shown ? { "If-None-Match": shown } : {};
      const response = await fetchImpl(url, { signal, cache: "no-store", headers });
      pending = response.ok ? response.headers.get("ETag") : null;
      return response;
    },
    paint: (image, key) => { paint(image, key); shown = pending; },
    onUnavailable: (key, response) => {
      if (response.status === 304 && shown) return; // unchanged: keep the painted frame
      forget(); onUnavailable(key, response);
    },
    onError: (...args) => { forget(); onError(...args); },
    onTimeout: (...args) => { forget(); onTimeout(...args); },
  });
  return { ...painter, invalidate() { forget(); painter.invalidate(); }, dispose() { forget(); painter.dispose(); } };
}

// Plain-text reason for a refused device action (400/409/413/423), or null.
// Never returns markup: HTML error pages fall back to the generic message.
export async function actionErrorMessage(response) {
  if (![400, 409, 413, 423].includes(response.status)) return null;
  const type = response.headers?.get?.("Content-Type") || "";
  if (/html|xml|json/i.test(type)) return null;
  let text = "";
  try { text = await response.text(); } catch { return null; }
  text = text.replace(/\s+/g, " ").trim();
  if (!text || /[<>]/.test(text) || /^\d{3}\b/.test(text)) return null;
  return text.length > 160 ? text.slice(0, 157) + "…" : text;
}
