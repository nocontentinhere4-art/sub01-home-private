import assert from 'node:assert/strict';
import {createEyeView, frameMode, safeFrameSrc, captionFor, LID_MS} from '../../web/house/eye_view.mjs';

// Minimal fake DOM: only what eye_view uses (no jsdom).
class FakeClassList {
  constructor() { this.set = new Set(); }
  add(c) { this.set.add(c); }
  remove(c) { this.set.delete(c); }
  toggle(c, on) { if (on === undefined) on = !this.set.has(c); on ? this.set.add(c) : this.set.delete(c); return on; }
  contains(c) { return this.set.has(c); }
}
class FakeElement {
  constructor(tag) {
    Object.assign(this, {tagName: tag.toUpperCase(), children: [], attributes: {}, dataset: {}, hidden: false,
      textContent: '', className: '', classList: new FakeClassList(), listeners: {}, parent: null, type: '', alt: ''});
  }
  append(...nodes) { for (const n of nodes) { n.parent = this; this.children.push(n); } }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  click() { for (const fn of this.listeners.click || []) fn(); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); }
}
const document = {createElement: tag => new FakeElement(tag)};
let timers = [];
const setTimeout = (fn, ms) => { timers.push({fn, ms}); return timers.length; };
const clearTimeout = id => { if (timers[id - 1]) timers[id - 1].fn = null; };
const runTimers = () => { const t = timers; timers = []; for (const x of t) if (x.fn) x.fn(); return t.filter(x => x.fn).map(x => x.ms); };

// Helpers.
assert.equal(frameMode({mode: 'outside', stage: 'AWAKE'}), 'outside');
assert.equal(frameMode({stage: 'REM'}), 'dream');
assert.equal(frameMode({stage: 'NREM'}), 'closed');
assert.equal(frameMode({mode: 'awake'}), null);
assert.equal(safeFrameSrc('/eye/1700000000000.jpg'), '/eye/1700000000000.jpg');
for (const bad of ['https://evil.example/x.jpg', '/eye/../secret.jpg', 'javascript:alert(1)', '/diary-img/x.jpg', null])
  assert.equal(safeFrameSrc(bad), null, String(bad));
assert.equal(captionFor('off', {}), '');
assert.equal(captionFor('dream', {t: '03:12', thought: 'a bridge of paper'}), 'Dreaming · 03:12 — “a bridge of paper”');
assert.match(captionFor('outside', {t: '15:01', resting: 'resting its eyes'}), /^What he sees · 15:01 · resting its eyes$/);

const container = new FakeElement('div');
const view = createEyeView(container, {document, setTimeout, clearTimeout});
const root = view.element, [picture, upper, lower] = root.children;
assert.equal(container.children[0], root);
assert.equal(root.attributes['aria-label'], 'What he sees');

// Awake at home: hidden, frames ignored.
assert.equal(root.hidden, true);
view.accept({type: 'eye_state', mode: 'off', since: 1});
view.accept({type: 'eye', mode: 'outside', stage: 'AWAKE', img: '/eye/1.jpg'});
assert.equal(root.hidden, true);
assert.equal(picture.getAttribute('src'), null);

// Falling asleep (REM): the eyelids close first, then the dream fades in.
view.accept({type: 'eye_state', mode: 'dream', since: 2});
assert.equal(root.hidden, false);
assert.equal(root.dataset.mode, 'dream');
assert.ok(upper.classList.contains('eye-view-lid-closed') && lower.classList.contains('eye-view-lid-closed'));
view.accept({type: 'eye', mode: 'dream', stage: 'REM', img: '/eye/2.jpg', t: '03:00', thought: 'stairs of water'});
assert.equal(view.snapshot().frameShown, false, 'not before the lids are closed');
assert.deepEqual(runTimers(), [LID_MS]);
assert.equal(view.snapshot().frameShown, true);
assert.equal(picture.getAttribute('src'), '/eye/2.jpg');
assert.ok(picture.classList.contains('eye-view-visible'));
assert.match(view.snapshot().caption, /^Dreaming · 03:00/);
// A frame of the wrong mode, or from elsewhere, is ignored.
view.accept({type: 'eye', mode: 'outside', img: '/eye/3.jpg'});
view.accept({type: 'eye', mode: 'dream', img: 'https://example.org/x.jpg'});
assert.equal(picture.getAttribute('src'), '/eye/2.jpg');

// REM -> NREM: still asleep, no new lid animation; the near-dark class is set.
view.accept({type: 'eye_state', mode: 'closed', since: 3});
assert.deepEqual(runTimers(), []);
assert.ok(root.classList.contains('eye-view-near-dark'));
assert.equal(view.snapshot().frameShown, false, 'the dream frame does not carry into deep sleep');
view.accept({type: 'eye', stage: 'NREM', img: '/eye/4.jpg'});
assert.equal(view.snapshot().frameShown, true);
assert.equal(view.snapshot().caption.startsWith('Deep sleep · eyes closed'), true);

// Bathroom privacy (from a home state): hidden at once, no picture on screen.
view.accept({home: {privacy: true}});
assert.equal(root.hidden, true);
assert.equal(picture.getAttribute('src'), null);
view.accept({type: 'eye', stage: 'NREM', img: '/eye/5.jpg'});
assert.equal(view.snapshot().frameShown, false);
assert.equal(view.snapshot().caption, '');
// Privacy over: the lids close again before anything is shown.
view.accept({home: {privacy: false}});
assert.equal(root.hidden, false);
assert.equal(view.snapshot().frameShown, false);
assert.deepEqual(runTimers(), [LID_MS]);
assert.equal(view.snapshot().frameShown, true);
assert.equal(picture.getAttribute('src'), '/eye/5.jpg');

// Waking up at home: hidden, timers cancelled, no picture kept.
view.accept({type: 'eye_state', mode: 'off', since: 4});
assert.equal(root.hidden, true);
assert.equal(picture.getAttribute('src'), null);
assert.ok(!upper.classList.contains('eye-view-lid-closed'));

// Outside: no eyelids, the latest real frame of what he sees.
view.accept({type: 'eye_state', mode: 'outside', since: 5});
assert.equal(root.hidden, false);
assert.ok(!upper.classList.contains('eye-view-lid-closed'));
assert.deepEqual(runTimers(), []);
view.accept({type: 'eye', mode: 'outside', stage: 'AWAKE', img: '/eye/6.jpg', t: '15:20'});
assert.equal(picture.getAttribute('src'), '/eye/6.jpg');
assert.equal(view.snapshot().caption, 'What he sees · 15:20');
view.accept({type: 'eye', stage: 'REM', img: '/eye/7.jpg'});            // not a dream while he is out
assert.equal(picture.getAttribute('src'), '/eye/6.jpg');

// Minimise / expand.
const toggle = root.children.find(c => c.tagName === 'BUTTON');
toggle.click();
assert.ok(root.classList.contains('eye-view-compact'));
assert.equal(toggle.textContent, 'Expand');
toggle.click();
assert.equal(toggle.textContent, 'Minimise');

// A short sleep: falling asleep then waking before the lids close never shows a frame.
view.accept({type: 'eye_state', mode: 'dream', since: 6});
view.accept({type: 'eye_state', mode: 'off', since: 7});
assert.deepEqual(runTimers(), []);
assert.equal(root.hidden, true);

// Unknown modes are off.
view.accept({type: 'eye_state', mode: 'gps'});
assert.equal(root.hidden, true);
console.log('eye_view_check: ok');
