import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import unreal_seat_detour as detour


def module(tmp_path, move=detour.MOVE_OLD):
    (tmp_path / 'Sub01HomeLab.h').write_text('struct A{\n' + detour.HEADER_ANCHOR + '};\n')
    (tmp_path / 'Sub01HomeLab.cpp').write_text('#include "x"\n' + detour.FUNCTION_ANCHOR + ' a();\n' + move + '}\n')
    return tmp_path


def test_install_adds_detour_once(tmp_path):
    path = module(tmp_path)
    assert detour.install(path)
    cpp = (path / 'Sub01HomeLab.cpp').read_text()
    assert cpp.index('Sub01SeatDetourRoute(UWorld') < cpp.index(detour.FUNCTION_ANCHOR)
    assert detour.MOVE_NEW in cpp and detour.MOVE_OLD not in cpp
    assert detour.HEADER_ADD in (path / 'Sub01HomeLab.h').read_text()
    assert detour.install(path) is False


def test_refuses_a_different_seat_source(tmp_path):
    with pytest.raises(RuntimeError):
        detour.install(module(tmp_path, move=' else {}\n'))
