// Operator controls for the server house state: doors (Open / Auto / Closed)
// and room lights (On / Auto / Off). Self-contained: build once into a
// container, then call update(homeState) on every state; the DOM is reused.
// Edits go through the page's authenticated mutate('settings', ...) helper.

export const DOOR_LABELS = Object.freeze({front: 'Front door', bathroom: 'Bathroom door', balcony: 'Balcony door'});
export const ROOM_LABELS = Object.freeze({living: 'Living room', kitchen: 'Kitchen', bedroom: 'Bedroom', bathroom: 'Bathroom'});
const DOOR_MODES = [['open', 'Open'], ['auto', 'Auto'], ['closed', 'Closed']];
const LIGHT_MODES = [['on', 'On'], ['auto', 'Auto'], ['off', 'Off']];
const LOCK_REASON = {bathroom: 'Occupied', front: 'Away'};

export function doorStatusText(name, door) {
  if (!door || typeof door.open !== 'boolean') return 'Unknown';
  const state = door.state || (door.open ? 'open' : door.locked ? 'locked' : 'closed');
  if (state === 'locked') return 'Locked · ' + (LOCK_REASON[name] || 'Locked');
  return state === 'open' ? 'Open' : 'Closed';
}

export function lightStatusText(room, lights) {
  const info = lights?.rooms?.[room];
  if (!info || typeof info.on !== 'boolean') return 'Unknown';
  if (lights.master === false) return 'Off · master lamp off';
  return info.on ? 'On' : 'Off';
}

// A mutate for this panel that reports refusals as {status, reason} instead
// of only false, so a 403 can disable the controls for the refused key.
export function operatorMutate(fetchImpl, operatorToken) {
  return async (action, data) => {
    try {
      const response = await fetchImpl('/api/home/' + action, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Admin-Token': operatorToken() || ''},
        body: JSON.stringify(data),
      });
      if (!response.ok) {
        let reason = '';
        try { reason = (await response.text()).slice(0, 200); } catch {}
        return {status: response.status, reason};
      }
      return await response.json();
    } catch {
      return {status: 0, reason: 'The house server is unreachable'};
    }
  };
}

export function createHouseControlsPanel(container, options = {}) {
  const doc = options.document || globalThis.document;
  const mutate = options.mutate;
  const operatorKey = options.operatorKey || (() => '');
  let state = null, deniedKey = null, message = '';
  const pending = new Set();

  const el = (tag, text, className) => {
    const node = doc.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const root = el('section', '', 'house-controls');
  root.setAttribute('role', 'group');
  root.setAttribute('aria-label', 'House controls');
  const note = el('p', '', 'muted');
  note.setAttribute('aria-live', 'polite');
  const rows = [];

  function row(kind, name, label, modes) {
    const line = el('div', '', 'house-control');
    line.setAttribute('role', 'group');
    line.setAttribute('aria-label', label);
    const title = el('span', label, 'house-control-name');
    const status = el('span', '', 'house-control-status');
    status.setAttribute('aria-live', 'polite');
    const buttons = {};
    line.append(title, status);
    for (const [mode, text] of modes) {
      const b = el('button', text);
      b.type = 'button';
      b.dataset.mode = mode;
      b.setAttribute('aria-pressed', 'false');
      b.setAttribute('aria-label', `${label}: ${text}`);
      b.addEventListener('click', () => choose(entry, mode));
      buttons[mode] = b;
      line.append(b);
    }
    const entry = {kind, name, label, status, buttons, line};
    rows.push(entry);
    return line;
  }

  root.append(el('h3', 'Doors'));
  for (const [name, label] of Object.entries(DOOR_LABELS)) root.append(row('doors', name, label, DOOR_MODES));
  root.append(el('h3', 'Lights'));
  for (const [room, label] of Object.entries(ROOM_LABELS)) root.append(row('lights', room, label, LIGHT_MODES));
  root.append(note);
  container.append(root);

  const isOperator = () => {
    const key = operatorKey() || '';
    return !!key && key !== deniedKey;
  };
  const privateBathroom = entry => entry.kind === 'doors' && entry.name === 'bathroom' && !!state?.privacy;

  function blockedReason(entry) {
    if (!isOperator()) return 'Operator access is required to change the house.';
    if (privateBathroom(entry)) return 'The bathroom is occupied; its door cannot be changed during privacy.';
    if (pending.has(entry)) return 'Saving…';
    return '';
  }

  function render() {
    for (const entry of rows) {
      const server = entry.kind === 'doors' ? state?.doors?.[entry.name] : state?.lights?.rooms?.[entry.name];
      const mode = server?.mode ?? state?.settings?.[entry.kind]?.[entry.name] ?? null;
      entry.status.textContent = entry.kind === 'doors'
        ? doorStatusText(entry.name, server) : lightStatusText(entry.name, state?.lights);
      const reason = blockedReason(entry);
      entry.line.dataset.locked = String(entry.kind === 'doors' && !!server?.locked);
      for (const [m, b] of Object.entries(entry.buttons)) {
        b.setAttribute('aria-pressed', String(m === mode));
        b.disabled = !!reason || !state;
        b.title = reason;
      }
    }
    note.textContent = message || (!isOperator() ? 'Operator access is required to change the house.' : '');
  }

  async function choose(entry, mode) {
    const reason = blockedReason(entry);
    if (reason) { message = reason; render(); return; }
    pending.add(entry);
    message = '';
    render();
    const key = operatorKey() || '';
    let result = false;
    try {
      result = await mutate('settings', {[entry.kind]: {[entry.name]: mode}});
    } catch { result = false; }
    pending.delete(entry);
    if (result?.status === 403) {
      deniedKey = key;   // this key was refused: disable until it changes
      message = 'Operator access is required to change the house.';
    } else if (!result || result.status) {
      message = `${entry.label} was not changed${result?.reason ? ': ' + result.reason : '.'}`;
    } else {
      const saved = result[entry.kind]?.[entry.name];
      if (saved && state) {
        // Show the saved mode now; the next home state confirms the rest.
        state = {...state, settings: {...state.settings, [entry.kind]: result[entry.kind]}};
        if (entry.kind === 'doors' && state.doors?.[entry.name])
          state = {...state, doors: {...state.doors, [entry.name]: {...state.doors[entry.name], mode: saved}}};
        if (entry.kind === 'lights' && state.lights?.rooms?.[entry.name])
          state = {...state, lights: {...state.lights, rooms: {...state.lights.rooms,
            [entry.name]: {...state.lights.rooms[entry.name], mode: saved}}}};
      }
      message = entry.kind === 'doors' && entry.name === 'bathroom' && mode === 'open' && state?.doors?.bathroom?.locked
        ? 'Saved. The bathroom door stays locked while it is occupied.' : `${entry.label}: ${mode}.`;
    }
    render();
  }

  render();
  return {
    element: root,
    update(next) { state = next || null; render(); },
    refreshOperator() { if ((operatorKey() || '') !== deniedKey) message = ''; render(); },
    destroy() { root.remove?.(); rows.length = 0; },
  };
}
