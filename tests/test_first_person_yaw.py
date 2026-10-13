"""Bounded smooth first-person yaw: pure CPU reference and the proposed native patch."""
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import first_person_yaw as fy  # noqa: E402

DT = 1 / 60


def walk(current, target, seconds, dt=DT):
    yaws = [current]
    for _ in range(round(seconds / dt)):
        yaws.append(fy.step_yaw(yaws[-1], target, dt))
    return yaws


@pytest.mark.parametrize("angle,expected", [
    (0, 0), (180, 180), (-180, 180), (190, -170), (-190, 170), (540, 180), (-721, -1), (359.5, -0.5),
])
def test_wrap_degrees_range(angle, expected):
    assert fy.wrap_degrees(angle) == pytest.approx(expected)


@pytest.mark.parametrize("current,target,expected", [
    (170, -170, 20),     # across the seam, not -340
    (-170, 170, -20),
    (10, 350, -20),
    (0, 90, 90),
    (720, 0, 0),
])
def test_shortest_delta_takes_the_short_arc(current, target, expected):
    assert fy.shortest_delta(current, target) == pytest.approx(expected)


def test_turn_across_seam_goes_the_short_way_and_never_leaves_range():
    yaws = walk(170, -170, 2)
    assert yaws[1] > 170 or yaws[1] < -170  # first step moves toward the seam, not back through 0
    assert all(-180 < y <= 180 for y in yaws)
    assert all(abs(y) >= 169.999 for y in yaws)  # never sweeps through the long arc
    assert yaws[-1] == pytest.approx(-170)


@pytest.mark.parametrize("dt", [1 / 120, 1 / 60, 1 / 30, 0.1])
def test_angular_speed_is_bounded(dt):
    yaws = walk(0, 180, 3, dt)
    for a, b in zip(yaws, yaws[1:]):
        assert abs(fy.shortest_delta(a, b)) <= fy.MAX_RATE_DEG_S * dt + 1e-9


def test_large_turn_is_not_instantaneous_but_completes():
    yaws = walk(0, 179, 4)
    assert abs(yaws[1]) < 5                # the old code jumped 179 degrees in one tick
    assert yaws[round(1 / DT)] < 179       # still turning after a second
    assert yaws[-1] == pytest.approx(179)  # settled (snap) within four seconds


def test_never_overshoots_and_settles_exactly():
    for target in (5, -45, 90, -135, 180):
        yaws = walk(0, target, 4)
        assert all(abs(y) <= abs(target) + 1e-9 for y in yaws), target
        assert yaws[-1] == target


def test_frame_hitch_is_capped():
    assert abs(fy.step_yaw(0, 180, 5.0)) <= fy.MAX_RATE_DEG_S * fy.MAX_DT_S + 1e-9


@pytest.mark.parametrize("current,target,dt,expected", [
    (30, math.nan, DT, 30),        # unknown heading: keep looking where we look
    (30, math.inf, DT, 30),
    (math.nan, 45, DT, 45),        # first tick / corrupt state: adopt the heading
    (math.nan, math.nan, DT, 0),
    (30, 90, 0, 30),               # no time: no turn
    (30, 90, -DT, 30),
    (30, 90, math.nan, 30),
    (390, 90, 0, 30),              # still wrapped
])
def test_invalid_inputs_never_jump_or_nan(current, target, dt, expected):
    out = fy.step_yaw(current, target, dt)
    assert math.isfinite(out)
    assert out == pytest.approx(expected)


@pytest.mark.parametrize("kwargs", [{"max_rate": 0}, {"max_rate": -1}, {"max_rate": math.nan}, {"response": 0}, {"response": math.inf}])
def test_invalid_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        fy.step_yaw(0, 90, DT, **kwargs)


