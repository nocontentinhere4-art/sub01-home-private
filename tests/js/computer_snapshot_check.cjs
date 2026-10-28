const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../computer/worker.cjs'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  const listeners = {}, intervals = [], signals = {}, captures = [], events = [], messages = [];
  let onLine, stored = Buffer.from('old'), pending;
  const guest = {add_listener: (name, fn) => listeners[name] = fn,
    run() {}, serial0_send(text) { events.push('input:' + text); }, is_running: () => true,
    save_state() {
      const promise = new Promise((resolve, reject) => captures.push({resolve, reject}));
      events.push('capture'); return promise;
    }, destroy() { events.push('destroy'); }};
  const filesystem = {existsSync: () => false, mkdirSync() {},
    writeFileSync(file, bytes) { assert.equal(file, '/mock/computer.bin.tmp'); pending = bytes; events.push('write'); },
    renameSync(from, to) { assert.equal(from, '/mock/computer.bin.tmp'); assert.equal(to, '/mock/computer.bin'); stored = pending; events.push('rename'); }};
  const context = {Buffer, setInterval: fn => intervals.push(fn), __dirname: '/mock',
    process: {env: {SUB01_VM_STATE: '/mock/computer.bin'}, stdin: {}, stdout: {write: text => messages.push(JSON.parse(text))},
      exit: () => events.push('exit'), on: (name, fn) => signals[name] = fn},
    require: name => name === './libv86.cjs' ? {V86: function() {return guest;}}
      : name === './guest_keyboard.cjs' ? {guestKeyboard:()=>({cancel(){},enqueue:async()=>true})}
      : name === './guest_mouse.cjs' ? require('../../computer/guest_mouse.cjs')
      : name === './vga_framebuffer.cjs' ? require('../../computer/vga_framebuffer.cjs')
      : name === './input_receipts.cjs' ? require('../../computer/input_receipts.cjs')
      : name === 'fs' ? filesystem : name === 'readline' ? {createInterface: () => ({on: (name, fn) => onLine = fn})} : require(name)};
  vm.runInNewContext(source, context);
  for (const byte of Buffer.from('~# ')) listeners['serial0-output-byte'](byte);
  return {events, messages, captures, periodic: () => intervals[1](),
    line: object => onLine(JSON.stringify(object)), signal: name => signals[name](), stored: () => stored.toString()};
}

(async () => {
  const overlapping = fixture();
  const periodic = overlapping.periodic();
  const closing = overlapping.line({type: 'shutdown'});
  await overlapping.signal('SIGTERM'); // A second shutdown cannot destroy early.
  await overlapping.line({type: 'input', text: 'touch late\n'});
  assert.deepEqual(overlapping.events, ['capture']);
  overlapping.captures[0].resolve(Buffer.from('periodic'));
  await periodic; await flush();
  assert.equal(overlapping.captures.length, 2, 'Shutdown must capture newer guest state after the older save');
  assert.equal(overlapping.events.includes('destroy'), false);
  overlapping.captures[1].resolve(Buffer.from('latest'));
  await closing;
  assert.equal(overlapping.stored(), 'latest');
  assert.deepEqual(overlapping.events, ['capture', 'write', 'rename', 'capture', 'write', 'rename', 'destroy', 'exit']);

  const recovery = fixture();
  const failedPeriodic = recovery.periodic();
  const recoveredClosing = recovery.signal('SIGINT');
  recovery.captures[0].reject(new Error('capture failed'));
  await failedPeriodic; await flush();
  assert.equal(recovery.captures.length, 2);
  assert.equal(recovery.stored(), 'old', 'Failed capture cannot replace previous valid snapshot');
  recovery.captures[1].resolve(Buffer.from('recovered'));
  await recoveredClosing;
  assert.equal(recovery.stored(), 'recovered');
  assert(recovery.messages.some(m => m.type === 'error' && m.message === 'VM snapshot failed'));

  const finalFailure = fixture();
  const failedClosing = finalFailure.line({type: 'shutdown'});
  finalFailure.captures[0].reject(new Error('capture failed'));
  await failedClosing;
  assert.equal(finalFailure.stored(), 'old');
  assert.equal(finalFailure.events.filter(e => e === 'destroy').length, 1);
  assert(finalFailure.messages.some(m => m.type === 'error'));
  console.log('Computer snapshot overlap, latest-state capture, atomic replacement and failure handling verified.');
})().catch(error => {console.error(error); process.exitCode = 1;});
