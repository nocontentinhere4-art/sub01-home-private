"""Run the private home only on localhost, with paid integrations disabled."""
import asyncio
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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
options = parser.parse_args()
if not 1 <= options.port <= 65535:
    parser.error('Port must be between 1 and 65535')
if not 1000 <= options.neurons <= 1000000:
    parser.error('Neurons must be between 1000 and 1000000')
os.environ.update(SUB01_SPIKING_LIVE='0' if options.no_spiking else '1',
                  SUB01_SPIKING_LIVE_NEURONS=str(options.neurons),
                  SUB01_SPIKING_LIVE_TIMEOUT_S='5', SUB01_DAY_LIVE='0',
                  SUB01_POD_SECRET='', RUNPOD_API_KEY='')
from live_server import main, build_parser

asyncio.run(main(build_parser().parse_args([
    '--host', '127.0.0.1', '--port', str(options.port), '--data-dir',
    options.data_dir, '--time-scale', str(options.time_scale), '--start', options.start,
])))
