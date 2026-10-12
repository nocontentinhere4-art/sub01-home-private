// One server-owned x86 VM. No host filesystem, network adapter, or subprocess bridge in the guest.
const { V86 } = require("./libv86.cjs"),
  fs = require("fs"),
  path = require("path"),
  readline = require("readline");
const snapshot = process.env.SUB01_VM_STATE;
const assets = process.env.SUB01_VM_ASSETS || __dirname;
let serial = "",
  ready = false,
  activeSave = null,
  shuttingDown = false,
  restored = false;
const send = (o) => process.stdout.write(JSON.stringify(o) + "\n");
const vm = new V86({
  wasm_path: path.join(__dirname, "v86.wasm"),
  memory_size: 64 * 1024 * 1024,
  vga_memory_size: 2 * 1024 * 1024,
  bios: { url: path.join(assets, "seabios.bin") },
  vga_bios: { url: path.join(assets, "vgabios.bin") },
  bzimage: { url: path.join(assets, "buildroot-bzimage.bin") },
  cmdline: "console=ttyS0 tsc=reliable",
  filesystem: {},
  autostart: false,
});
vm.add_listener("serial0-output-byte", (byte) => {
  serial = (serial + String.fromCharCode(byte)).slice(-12000);
  if (/~[%#] $/.test(serial)) ready = true;
});
vm.add_listener("emulator-loaded", async () => {
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
  send({ type: "terminal", ready, output: serial, paused: !vm.is_running() });
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
    } else if (m.type === "pause") {
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
