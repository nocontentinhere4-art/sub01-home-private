// One server-owned x86 VM. No host filesystem, network adapter, or subprocess bridge in the guest.
const { V86 } = require("./libv86.cjs"),
  fs = require("fs"),
  path = require("path"),
  readline = require("readline");
const { attachFramebuffer } = require('./vga_framebuffer.cjs');
const { guestKeyboard } = require('./guest_keyboard.cjs');
const { inputReceipts } = require('./input_receipts.cjs');
const { guestMouse, mouseDiagnostics } = require('./guest_mouse.cjs');
// v86's pixel container only; no canvas or browser is introduced.
globalThis.ImageData ??= class ImageData { constructor(data, width, height) { this.data=data; this.width=width; this.height=height; } };
const snapshot = process.env.SUB01_VM_STATE;
const assets = process.env.SUB01_VM_ASSETS || __dirname;
let serial = "",
  ready = false,
  activeSave = null,
  shuttingDown = false,
  restored = false;
const send = (o) => process.stdout.write(JSON.stringify(o) + "\n");
const receipts = inputReceipts(send);
const vm = new V86({
  wasm_path: path.join(__dirname, "v86.wasm"),
  memory_size: (process.env.SUB01_VM_CDROM ? 128 : 64) * 1024 * 1024,
  vga_memory_size: 2 * 1024 * 1024,
  bios: { url: path.join(assets, "seabios.bin") },
  vga_bios: { url: path.join(assets, "vgabios.bin") },
  ...(process.env.SUB01_VM_CDROM ? {
    cdrom: { url: process.env.SUB01_VM_CDROM },
  } : {
    bzimage: { url: path.join(assets, "buildroot-bzimage.bin") },
    cmdline: "console=ttyS0 tsc=reliable",
  }),
  filesystem: {},
  autostart: false,
});
const keyboard = guestKeyboard(codes => vm.keyboard_send_scancodes(codes));
let framebuffer = null;
let lastFrameRevision = null, lastDisplayKind = '';
const mouse = guestMouse(vm, () => framebuffer?.capture());
vm.add_listener("serial0-output-byte", (byte) => {
  serial = (serial + String.fromCharCode(byte)).slice(-12000);
  if (/~[%#] $/.test(serial)) ready = true;
});
vm.add_listener("emulator-loaded", async () => {
  framebuffer = attachFramebuffer(vm.screen_adapter, () => vm.v86?.cpu?.devices?.vga);
  try {
    if (snapshot && fs.existsSync(snapshot)) {
      await vm.restore_state(fs.readFileSync(snapshot));
      ready = true;
      restored = true;
      send({ type: "restored" });
    }
  } catch (e) {
    send({
      type: "error",
      message: "Saved VM could not be restored; booting fresh",
    });
  }
  vm.run();
  if (restored) {
    serial = "[Linux restored from its saved state]\r\n";
    vm.serial0_send("\n");
  }
});
setInterval(() => {
  const vgaText = process.env.SUB01_VM_CDROM && vm.screen_adapter?.get_text_screen ? vm.screen_adapter.get_text_screen().join("\n").trimEnd() : '';
  send({ type: "terminal", ready, output: vgaText || serial, paused: !vm.is_running(), instruction_counter: vm.get_instruction_counter?.() ?? null, mouse_state: mouseDiagnostics(vm) });
  const frame = framebuffer ? framebuffer.capture() : {kind: "serial", available: false, reason: "Emulator VGA is initializing"};
  if (frame.available) ready = true;
  if (process.env.SUB01_VM_CDROM && framebuffer) {
    frame.keyboard_available = true;
    if (!frame.available) frame.kind = 'vga-text';
    ready = true;
  }
  if (frame.kind !== lastDisplayKind || (frame.available && frame.revision !== lastFrameRevision)) {
    const { png, ...display } = frame;
    send({ type: 'display', display, ...(png ? { png: png.toString('base64') } : {}) });
    lastDisplayKind = frame.kind; lastFrameRevision = frame.revision;
  }
}, 1000);
async function save(final = false) {
  if (activeSave) {
    await activeSave;
    if (!final) return;
  }
  if (!snapshot || !ready) return;
  // A final save follows any older periodic save: the guest may have changed
  // since that capture began. Keep atomic replacement and bounded disk writes.
  const saving = (async () => {
    try {
      const state = Buffer.from(await vm.save_state());
      fs.mkdirSync(path.dirname(snapshot), { recursive: true });
      fs.writeFileSync(snapshot + ".tmp", state);
      fs.renameSync(snapshot + ".tmp", snapshot);
    } catch (e) {
      send({ type: "error", message: "VM snapshot failed" });
    }
  })();
  activeSave = saving;
  try {
    await saving;
  } finally {
    if (activeSave === saving) activeSave = null;
  }
}
async function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  receipts.cancelAll();keyboard.cancel();
  await save(true);
  vm.destroy();
  process.exit(0);
}
setInterval(save, 60000);
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  try {
    const m = JSON.parse(line);
    if (shuttingDown) return;
    if (
      m.type === "input" &&
      typeof m.text === "string" &&
      m.text.length <= 2000
    ) {
      vm.run();
      vm.serial0_send(m.text);
    } else if (m.type === "vga-keyboard" && Array.isArray(m.scancodes) && m.scancodes.length >= 1 && m.scancodes.length <= 16 && m.scancodes.every(code => Number.isInteger(code) && code >= 0 && code <= 255)) {
      const receipt=receipts.begin(m);if(!receipt)return;
      try {if(!receipt.valid()){receipt.finish(false,'Rejected');return;}
       vm.run();const ok=await keyboard.enqueue(m.scancodes,receipt.valid,receipt.wait);
       receipt.finish(ok,'GuestKeyboardInjected');
      }catch(e){receipt.finish(false,'Rejected');throw e;}
    } else if (m.type === "vga-mouse" && [m.dx, m.dy, m.wheel].every(value => Number.isFinite(value) && Math.abs(value) <= 100) && Array.isArray(m.buttons) && m.buttons.length === 3 && m.buttons.every(value => typeof value === 'boolean')) {
      const receipt=receipts.begin(m);if(!receipt)return;
      try {if(!receipt.valid()){receipt.finish(false,'Rejected');return;}
       mouse(m);receipt.finish(true,'GuestMouseInjected');
      }catch(e){receipt.finish(false,'Rejected');throw e;}
    } else if(m.type==='graphical-input-cancel') {
      receipts.cancel(m);
    } else if (m.type === "pause") {
      receipts.cancelAll();keyboard.cancel();
      vm.bus?.send("mouse-click", [0, 0, 0]);
      await vm.stop();
    } else if (m.type === "resume") {
      vm.run();
    } else if (m.type === "save") {
      await save();
    } else if (m.type === "shutdown") {
      await shutdown();
    }
  } catch (e) {
    send({ type: "error", message: "Invalid VM command" });
  }
});
for (const signal of ["SIGTERM", "SIGINT"])
  process.on(signal, shutdown);
