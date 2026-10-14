"""Authenticated native display on the one allocated A40, without software GPU."""
import re
import os
import ctypes
import subprocess
from pathlib import Path


def allocated_a40_bus_id(query_output):
    rows = [line.strip().split(",") for line in query_output.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][0].strip() != "NVIDIA A40":
        raise ValueError("Expected exactly one allocated NVIDIA A40")
    match = re.fullmatch(r"([0-9a-fA-F]{4,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])", rows[0][1].strip())
    if not match or int(match[1], 16) != 0:
        raise ValueError("Unsupported allocated GPU PCI domain")
    bus, device, function = int(match[2], 16), int(match[3], 16), int(match[4])
    if device > 31:
        raise ValueError("Invalid allocated PCI device")
    return f"PCI:{bus}:{device}:{function}"


def nvidia_xorg_config(bus_id):
    if not re.fullmatch(r"PCI:[0-9]{1,3}:[0-9]{1,2}:[0-7]", bus_id):
        raise ValueError("Invalid validated PCI selector")
    # Use the driver's display selection: this target exposes a virtual head,
    # and its actual 570.195.03 log rejects UseDisplayDevice "None".
    return f'''Section "ServerFlags"
    Option "AutoAddDevices" "False"
    Option "AutoAddGPU" "False"
EndSection
Section "Files"
    ModulePath "/usr/lib/x86_64-linux-gnu/nvidia/xorg"
    ModulePath "/usr/lib/xorg/modules"
EndSection
Section "Device"
    Identifier "AllocatedA40"
    Driver "nvidia"
    BusID "{bus_id}"
    Option "AllowEmptyInitialConfiguration" "True"
    Option "ProbeAllGpus" "False"
EndSection
Section "Screen"
    Identifier "PrivateNativeScreen"
    Device "AllocatedA40"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Virtual 1280 720
    EndSubSection
EndSection
Section "ServerLayout"
    Identifier "PrivateNativeLayout"
    Screen 0 "PrivateNativeScreen"
EndSection
'''


def xorg_command(config_path, auth_path, log_path):
    return ["/usr/lib/xorg/Xorg", ":99", "-config", str(Path(config_path)),
            "-auth", str(Path(auth_path)), "-nolisten", "tcp", "-noreset",
            "-logfile", str(Path(log_path))]


def owned_xorg_pid(config_path, auth_path):
    """Reuse only the existing authenticated display created by this launcher."""
    matches = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
            args = [x.decode() for x in args if x]
        except (OSError, UnicodeError):
            continue
        expected = {"-config": str(config_path), "-auth": str(auth_path), "-nolisten": "tcp"}
        if args and args[0] == "/usr/lib/xorg/Xorg" and ":99" in args and "-ac" not in args:
            if all(key in args and args.index(key)+1 < len(args) and args[args.index(key)+1] == value for key, value in expected.items()):
                matches.append(int(proc.name))
    if len(matches) != 1:
        raise ValueError("Exactly one owned authenticated NVIDIA Xorg display required")
    return matches[0]


def resize_owned_game_window(display_environment):
    """Resize the real SDL game window; never crop or scale captured evidence."""
    tree = subprocess.check_output(["xwininfo", "-root", "-tree"], env=display_environment, text=True, timeout=5)
    ids = re.findall(r'(0x[0-9a-f]+) "Sub01HomeLab \(', tree)
    if len(ids) != 1:
        raise ValueError("Exactly one real native game window required")
    old_display, old_auth = os.environ.get("DISPLAY"), os.environ.get("XAUTHORITY")
    os.environ["DISPLAY"] = display_environment["DISPLAY"]
    os.environ["XAUTHORITY"] = display_environment["XAUTHORITY"]
    connection = None
    lib = ctypes.CDLL("libX11.so.6")
    try:
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]; lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XMoveResizeWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]; lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        connection = lib.XOpenDisplay(display_environment["DISPLAY"].encode())
        if not connection:
            raise ValueError("Authenticated native display unavailable")
        lib.XMoveResizeWindow(connection, int(ids[0], 16), 0, 0, 1280, 720)
        lib.XSync(connection, 0)
    finally:
        if connection:
            lib.XCloseDisplay(connection)
        for key, old in (("DISPLAY", old_display), ("XAUTHORITY", old_auth)):
            if old is None: os.environ.pop(key, None)
            else: os.environ[key] = old
    geometry = subprocess.check_output(["xwininfo", "-id", ids[0]], env=display_environment, text=True, timeout=5)
    for field, value in (("Width", "1280"), ("Height", "720"),
                         ("Absolute upper-left X", "0"), ("Absolute upper-left Y", "0")):
        if not re.search(re.escape(field) + r":\s*" + value + r"\s*$", geometry, re.MULTILINE):
            raise ValueError("Native window did not adopt the requested physical geometry")
    return ids[0]
