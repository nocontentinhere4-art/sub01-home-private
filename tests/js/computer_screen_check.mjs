import assert from "node:assert/strict";
import { stripTerminal, wrapLines, computerSummary, computerScreenLines, computerPanelText,
  browserUnavailableMessage, CONNECTING } from "../../web/house/computer_screen.mjs";

// 1. Real guest output wins and is cleaned of ANSI; only the last lines fit the monitor.
const serial = "\x1b]0;title\x07~# \x1b[32muname -a\x1b[0m\r\nLinux localhost 5.6.15 i686\r\n~# ";
assert.equal(stripTerminal(serial), "~# uname -a\nLinux localhost 5.6.15 i686\n~# ");
const ready = { status: "ready", ready: true, paused: false, output: serial, summary: "Buildroot Linux / x86 · running", hint: "" };
assert.deepEqual(computerScreenLines(ready), ["~# uname -a", "Linux localhost 5.6.15 i686", "~#"]);
const many = { ...ready, output: Array.from({ length: 50 }, (_, i) => "line " + i).join("\n") };
const shown = computerScreenLines(many, 29);
assert.equal(shown.length, 29); assert.equal(shown[0], "line 21"); assert.equal(shown.at(-1), "line 49");
assert.match(computerPanelText(ready), /^~# uname -a\nLinux localhost 5\.6\.15 i686\n~#\n\n\[ready\] Buildroot Linux \/ x86 · running$/);

// 2. No guest output: the honest placeholder (never black, never a made-up prompt).
const missing = { status: "unavailable", ready: false, output: "",
  error: "Linux guest not installed: 5 of 5 pinned files missing (libv86.cjs ...)",
  summary: "Linux guest not installed: 5 of 5 pinned files missing (libv86.cjs ...)",
  hint: "The computer is off until the guest files are there: run `python computer/bootstrap.py` once (downloads the pinned v86 BIOS and Buildroot Linux image); the server retries by itself",
  guest: { assets: null, worker: null, restarts: 0, exit_code: null } };
const lines = computerScreenLines(missing);
assert.equal(lines[0], missing.summary);
assert.ok(lines.some(l => l.includes("python computer/bootstrap.py")), "the fix is on the monitor");
assert.equal(lines.at(-1), "[unavailable]");
assert.ok(lines.every(l => l.length <= 100), "monitor lines are wrapped to its width");
assert.ok(!lines.some(l => /~#/.test(l)), "no fake shell prompt");
assert.match(computerPanelText(missing), /^Connecting to his Linux computer…\n\n\[unavailable\] Linux guest not installed/);
assert.ok(computerPanelText(missing).endsWith(missing.hint));

// 3. A dead worker says so, with its restart count; booting and paused states are plain.
const exited = { status: "offline", output: "", summary: "Linux guest worker exited with code 1; stderr: Error: Cannot find module",
  hint: "It restarts by itself (see the server log for the worker's last lines)", guest: { worker: "exited", restarts: 2, exit_code: 1 } };
assert.ok(computerScreenLines(exited).includes("guest worker restarts: 2"));
assert.deepEqual(computerScreenLines({ status: "booting", output: "", summary: "Linux is booting…" }), ["Linux is booting…", "", "[booting]"]);
assert.equal(computerSummary({ status: "ready", paused: true, summary: "Buildroot Linux / x86 · paused while he is away from the desk" }),
  "Buildroot Linux / x86 · paused while he is away from the desk");

// 4. Before the first /api/home answer, during privacy, and with an old server without `summary`.
assert.deepEqual(computerScreenLines({}), [CONNECTING, "", "[offline]"]);
assert.deepEqual(computerScreenLines(undefined), [CONNECTING, "", "[offline]"]);
assert.equal(computerSummary({ status: "private", output: "" }), "Bathroom privacy is active");
assert.equal(computerSummary({ status: "unavailable", error: "Node.js is not installed" }), "Node.js is not installed");

// 5. Word wrap: long words are cut, paragraphs kept, nothing lost.
assert.deepEqual(wrapLines("aaa bbb ccc", 7), ["aaa bbb", "ccc"]);
assert.deepEqual(wrapLines("x".repeat(12), 5), ["xxxxx", "xxxxx", "xx"]);
assert.deepEqual(wrapLines("one\ntwo three", 9), ["one", "two three"]);

// 6. The browser placeholder names the real reason from /api/home `browser` (screens status).
assert.equal(browserUnavailableMessage({ state: "off", why: "the browser is turned off (BROWSE=0)" }),
  "His browser is off: the browser is turned off (BROWSE=0).");
assert.equal(browserUnavailableMessage({ state: "off", why: "playwright is not installed: no browser" }),
  "His browser is off: playwright is not installed: no browser.");
assert.equal(browserUnavailableMessage({ state: "down", why: "connection refused" }), "His browser is restarting (connection refused)…");
assert.equal(browserUnavailableMessage({ state: "idle", why: "he is not at a screen" }), "His browser is idle: it starts when he sits down at a screen.");
assert.equal(browserUnavailableMessage({ state: "up" }), "His browser has no public page to show right now.");
assert.equal(browserUnavailableMessage(null, "custom"), "custom");
assert.equal(browserUnavailableMessage({ state: "waiting", why: "Looking for an accessible page; no current page to show" }),
  "Looking for an accessible page; no current page to show");
console.log("PASS: monitor/panel text is honest without guest output, keeps real output, wraps, and names the browser's state");
