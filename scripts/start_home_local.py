"""Run the private home only on localhost, with paid integrations disabled."""
import asyncio
import argparse
import os
import sys
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _var in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(_var, '1')            # one BLAS thread: idle pools spin and burn cores (spiking/threads.py)
os.environ.update(
    HOME_ENABLED='1', HOME_ENTRYPOINT='1', SUB01_SPIKING_LIVE='0',
    BROWSE='1', BROWSE_SERVICE_URL='', MIND='0', CLIPS='0',
    ANTHROPIC_API_KEY='', REPLICATE_API_TOKEN='', OPENROUTER_API_KEY='',
    OPENAI_API_KEY='', SUB01_ADMIN_TOKEN='house-local-test',
)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=8798)
parser.add_argument('--start', default='15:00')
parser.add_argument('--time-scale', type=float, default=1)
parser.add_argument('--data-dir', default=str(ROOT / 'data'))
parser.add_argument('--neurons', type=int, default=500000)
parser.add_argument('--no-spiking', action='store_true', help='Lightweight visual QA only')
parser.add_argument('--minecraft', action='store_true', help='Enable the prepared private Minecraft console; requires owner EULA acceptance')
parser.add_argument('--browser-service', help='Optional isolated browser service, loopback only')
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

try:
    asyncio.run(main(build_parser().parse_args([
        '--host', '127.0.0.1', '--port', str(options.port), '--data-dir',
        options.data_dir, '--time-scale', str(options.time_scale), '--start', options.start,
    ])))
except asyncio.CancelledError:
    pass  # Intentional SIGTERM; main has saved state and closed its children.
