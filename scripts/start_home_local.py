"""Run the private home only on localhost, with paid integrations disabled except the eye.

The eye (what he sees: dreams while he sleeps, the street while he is outside) may use the owner's Replicate token
from the private environment or the git-ignored .env, within the existing daily eye cap ($1.00), and only through
SUB01_EYE_REPLICATE_TOKEN (scripts/home_local_env.py). Awake at home it spends nothing. --no-eye turns it off."""
import asyncio
import argparse
import os
import sys
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.home_local_env import eye_env
_eye_wanted = '--no-eye' not in sys.argv[1:]
_eye_updates, _eye_on = eye_env(os.environ, ROOT / '.env', enabled=_eye_wanted)   # read before the keys are blanked
os.environ.update(
    HOME_ENABLED='1', HOME_ENTRYPOINT='1', SUB01_SPIKING_LIVE='0',
    BROWSE='1', BROWSE_SERVICE_URL='', MIND='0', CLIPS='0',
    ANTHROPIC_API_KEY='', REPLICATE_API_TOKEN='', OPENROUTER_API_KEY='',
    OPENAI_API_KEY='', SUB01_ADMIN_TOKEN='house-local-test',
)
os.environ.update(_eye_updates)   # every paid key stays blank; the eye alone gets its own token and the capped budget
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=8798)
parser.add_argument('--start', default='15:00')
parser.add_argument('--time-scale', type=float, default=1)
parser.add_argument('--data-dir', default=str(ROOT / 'data'))
parser.add_argument('--neurons', type=int, default=500000)
parser.add_argument('--no-spiking', action='store_true', help='Lightweight visual QA only')
parser.add_argument('--minecraft', action='store_true', help='Enable the prepared private Minecraft console; requires owner EULA acceptance')
parser.add_argument('--browser-service', help='Optional isolated browser service, loopback only')
parser.add_argument('--no-eye', action='store_true', help='Keep the eye off (no Replicate images at all)')
options = parser.parse_args()
if not 1 <= options.port <= 65535:
    parser.error('Port must be between 1 and 65535')
if not 1000 <= options.neurons <= 1000000:
    parser.error('Neurons must be between 1000 and 1000000')
if options.browser_service:
    parsed = urlparse(options.browser_service)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        parser.error('The browser service must be a plain loopback HTTP URL')
    os.environ.update(BROWSE_SERVICE_URL=options.browser_service,
                      BROWSE_SERVICE_TOKEN='home-private-browser')
os.environ.update(SUB01_SPIKING_LIVE='0' if options.no_spiking else '1',
                  SUB01_MINECRAFT='1' if options.minecraft else '0',
                  SUB01_SPIKING_LIVE_NEURONS=str(options.neurons),
                  SUB01_SPIKING_LIVE_TIMEOUT_S='5', SUB01_DAY_LIVE='0',
                  SUB01_POD_SECRET='', RUNPOD_API_KEY='')
from scripts.local_port import wait_for_local_port
if wait_for_local_port(options.port):
    print("Previous local listener closed; starting the private home.", flush=True)
from live_server import main, build_parser

server_args = ['--host', '127.0.0.1', '--port', str(options.port), '--data-dir',
               options.data_dir, '--time-scale', str(options.time_scale), '--start', options.start]
if _eye_on:
    server_args.append('--eye')
    print("Eye on: Replicate images only while he sleeps or is outside, capped at "
          f"{os.environ['SUB01_EYE_USD_PER_DAY']} USD/day.", flush=True)
else:
    print("Eye off: " + ("--no-eye." if options.no_eye else "no Replicate token in the private environment."), flush=True)

try:
    asyncio.run(main(build_parser().parse_args(server_args)))
except asyncio.CancelledError:
    pass  # Intentional SIGTERM; main has saved state and closed its children.
