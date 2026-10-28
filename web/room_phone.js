// The phone's screen in the room (#75): what he looks at, drawn on a canvas at the glass's own aspect, so nothing is
// stretched; a thin status bar (Tokyo time, signal, battery), rounded corners, a dark glass when it is off, and the
// colour it throws on his face and hand. Generic on purpose: no OS logo, no app or brand UI.
//
//   import { PhoneScreen, phoneGlow } from "./room_phone.js";
//   const ps = new PhoneScreen(THREE, renderer, aspect);    // aspect = glass width / height
//   ps.show(imgOrCanvas, {time:"21:04", battery:0.62});     // cover-fits the page under the status bar, top first
//   ps.off();                                               // dark glass; ps.on tells which
//   mesh.material.map = ps.texture;                         // one texture for both states (repeat 1, offset 0)
//   light.intensity = phoneGlow(day, ps.on); light.color.copy(ps.glow);

const H = 1280;                          // canvas height in pixels: the glass is ~14 cm tall, seen at ~40 cm in close-ups
const BAR = 0.034;                       // status bar height (fraction of the screen height)
const RADIUS = 0.085;                    // corner radius (fraction of the screen width)

export function tokyoTime(date = new Date()){
  try { return new Intl.DateTimeFormat("en-GB", {timeZone:"Asia/Tokyo", hour:"2-digit", minute:"2-digit", hour12:false}).format(date); }
  catch { return date.toTimeString().slice(0, 5); }
}

// a battery level that drains through his day and charges at night (a look only; nothing measures it): one continuous
// curve, 12 % at midnight, full at 07:00, back to 12 % by the next midnight (no jump at 00:00)
const BAT_LO = 0.12, BAT_FULL_H = 7;
export function batteryAt(hour){
  const h = ((hour % 24) + 24) % 24;
  return h < BAT_FULL_H ? BAT_LO + (1 - BAT_LO) * h / BAT_FULL_H : Math.max(BAT_LO, 1 - (1 - BAT_LO) * (h - BAT_FULL_H) / (24 - BAT_FULL_H));
}

// how bright the light the screen throws on his face and hand is: only when the screen is on, soft by day, clear at night
export function phoneGlow(day, on){
  return on ? 0.12 + 0.75 * (1 - Math.max(0, Math.min(1, day))) : 0;
}

