from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(not shutil.which('node'),reason='Node.js required')
def test_actual_worker_receipt_and_owned_key_cancellation():
    subprocess.run([shutil.which('node'),str(ROOT/'tests/js/worker_input_receipts_check.cjs')],check=True,capture_output=True,timeout=10)
