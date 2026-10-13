import assert from 'node:assert/strict';
import {createHouseControlsPanel, doorStatusText, lightStatusText, operatorMutate}
  from '../../web/house/house_controls_panel.mjs';

// Minimal fake DOM: only what the panel uses (no jsdom).
let created = 0;
class FakeElement {
  constructor(tag) {
    created++;
    Object.assign(this, {tagName: tag.toUpperCase(), children: [], attributes: {}, dataset: {},
      textContent: '', className: '', disabled: false, title: '', type: '', listeners: {}, parent: null});
  }
  append(...nodes) { for (const n of nodes) { n.parent = this; this.children.push(n); } }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  click() { if (!this.disabled) for (const fn of this.listeners.click || []) fn(); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); }
  *walk() { yield this; for (const c of this.children) yield* c.walk(); }
}
const document = {createElement: tag => new FakeElement(tag)};
const all = root => [...root.walk()];
const button = (root, label) => all(root).find(e => e.tagName === 'BUTTON' && e.attributes['aria-label'] === label);
const statusOf = (root, label) => all(root).find(e => e.attributes.role === 'group' && e.attributes['aria-label'] === label)
  .children.find(c => c.className === 'house-control-status').textContent;
const tick = () => new Promise(r => setTimeout(r, 0));

const door = (open, locked, mode = 'auto') => ({open, locked, state: open ? 'open' : locked ? 'locked' : 'closed', mode});
const light = (on, mode = 'auto') => ({on, mode});
function homeState(extra = {}) {
  return {
    privacy: false,
    doors: {front: door(false, false), bathroom: door(false, false), balcony: door(true, false, 'open')},
    lights: {master: true, dark: true, rooms: {living: light(true), kitchen: light(false, 'off'),
      bedroom: light(false), bathroom: light(false)}},
    settings: {doors: {front: 'auto', bathroom: 'auto', balcony: 'open'},
      lights: {living: 'auto', kitchen: 'off', bedroom: 'auto', bathroom: 'auto'}},
    ...extra,
  };
}

// Status text helpers.
assert.equal(doorStatusText('bathroom', door(false, true)), 'Locked · Occupied');
assert.equal(doorStatusText('front', door(false, true)), 'Locked · Away');
assert.equal(doorStatusText('balcony', door(true, false)), 'Open');
assert.equal(doorStatusText('front', null), 'Unknown');
assert.equal(lightStatusText('living', {master: false, rooms: {living: light(false)}}), 'Off · master lamp off');

// Rendering.
const calls = [];
let key = 'secret', reply = body => ({...homeState().settings, ...body});
const container = new FakeElement('div');
const panel = createHouseControlsPanel(container, {
  document, operatorKey: () => key,
  mutate: async (action, data) => { calls.push([action, data]); return reply(data); },
});
assert.equal(container.children[0], panel.element);
assert.equal(panel.element.attributes['aria-label'], 'House controls');
const buttons = all(panel.element).filter(e => e.tagName === 'BUTTON');
assert.equal(buttons.length, 3 * 3 + 4 * 3);
assert.ok(buttons.every(b => b.type === 'button' && b.attributes['aria-label']));
assert.ok(buttons.every(b => b.disabled), 'disabled until a state arrives');
panel.update(homeState());
const count = created;
assert.equal(statusOf(panel.element, 'Front door'), 'Closed');
assert.equal(statusOf(panel.element, 'Balcony door'), 'Open');
assert.equal(statusOf(panel.element, 'Living room'), 'On');
assert.equal(button(panel.element, 'Balcony door: Open').attributes['aria-pressed'], 'true');
assert.equal(button(panel.element, 'Kitchen: Off').attributes['aria-pressed'], 'true');
assert.equal(button(panel.element, 'Kitchen: Auto').attributes['aria-pressed'], 'false');
assert.ok(!button(panel.element, 'Front door: Open').disabled);

// Updates reuse the DOM.
panel.update(homeState({doors: {...homeState().doors, front: door(false, true)}}));
panel.update(homeState({doors: {...homeState().doors, front: door(true, false, 'open')}}));
assert.equal(created, count, 'no DOM re-creation on update');
assert.equal(statusOf(panel.element, 'Front door'), 'Open');
assert.equal(button(panel.element, 'Front door: Open').attributes['aria-pressed'], 'true');

// Clicks send the right payloads.
button(panel.element, 'Front door: Closed').click();
await tick();
button(panel.element, 'Kitchen: On').click();
await tick();
assert.equal(button(panel.element, 'Front door: Closed').attributes['aria-pressed'], 'true', 'saved mode shown');
assert.deepEqual(calls, [
  ['settings', {doors: {front: 'closed'}}],
  ['settings', {lights: {kitchen: 'on'}}],
]);

// Locked, occupied bathroom: bathroom door disabled with a reason, others work.
panel.update(homeState({privacy: true, doors: {...homeState().doors, bathroom: door(false, true)}}));
assert.equal(statusOf(panel.element, 'Bathroom door'), 'Locked · Occupied');
const bathOpen = button(panel.element, 'Bathroom door: Open');
assert.ok(bathOpen.disabled && /occupied/i.test(bathOpen.title));
bathOpen.click();
await tick();
assert.equal(calls.length, 2, 'no request for a locked occupied bathroom');
assert.ok(!button(panel.element, 'Front door: Auto').disabled);
// Saved while still locked (e.g. privacy began after the click): explained.
panel.update(homeState({doors: {...homeState().doors, bathroom: door(false, true)}}));
button(panel.element, 'Bathroom door: Open').click();
await tick();
assert.deepEqual(calls[2], ['settings', {doors: {bathroom: 'open'}}]);
assert.match(panel.element.children.at(-1).textContent, /stays locked while it is occupied/);

// Other refusals: message, controls stay usable.
reply = () => ({status: 409, reason: 'Busy'});
button(panel.element, 'Living room: Off').click();
await tick();
assert.match(panel.element.children.at(-1).textContent, /Living room was not changed: Busy/);
assert.ok(!button(panel.element, 'Living room: On').disabled);
reply = () => false;
button(panel.element, 'Living room: Off').click();
await tick();
assert.ok(!button(panel.element, 'Living room: On').disabled);

// 403: disabled for this key, re-enabled when the operator key changes.
reply = () => ({status: 403});
button(panel.element, 'Living room: Off').click();
await tick();
assert.ok(buttons.every(b => b.disabled));
assert.match(panel.element.children.at(-1).textContent, /Operator access is required/);
const before = calls.length;
button(panel.element, 'Living room: On').click();
await tick();
assert.equal(calls.length, before);
key = 'another';
panel.refreshOperator();
assert.ok(!button(panel.element, 'Living room: On').disabled);
key = '';
panel.update(homeState());
assert.ok(buttons.every(b => b.disabled), 'no operator key: read-only');

// operatorMutate maps HTTP results.
const fetched = [];
const fake = status => async (url, init) => {
  fetched.push([url, init]);
  return {ok: status === 200, status, json: async () => ({lamp: true}), text: async () => 'Expected object'};
};
assert.deepEqual(await operatorMutate(fake(200), () => 'k')('settings', {lamp: true}), {lamp: true});
assert.equal(fetched[0][0], '/api/home/settings');
assert.equal(fetched[0][1].headers['X-Admin-Token'], 'k');
assert.deepEqual(await operatorMutate(fake(403), () => '')('settings', {}), {status: 403, reason: 'Expected object'});
assert.equal((await operatorMutate(async () => { throw Error('down'); }, () => '')('settings', {})).status, 0);
panel.destroy();
assert.equal(container.children.length, 0);
console.log('house controls panel ok');
