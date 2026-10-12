import assert from 'node:assert/strict';
import {createDraftSubmit} from '../../web/house/draft_submit.mjs';
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
};
function fixture(submit, afterSuccess) {
  const input = new EventTarget();
  input.value = 'first draft';
  const button = {disabled: false};
  const handler = createDraftSubmit({input, button, submit, afterSuccess});
  return {input, button, handler, type(text) {input.value = text; input.dispatchEvent(new Event('input'));}};
}

const request = deferred(), refresh = deferred(), sent = [];
const race = fixture(text => {sent.push(text); return request.promise;}, () => refresh.promise);
const sending = race.handler();
assert.equal(race.button.disabled, true);
assert.equal(await race.handler(), false, 'Enter while pending must not submit twice');
race.type('next draft');
request.resolve({ok: true});
await Promise.resolve();
assert.equal(race.input.value, 'next draft', 'Late success must not clear a newer draft');
race.type('edited during refresh');
refresh.resolve();
assert.equal(await sending, true);
assert.equal(race.input.value, 'edited during refresh');
assert.equal(race.button.disabled, false);
assert.deepEqual(sent, ['first draft']);

const unchanged = fixture(async () => ({ok: true}));
assert.equal(await unchanged.handler(), true);
assert.equal(unchanged.input.value, '', 'Only the unchanged accepted draft is cleared');
const denied = fixture(async () => false);
assert.equal(await denied.handler(), false);
assert.equal(denied.input.value, 'first draft', 'Rejected input must remain editable');
assert.equal(denied.button.disabled, false);

const failed = fixture(async () => {throw Error('disconnected');});
await assert.rejects(failed.handler(), /disconnected/);
assert.equal(failed.input.value, 'first draft');
assert.equal(failed.button.disabled, false);

const sameTextResponse = deferred();
const revised = fixture(() => sameTextResponse.promise);
const revisedSending = revised.handler();
revised.type('other'); revised.type('first draft');
sameTextResponse.resolve({ok: true}); await revisedSending;
assert.equal(revised.input.value, 'first draft', 'Editing away and back is still a new draft revision');
console.log('PASS: accepted drafts, rejected/network-failed drafts, duplicate submissions and edits during request/refresh');