def test_movement_input_matches_native_formula():
    (ux, uy), scale = fy.movement_input((0, 0, 96), (30, 40, 96))
    assert (ux, uy) == pytest.approx((0.6, 0.8)) and scale == pytest.approx(50 / 45 if 50 / 45 < 1 else 1)
    assert fy.movement_input((0, 0), (3, 4))[1] == pytest.approx(0.15)  # clamp low
    assert fy.movement_input((0, 0), (0.5, 0)) is None                    # within 1cm: no input
    assert fy.heading_degrees((0, 0), (0, 10)) == pytest.approx(90)       # UE yaw: atan2(Y, X)


def test_physical_target_and_path_independent_of_view_yaw():
    here, target = (30, 255, 96), (30, -170, 396)  # stair_bottom -> stair_top
    reference = fy.movement_input(here, target)
    for view in (-180, -90, 0, 45, 179.9, math.nan):
        move, _ = fy.route_tick(here, target, view, DT)
        assert move == reference


def test_route_waypoint_turn_is_smooth():
    # Native route corner front -> stair_approach -> stair_bottom turns 90 degrees.
    view = fy.heading_degrees((130, 320), (30, 320))
    corner = fy.heading_degrees((30, 320), (30, 255))
    assert abs(fy.shortest_delta(view, corner)) == pytest.approx(90)
    _, nxt = fy.route_tick((30, 320), (30, 255), view, DT)
    assert abs(fy.shortest_delta(view, nxt)) <= fy.MAX_RATE_DEG_S * DT + 1e-9


# Proposed native patch (the native file itself stays untouched).

def test_native_sources_still_snap_until_patch_is_applied():
    for path in fy.NATIVE:
        assert "SetControlRotation(FRotator(-4,Delta.Rotation().Yaw,0))" in (ROOT / path).read_text(), path


def test_proposed_patch_is_up_to_date_and_applies():
    assert fy.main(["--check"]) == 0
    subprocess.run(["git", "apply", "--check", str(fy.PATCH)], cwd=ROOT, check=True)


def _patched(path):
    original, patched = {"__file__": str(ROOT / path)}, {"__file__": str(ROOT / path)}
    text = (ROOT / path).read_text()
    exec(compile(text, path, "exec"), original)
    exec(compile(fy.apply_edits(text, path), path, "exec"), patched)
    return original, patched


MOVE = "AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));"


@pytest.mark.parametrize("path,state,reset", [
    (fy.ROUTE, "RouteViewYaw", "RouteActive=true;RouteViewYawReady=false;"),
    (fy.LIVE, "LiveHomeViewYaw", "LiveHome=true;LiveHomeViewYawReady=false;"),
])
def test_patched_native_keeps_path_and_bounds_turn(path, state, reset):
    original, patched = _patched(path)
    methods, fields = patched["METHODS"], patched["FIELDS"]
    # Physical behaviour unchanged: same movement input, arrival test and node targets.
    assert methods.count(MOVE) == original["METHODS"].count(MOVE) == 1
    assert methods.count("Distance<12&&HeightError<20") == original["METHODS"].count("Distance<12&&HeightError<20")
    assert methods.count("Distance<12&&Height<20") == original["METHODS"].count("Distance<12&&Height<20")
    assert re.findall(r"FVector\([^)]*\)", methods) == re.findall(r"FVector\([^)]*\)", original["METHODS"])
    assert "SetActorLocation" not in methods and "Teleport" not in methods
    # Only the view yaw changed, eased with the reference constants.
    assert methods.count("SetControlRotation(") == 1
    assert f"SetControlRotation(FRotator(-4,{state},0))" in methods
    assert "Delta.Rotation().Yaw,0)" not in methods
    assert f"{fy.MAX_RATE_DEG_S:.4f}f*YawDt" in methods
    assert f"FMath::Exp(-{fy.RESPONSE_PER_S:g}.f*YawDt)" in methods
    assert "FMath::Min(GetWorld()->GetDeltaSeconds(),.1f)" in methods and fy.MAX_DT_S == 0.1
    assert "FindDeltaAngleDegrees" in methods and "NormalizeAxis" in methods
    assert f"{state}Ready" in fields and reset in methods
    # The rotation is still set before the unchanged movement input.
    assert methods.index(f"SetControlRotation(FRotator(-4,{state},0))") < methods.index(MOVE)
