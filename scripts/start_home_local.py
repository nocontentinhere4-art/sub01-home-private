"""Run the private home only on localhost, with paid integrations disabled."""
import asyncio
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
from live_server import main, build_parser

asyncio.run(main(build_parser().parse_args([
    '--host', '127.0.0.1', '--port', '8798', '--data-dir',
    str(ROOT / 'data'), '--time-scale', '1', '--start', '15:00',
])))