function roundRect(g, x, y, w, h, r){
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

export class PhoneScreen {
  constructor(THREE, renderer, aspect){
    this.THREE = THREE;
    this.canvas = document.createElement("canvas");
    this.canvas.height = H; this.canvas.width = Math.round(H * aspect);
    this.g = this.canvas.getContext("2d");
    const t = this.texture = new THREE.CanvasTexture(this.canvas);
    t.colorSpace = THREE.SRGBColorSpace;                 // canvas pixels are sRGB
    t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; t.generateMipmaps = true;
    this.glow = new THREE.Color(0xcfe0ff); this.on = false; this.src = null; this.opts = {};
    this.off();
  }
  get aspect(){ return this.canvas.width / this.canvas.height; }

  // the page (or a drawn view) under the status bar: scaled to the screen's width, its top first; never stretched
  show(src, opts = {}){
    this.src = src; this.opts = opts; this.on = true;
    const {g, canvas:{width:W, height:Hh}} = this, bar = Math.round(Hh * BAR);
    this.clip(() => {
      g.fillStyle = opts.background || "#ffffff"; g.fillRect(0, 0, W, Hh);
      const sw = src.naturalWidth || src.videoWidth || src.width, sh = src.naturalHeight || src.videoHeight || src.height;
      if (sw && sh) {
        const k = W / sw, area = Hh - bar, h = Math.min(sh, area / k);       // source rows that fit
        g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
        g.drawImage(src, 0, 0, sw, h, 0, bar, W, h * k);
      }
      this.statusBar(opts);
    });
    this.glow.copy(this.average(bar));
    this.texture.needsUpdate = true; return this;
  }
  // a new minute or battery level: redraw the bar only
  tick(opts = {}){ if (this.on && this.src) this.show(this.src, {...this.opts, ...opts}); return this; }

  // off: dark glass with a faint diagonal sheen, the same rounded corners
  off(){
    this.on = false; this.src = null;
    const {g, canvas:{width:W, height:Hh}} = this;
    g.fillStyle = "#000"; g.fillRect(0, 0, W, Hh);
    this.clip(() => {
      g.fillStyle = "#07080a"; g.fillRect(0, 0, W, Hh);
      const s = g.createLinearGradient(0, 0, W, Hh * 0.6);
      s.addColorStop(0, "rgba(255,255,255,0.00)"); s.addColorStop(0.45, "rgba(255,255,255,0.05)"); s.addColorStop(0.55, "rgba(255,255,255,0.00)");
      g.fillStyle = s; g.fillRect(0, 0, W, Hh);
    });
    this.texture.needsUpdate = true; return this;
  }

  clip(draw){
    const {g, canvas:{width:W, height:Hh}} = this;
    g.save(); g.fillStyle = "#000"; g.fillRect(0, 0, W, Hh);           // the corners outside the glass stay black (bezel)
    roundRect(g, 0, 0, W, Hh, Math.round(W * RADIUS)); g.clip(); draw(); g.restore();
  }

  // the bar: time on the left; signal and battery on the right. Plain shapes, readable over any page
  statusBar({time = tokyoTime(), battery = 0.8, signal = 3, dark = true} = {}){
    const {g, canvas:{width:W, height:Hh}} = this, bar = Math.round(Hh * BAR), fg = dark ? "#f2f2f2" : "#111", pad = Math.round(W * 0.09);
    g.fillStyle = dark ? "#0d0e12" : "#f4f4f6"; g.fillRect(0, 0, W, bar);
    g.fillStyle = fg; g.textBaseline = "middle"; g.font = `600 ${Math.round(bar * 0.56)}px system-ui, -apple-system, "Segoe UI", sans-serif`;
    g.fillText(time, pad, bar * 0.54);
    const bh = bar * 0.38, bw = bh * 2.1, bx = W - pad - bw, by = (bar - bh) / 2 + bar * 0.04;   // battery
    g.strokeStyle = fg; g.lineWidth = Math.max(1, bar * 0.05); roundRect(g, bx, by, bw, bh, bh * 0.22); g.stroke();
    g.fillRect(bx + bw + bar * 0.03, by + bh * 0.3, bar * 0.05, bh * 0.4);
    const lvl = Math.max(0, Math.min(1, battery));
    g.fillStyle = lvl < 0.2 ? "#e5484d" : fg; g.fillRect(bx + bh * 0.16, by + bh * 0.16, (bw - bh * 0.32) * lvl, bh * 0.68);
    const sx = bx - bar * 0.95, base = by + bh;                                                 // signal: 4 bars
    for (let i = 0; i < 4; i++) {
      const h = bh * (0.35 + 0.65 * i / 3); g.fillStyle = i < signal ? fg : (dark ? "#55565c" : "#b9bac0");
      g.fillRect(sx + i * bar * 0.16, base - h, bar * 0.1, h);
    }
  }

  // the colour of the page (under the bar), lifted so it reads as light
  average(top){
    try {
      const c = document.createElement("canvas"); c.width = c.height = 8; const x = c.getContext("2d", {willReadFrequently:true});
      x.drawImage(this.canvas, 0, top, this.canvas.width, this.canvas.height - top, 0, 0, 8, 8);
      const d = x.getImageData(0, 0, 8, 8).data; let r = 0, gg = 0, b = 0;
      for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; }
      const n = d.length / 4, col = new this.THREE.Color().setRGB(r / n / 255, gg / n / 255, b / n / 255, this.THREE.SRGBColorSpace), hsl = {};
      col.getHSL(hsl); return col.setHSL(hsl.h, Math.min(0.6, hsl.s * 1.2 + 0.05), 0.62 + 0.25 * hsl.l);
    } catch { return new this.THREE.Color(0xcfe0ff); }
  }
}

