"""Headless pictures of the gait model and the first-person body (docs/design/natural-motion/2026-10-23).

Serves the repository root on a free loopback port (python -m http.server), drives the two review pages in this
directory with Playwright's Chromium on SwiftShader (software WebGL: slow, so the viewports are small and the timeouts
long), and saves PNGs. Usage, from the repository root:

    python docs/design/natural-motion/tools/shots.py <out dir> [fp|gait|all]

Needs the playwright package and a Chromium at CHROME (below) or $PW_CHROME. No network: every file is local.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
CHROME = os.environ.get("PW_CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
TOOLS = "/docs/design/natural-motion/tools"
# the first-person pictures: name -> query (the walk at 1.2 m/s; pitch in radians, down is negative)
FP = {
    "fp_walk_down_t03": "mode=walking&speed=1.2&pitch=-1.1&t=0.3",
    "fp_walk_down_t06": "mode=walking&speed=1.2&pitch=-1.1&t=0.6",
    "fp_walk_down_t09": "mode=walking&speed=1.2&pitch=-1.1&t=0.9",
    "fp_walk_steep_t06": "mode=walking&speed=1.2&pitch=-1.4&t=0.6",
    "fp_walk_level_t06": "mode=walking&speed=1.2&pitch=-0.15&t=0.6",
    "fp_walk_half_t06": "mode=walking&speed=1.2&pitch=-0.6&t=0.6",
    "fp_idle_down": "mode=idle&pitch=-1.1&t=0.3",
}
GAIT = {"gait_0.4ms": "speed=0.4&every=0.35", "gait_0.8ms": "speed=0.8&every=0.25", "gait_1.2ms": "speed=1.2&every=0.2"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/design/natural-motion/2026-10-23")
    which = sys.argv[2] if len(sys.argv) > 2 else "all"
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "-d", str(ROOT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.8)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, args=[
                "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
            jobs = []
            if which in ("fp", "all"):
                jobs += [(n, f"{TOOLS}/fp_review.html?w=480&h=360&{qs}", 480, 360) for n, qs in FP.items()]
            if which in ("gait", "all"):
                jobs += [(n, f"{TOOLS}/gait_review.html?n=5&cw=180&ch=240&{qs}", 900, 480) for n, qs in GAIT.items()]
            for name, url, w, h in jobs:
                page = browser.new_page(viewport={"width": w, "height": h})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                t0 = time.time()
                page.goto(f"http://127.0.0.1:{port}{url}")
                page.wait_for_function("window.ready === true || window.ready === 'failed'", timeout=600000)
                state = page.evaluate("window.ready")
                info = page.evaluate("JSON.stringify(window.info || (window.statuses || []).slice(-1)[0] || null)")
                page.screenshot(path=str(out / f"{name}.png"))
                print(f"{name}: {state} in {time.time() - t0:.0f} s  {info}  {' | '.join(errors)[:300]}")
                page.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
