// What the desk monitor and the computer panel say about his PC, from the shared
// /api/home state (`computer` from home_computer.Computer.view(), `browser` from
// screens.ScreensStatus.public()). Pure: no DOM, no fetch (tests/js/computer_screen_check.mjs).
// The monitor never goes black and never shows a made-up terminal: without guest
// output it shows the honest status (guest not installed, booting, worker exited,
// paused) and the fix named by the server.
export const CONNECTING = "Connecting to his Linux computer…";
const MONITOR_COLUMNS = 100;

// Serial output without carriage returns, CSI sequences and OSC titles.
export function stripTerminal(text) {
  return String(text ?? "")
    .replace(/\r/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "");
}

// Greedy word wrap for a fixed-width screen; a word longer than the width is cut.
export function wrapLines(text, columns = MONITOR_COLUMNS) {
  const out = [];
  for (const paragraph of String(text ?? "").split("\n")) {
    let line = "";
    for (const word of paragraph.split(/\s+/).filter(Boolean)) {
      if (!line) line = word;
      else if (line.length + 1 + word.length <= columns) line += " " + word;
      else { out.push(line); line = word; }
      while (line.length > columns) { out.push(line.slice(0, columns)); line = line.slice(columns); }
    }
    out.push(line);
  }
  return out;
}

// The one-line state of the computer: the server's summary when it has one.
export function computerSummary(computer) {
  const c = computer || {};
  if (typeof c.summary === "string" && c.summary) return c.summary;
  if (c.status === "private") return "Bathroom privacy is active";
  if (c.error) return String(c.error);
  return CONNECTING;
}

// Lines for the 3D monitor while he is at the computer (`maxLines` fit the screen).
// Real guest output wins; otherwise the honest placeholder with the status and the fix.
export function computerScreenLines(computer, maxLines = 29, columns = MONITOR_COLUMNS) {
  const c = computer || {};
  const output = stripTerminal(c.output).trimEnd();
  if (output) return output.split("\n").slice(-maxLines);
  const lines = [...wrapLines(computerSummary(c), columns), ""];
  if (c.hint) lines.push(...wrapLines(c.hint, columns), "");
  if (c.guest && c.guest.worker === "exited" && Number.isInteger(c.guest.restarts))
    lines.push(`guest worker restarts: ${c.guest.restarts}`, "");
  lines.push(`[${c.status || "offline"}]`);
  return lines.slice(0, maxLines);
}

// The <pre> of the Linux app in the computer panel: output (or the placeholder), then the state line.
export function computerPanelText(computer) {
  const c = computer || {};
  const output = stripTerminal(c.output).trimEnd();
  const state = `[${c.status || "offline"}] ${computerSummary(c)}`;
  return (output || CONNECTING) + "\n\n" + state + (c.hint ? "\n" + c.hint : "");
}

// Why the desk/phone browser shows nothing, from the screens status (BROWSE=0,
// playwright missing, restarting, idle), else the caller's wording.
export function browserUnavailableMessage(browser, fallback = "His browser has no public page to show right now.") {
  const b = browser || {};
  const why = typeof b.why === "string" && b.why ? b.why : "";
  switch (b.state) {
    case "off": return "His browser is off" + (why ? ": " + why : "") + ".";
    case "down": return "His browser is restarting" + (why ? " (" + why + ")" : "") + "…";
    case "idle": return "His browser is idle: it starts when he sits down at a screen.";
    case "starting": return "His browser is starting…";
    case "waiting": return why || fallback;
    default: return fallback;
  }
}
