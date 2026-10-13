// The 3D phone shows what SUB-01 actually has open: while he is on the phone
// and the browser service has a public phone page, its real frame (by frame
// identity) is painted under a status bar. Otherwise the caller keeps drawing
// the idle home screen. Privacy and hidden pages never fetch or paint.
import { createOwnedBitmapPainter } from "./owned_bitmap_painter.mjs?v=1";

const APP_LABELS = { page: "Browser", search: "Search", video: "Video", browser: "Browser", music: "Music", home: "Home" };

export function phoneAppLabel(app) {
  return APP_LABELS[app] || "Browser";
}

export function createPhoneScreen({
  canvas, texture, getState,
  createPage = (w, h) => Object.assign(document.createElement("canvas"), { width: w, height: h }),
  painterFactory = createOwnedBitmapPainter,
}) {
  const W = canvas.width, H = canvas.height, BAR = 52, page = createPage(W, H - BAR);
  let pageKey = null, pageNote = "", composedKey = "", showing = false;
  const visible = s => !s.privacy && !s.hidden;
  const frameKey = () => {
    const s = getState();
    return s.activity === "phone" && visible(s) && s.frameId ? s.frameId : null;
  };
  const painter = painterFactory({
    getContextKey: frameKey,
    isActive: () => visible(getState()),
    getURL: id => "/api/screen/phone.jpg?frame_id=" + encodeURIComponent(id),
    dedupPaintedKey: true,
    paint: (image, key) => {
      const p = page.getContext("2d");
      p.fillStyle = "#f4f1ec"; p.fillRect(0, 0, page.width, page.height);
      // Fit width (a phone page is portrait); crop the bottom rather than letterbox.
      const scale = page.width / image.width;
      p.drawImage(image, 0, 0, page.width, image.height * scale);
      pageKey = key; pageNote = ""; composedKey = "";
      compose();
    },
    onUnavailable: (key, response) => { pageNote = response.status === 409 ? "Updating his page…" : "Page not available"; composedKey = ""; compose(); },
    onError: () => { pageNote = "Page not available"; composedKey = ""; compose(); },
    onTimeout: () => { pageNote = "Loading…"; composedKey = ""; compose(); },
  });

  function compose() {
    const s = getState();
    if (s.activity !== "phone" || !visible(s)) return false;
    const key = `${s.time}/${s.battery}/${s.app}/${pageKey}/${s.frameId}/${pageNote}/${s.title || ""}`;
    if (key === composedKey) return true;
    composedKey = key;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#101418"; ctx.fillRect(0, 0, W, BAR);
    ctx.fillStyle = "#f7eee4"; ctx.font = "16px system-ui";
    ctx.textAlign = "left"; ctx.fillText(s.time, 16, 22);
    ctx.textAlign = "right"; ctx.fillText(`${s.battery ?? "—"}%`, W - 16, 22);
    ctx.textAlign = "left"; ctx.font = "13px system-ui"; ctx.fillStyle = "#b9c2c8";
    const title = (s.title || phoneAppLabel(s.app)).slice(0, 34);
    ctx.fillText(title, 16, 43);
    if (pageKey && pageKey === s.frameId) ctx.drawImage(page, 0, BAR);
    else {
      ctx.fillStyle = "#1d262c"; ctx.fillRect(0, BAR, W, H - BAR);
      ctx.fillStyle = "#e9e2d8"; ctx.textAlign = "center"; ctx.font = "20px system-ui";
      ctx.fillText(phoneAppLabel(s.app), W / 2, H / 2 - 8);
      ctx.font = "14px system-ui"; ctx.fillStyle = "#aab4ba";
      ctx.fillText(pageNote || (s.frameId ? "Loading…" : "Nothing open right now"), W / 2, H / 2 + 20);
    }
    texture.needsUpdate = true;
    return true;
  }

  return {
    // Returns true when the phone shows its live app (the caller then skips
    // the idle home screen), false when the idle screen should be drawn.
    update() {
      painter.synchronize();
      const s = getState();
      if (s.activity !== "phone" || !visible(s)) {
        if (showing) { showing = false; composedKey = ""; }
        return false;
      }
      showing = true;
      if (pageKey && pageKey !== s.frameId) pageKey = null;
      if (s.frameId) void painter.update();
      return compose();
    },
    invalidate() { painter.invalidate(); pageKey = null; composedKey = ""; pageNote = ""; },
    state() { return { ...painter.state(), showing, pageKey }; },
    dispose() { painter.dispose(); },
  };
}