// ---- the chat app and the order app: home_phone.life_view decides which one is due; these draw only the view they are
// given. drawLifeApp(g, w, h, view, top) paints into a 2D context of w x h below `top` px (the status bar's band). A view
// of app 'short', or none, paints nothing: the page then shows the browser's own frame. Sizes scale with the width (390 px
// is the base), so one view fits the classic room's glass and the house page's screen alike.
const LIFE_BASE = 390, LIFE_FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
function lifeWrap(g, text, width, max){
  const out = []; let line = "";
  for (const word of String(text || "").split(/\s+/)) {
    const t = line ? line + " " + word : word;
    if (g.measureText(t).width > width && line) { out.push(line); line = word; if (out.length >= max) break; }
    else line = t;
  }
  if (line && out.length < max) out.push(line);
  return out;
}
function lifeChat(g, w, h, view, top){
  const s = w / LIFE_BASE, pad = 22 * s, bw = w - 2 * pad, inner = 14 * s;
  const rows = Array.isArray(view.lines) ? view.lines : [];
  g.fillStyle = "#0d0f15"; g.fillRect(0, top, w, h - top);
  g.fillStyle = "#151924"; g.fillRect(0, top, w, 56 * s);
  g.fillStyle = "#e6e8ef"; g.font = `bold ${24 * s}px ${LIFE_FONT}`; g.textAlign = "left"; g.fillText("Chat", pad, top + 37 * s);
  if (!rows.length) { g.fillStyle = "#7b8196"; g.font = `${18 * s}px ${LIFE_FONT}`; g.fillText("no messages yet", pad, top + 110 * s); }
  // newest at the bottom, laid out upwards until the glass is full (older lines are let go); measured in the body's font
  g.font = `${16 * s}px ${LIFE_FONT}`;
  const blocks = rows.map(x => ({x, lines: lifeWrap(g, x.text, bw - 2 * inner, 4)}));
  let y = h - (view.why ? 52 : 34) * s;
  for (let i = blocks.length - 1; i >= 0; i--) {
    const {x, lines} = blocks[i], extra = x.re ? 18 * s : 0, bh = (48 + 22 * lines.length) * s + extra;
    y -= bh + 8 * s; if (y < top + 70 * s) break;
    const mine = x.kind !== "viewer", left = mine ? w - pad - bw : pad;     // his replies and reactions on the right
    g.fillStyle = mine ? "#3a2510" : "#1b1f2b"; g.beginPath();
    if (g.roundRect) g.roundRect(left, y, bw, bh, 12 * s); else g.rect(left, y, bw, bh);
    g.fill();
    if (mine) { g.fillStyle = "#ff9a3c"; g.fillRect(left, y + 8 * s, 4 * s, bh - 16 * s); }
    g.font = `${12 * s}px ${LIFE_FONT}`; g.fillStyle = mine ? "#ffb877" : "#7b8196";
    g.fillText(`${String(x.who || "")} · ${String(x.t || "")}`, left + inner, y + 20 * s);
    let ty = y + 40 * s;
    if (x.re) { g.fillStyle = "#8d93a6"; g.fillText(`to a viewer: “${String(x.re)}”`, left + inner, ty); ty += 18 * s; }
    g.font = `${16 * s}px ${LIFE_FONT}`; g.fillStyle = mine ? "#fff1e2" : "#d5d8e2";
    lines.forEach((l, k) => g.fillText(l, left + inner, ty + k * 22 * s));
  }
  if (view.why) { g.fillStyle = "#c79a7a"; g.font = `${12 * s}px ${LIFE_FONT}`; g.fillText(String(view.why), pad, h - 34 * s); }
  g.fillStyle = "#6f7488"; g.font = `${11 * s}px ${LIFE_FONT}`;
  g.fillText("his replies are AI-written · his reactions are fixed lines", pad, h - 14 * s);
}
function lifeOrder(g, w, h, view, top){
  const s = w / LIFE_BASE, X = 24 * s, span = h - top, at = f => top + span * f;
  g.fillStyle = "#f6f4ef"; g.fillRect(0, top, w, span);
  g.fillStyle = "#06c167"; g.fillRect(0, top, w, span * 0.13);
  g.fillStyle = "#fff"; g.textAlign = "left"; g.font = `bold ${20 * s}px ${LIFE_FONT}`;
  g.fillText(view.dish ? `Your order: 1 × ${String(view.dish)}` : "Your order", X, at(0.085));
  g.font = `${13 * s}px ${LIFE_FONT}`; g.fillText("Kichijōji · simulated delivery", X, at(0.115));
  g.fillStyle = "#111"; g.font = `bold ${58 * s}px ${LIFE_FONT}`;
  g.fillText(view.eta_min != null ? `${view.eta_min} min` : "…", X, at(0.23));
  g.font = `${15 * s}px ${LIFE_FONT}`; g.fillStyle = "#555"; g.fillText(String(view.status || ""), X, at(0.265));
  const steps = Array.isArray(view.steps) ? view.steps : [], step = Number.isInteger(view.step) ? view.step : 0;
  steps.forEach((label, i) => {
    const y = at(0.44 + i * 0.075), done = i <= step;
    g.fillStyle = done ? "#06c167" : "#d6d2c8"; g.beginPath(); g.arc(36 * s, y, 7 * s, 0, 2 * Math.PI); g.fill();
    g.fillStyle = done ? "#111" : "#999"; g.font = `${i === step ? "bold " : ""}${15 * s}px ${LIFE_FONT}`;
    g.fillText(String(label), 60 * s, y + 5 * s);
  });
  g.fillStyle = "#999"; g.font = `${12 * s}px ${LIFE_FONT}`; g.fillText("Food orders and the courier are simulated.", X, at(0.965));
}
export function drawLifeApp(g, w, h, view, top = 0){
  if (!view || (view.app !== "chat" && view.app !== "order")) return false;
  g.save();
  try { if (view.app === "order") lifeOrder(g, w, h, view, top); else lifeChat(g, w, h, view, top); }
  finally { g.restore(); }
  return true;
}
// the view as a canvas, for the classic room's glass (PhoneScreen.show draws its status bar over the top `top` px)
export function lifeAppCanvas(view, w = LIFE_BASE, h = 844, top = 0){
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  drawLifeApp(c.getContext("2d"), w, h, view, top); return c;
}
