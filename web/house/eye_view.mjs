// What he sees (owner decision 2026-10-13). The eye is open only while he
// sleeps or is outside; the server says which with {type:'eye_state', mode}:
//   closed  - NREM: the eyelids close over the house, then a near-dark trace
//   dream   - REM: the eyelids close, then the dream frames fade in
//   outside - what he sees on the way (the latest real eye frame), no eyelids
//   off     - awake at home: nothing is shown
// Bathroom privacy hides everything at once, whatever the mode. Frames are the
// eye's own images (/eye/...); anything else is ignored. English UI.

export const EYE_MODES = ['closed', 'dream', 'outside', 'off'];
export const LID_MS = 1200;          // eyelids closing, before a dream fades in

const FRAME_MODE = { REM: 'dream', NREM: 'closed', AWAKE: 'outside' };

// The mode a frame belongs to (older servers send only the stage).
export function frameMode(frame) {
  if (!frame) return null;
  if (EYE_MODES.includes(frame.mode)) return frame.mode;
  return FRAME_MODE[frame.stage] ?? null;
}

// Only the eye's own images, on this server.
export function safeFrameSrc(img) {
  return typeof img === 'string' && /^\/eye\/[A-Za-z0-9._-]+\.(jpg|jpeg|png|webp)$/.test(img) ? img : null;
}

export function captionFor(mode, frame) {
  const head = { closed: 'Deep sleep · eyes closed', dream: 'Dreaming', outside: 'What he sees' }[mode] ?? '';
  if (!head) return '';
  const bits = [head];
  if (frame?.t) bits.push(String(frame.t).slice(0, 5));
  if (frame?.resting) bits.push('resting its eyes');
  const thought = frame?.thought ? `“${String(frame.thought).slice(0, 90)}”` : '';
  return bits.join(' · ') + (thought ? ` — ${thought}` : '');
}

export function createEyeView(container, options = {}) {
  const doc = options.document ?? globalThis.document;
  const schedule = options.setTimeout ?? globalThis.setTimeout.bind(globalThis);
  const cancel = options.clearTimeout ?? globalThis.clearTimeout.bind(globalThis);
  const make = (tag, className) => { const e = doc.createElement(tag); e.className = className; return e; };

  const root = make('section', 'eye-view');
  root.setAttribute('aria-label', 'What he sees');
  root.setAttribute('aria-live', 'polite');
  root.hidden = true;
  root.dataset.mode = 'off';
  const picture = make('img', 'eye-view-frame');
  picture.alt = '';
  const upper = make('div', 'eye-view-lid eye-view-lid-upper');
  const lower = make('div', 'eye-view-lid eye-view-lid-lower');
  const caption = make('p', 'eye-view-caption');
  const note = make('p', 'eye-view-note');
  note.textContent = 'AI-generated from the brain model’s state; not what a real person saw.';
  const shrink = make('button', 'eye-view-toggle');
  shrink.type = 'button';
  shrink.textContent = 'Minimise';
  shrink.setAttribute('aria-pressed', 'false');
  root.append(picture, upper, lower, caption, note, shrink);
  container.append(root);

  const state = { mode: 'off', since: null, privacy: false, frame: null, lidsClosed: false, shown: false,
    compact: false, timer: null };

  shrink.addEventListener('click', () => {
    state.compact = !state.compact;
    root.classList.toggle('eye-view-compact', state.compact);
    shrink.textContent = state.compact ? 'Expand' : 'Minimise';
    shrink.setAttribute('aria-pressed', String(state.compact));
  });

  function clearTimer() { if (state.timer !== null) { cancel(state.timer); state.timer = null; } }

  function showFrame() {
    const src = state.frame && frameMode(state.frame) === state.mode ? safeFrameSrc(state.frame.img) : null;
    state.shown = !!src && !state.privacy && state.mode !== 'off' && (state.mode === 'outside' || state.lidsClosed);
    if (state.shown) {
      if (picture.getAttribute('src') !== src) picture.setAttribute('src', src);
      picture.classList.add('eye-view-visible');
    } else picture.classList.remove('eye-view-visible');
    caption.textContent = state.privacy || state.mode === 'off' ? '' : captionFor(state.mode, state.shown ? state.frame : null);
  }

  function render() {
    const open = !state.privacy && state.mode !== 'off';
    root.hidden = !open;
    root.dataset.mode = open ? state.mode : 'off';
    const asleep = open && (state.mode === 'closed' || state.mode === 'dream');
    root.classList.toggle('eye-view-asleep', asleep);
    root.classList.toggle('eye-view-near-dark', open && state.mode === 'closed');
    upper.classList.toggle('eye-view-lid-closed', asleep);
    lower.classList.toggle('eye-view-lid-closed', asleep);
    if (!open) {                       // privacy or awake at home: nothing stays on screen
      clearTimer();
      state.lidsClosed = false;
      picture.removeAttribute('src');
    }
    showFrame();
  }

  const isAsleep = mode => mode === 'closed' || mode === 'dream';

  function closeLids() {               // the eyelids close first, then the dream (or near dark) fades in
    clearTimer();
    state.lidsClosed = false;
    state.timer = schedule(() => { state.timer = null; state.lidsClosed = true; showFrame(); }, LID_MS);
  }

  function setMode(mode, since = null) {
    if (!EYE_MODES.includes(mode)) mode = 'off';
    const was = state.mode;
    state.mode = mode;
    state.since = since;
    if (!isAsleep(mode)) { clearTimer(); state.lidsClosed = false; }
    else if (!isAsleep(was)) closeLids();
    if (mode !== was && frameMode(state.frame) !== mode) state.frame = null;
    render();                          // (privacy: render cancels the lids; they close again when it ends)
  }

  return {
    element: root,
    // Every websocket message can go through here: eye_state, eye frames and home states (privacy).
    accept(message) {
      if (!message || typeof message !== 'object') return;
      if (message.type === 'eye_state') setMode(message.mode, message.since ?? null);
      else if (message.type === 'eye') {
        if (state.mode === 'off' || frameMode(message) !== state.mode || !safeFrameSrc(message.img)) return;
        state.frame = message;
        showFrame();
      }
      if (message.home && typeof message.home === 'object') this.setPrivacy(!!message.home.privacy);
    },
    setPrivacy(active) {
      active = !!active;
      if (active === state.privacy) return;
      state.privacy = active;
      render();                        // privacy: hidden at once, no picture kept on screen
      if (!active && isAsleep(state.mode)) closeLids();
    },
    snapshot() {
      return { mode: state.mode, since: state.since, privacy: state.privacy, visible: !root.hidden,
        frameShown: state.shown, lidsClosed: state.lidsClosed, compact: state.compact,
        src: picture.getAttribute('src'), caption: caption.textContent };
    },
    dispose() { clearTimer(); root.remove?.(); },
  };
}
