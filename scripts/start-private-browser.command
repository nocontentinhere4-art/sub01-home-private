#!/bin/zsh
# Run the isolated browser service from the user's Terminal, on loopback only.
set -eu
sub01_local_root=${0:A:h:h}
sub01_local_python="$sub01_local_root/.venv/bin/python"
if [[ ! -x "$sub01_local_python" ]]; then
  sub01_local_python="$sub01_local_root/../sub01-house-live/.venv/bin/python"
fi
if [[ ! -x "$sub01_local_python" ]]; then
  print 'Create a local Python environment and install requirements-server.txt first.'
  exit 1
fi
export PLAYWRIGHT_BROWSERS_PATH=/private/tmp/sub01-house-chromium
export BROWSE_SERVICE_TOKEN=home-private-browser
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export ANTHROPIC_API_KEY='' REPLICATE_API_TOKEN='' OPENAI_API_KEY='' OPENROUTER_API_KEY=''
cd "$sub01_local_root"
exec "$sub01_local_python" browse_service.py --host 127.0.0.1 --port 8799
