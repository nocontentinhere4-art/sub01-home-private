"""CPU-only ordering invariants for the native HTTP input dispatcher."""
from pathlib import Path
import shutil
import subprocess
import pytest

COMPILER = shutil.which('clang++') or shutil.which('g++')

@pytest.mark.skipif(not COMPILER, reason='A C++ compiler is required for the native queue unit check')
@pytest.mark.parametrize('filename', ['native_guest_input_queue.cpp', 'native_guest_frame_layout.cpp'])
def test_native_dispatch_and_unchanged_guest_pixels(tmp_path, filename):
    source = Path(__file__).with_name(filename)
    executable = tmp_path / 'native-queue-check'
    subprocess.run([COMPILER, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(executable)], check=True, capture_output=True)
    subprocess.run([str(executable)], check=True, capture_output=True)
