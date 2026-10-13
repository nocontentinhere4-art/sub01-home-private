"""Bounded smooth first-person yaw for the native route (pure CPU, no Unreal).

The native route test (tools/unreal_native_route.py) and the live home runtime
(tools/unreal_live_home_runtime.py) snap the control rotation to each segment's
heading every tick, so the first-person view jumps
by up to 180 degrees at a waypoint. This module is the reference for the
proposed fix: the camera yaw approaches the heading along the shortest arc,
eased like the browser's FirstPersonLook (web/house/first_person_look.mjs) and
never faster than a fixed angular speed. Only the view turns smoothly: the
movement input (direction and scale toward the same target) is unchanged.

    python tools/first_person_yaw.py            # write the proposed native patch
    python tools/first_person_yaw.py --check    # patch up to date?

The patch is a proposal (docs/proposed/native-route-smooth-yaw.patch); the native
files stay untouched until the runtime gates pass and its owner applies it.
"""

import argparse
import difflib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "docs/proposed/native-route-smooth-yaw.patch"

# Same feel as the browser camera: 1 - exp(-4 dt) easing, capped at 1.8 rad/s.
RESPONSE_PER_S = 4.0
MAX_RATE_DEG_S = math.degrees(1.8)
MAX_DT_S = 0.1  # a frame hitch never turns the view by more than 0.1 s worth
SNAP_DEG = 0.05


def wrap_degrees(angle):
    """Angle in (-180, 180]."""
    wrapped = math.fmod(angle, 360.0)
    if wrapped <= -180.0:
        wrapped += 360.0
    elif wrapped > 180.0:
        wrapped -= 360.0
    return wrapped


def shortest_delta(current, target):
    """Signed turn from current to target along the shortest arc, in (-180, 180]."""
    return wrap_degrees(target - current)


def step_yaw(current, target, dt, max_rate=MAX_RATE_DEG_S, response=RESPONSE_PER_S):
    """Next view yaw (degrees): eased toward target, |turn| <= max_rate * dt.

    Invalid input never produces a jump or a NaN: a non-finite target keeps the
    current yaw, a non-finite current (first tick) adopts the target, and a
    non-finite or non-positive dt does not turn.
    """
    if not (math.isfinite(max_rate) and max_rate > 0 and math.isfinite(response) and response > 0):
        raise ValueError("max_rate and response must be finite and positive")
    if not math.isfinite(target):
        return wrap_degrees(current) if math.isfinite(current) else 0.0
    if not math.isfinite(current):
        return wrap_degrees(target)
    if not math.isfinite(dt) or dt <= 0:
        return wrap_degrees(current)
    dt = min(dt, MAX_DT_S)
    delta = shortest_delta(current, target)
    if abs(delta) <= SNAP_DEG:
        return wrap_degrees(target)
    limit = max_rate * dt
    turn = max(-limit, min(limit, delta * (1 - math.exp(-response * dt))))
    return wrap_degrees(current + turn)


def movement_input(here, target):
    """The native route's movement input toward target: (unit xy direction, scale) or None.

    Mirrors `AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f))`;
    it reads only positions, so the smoothed view cannot change the walked path.
    """
    dx, dy = target[0] - here[0], target[1] - here[1]
    distance = math.hypot(dx, dy)
    if distance <= 1:
        return None
    return (dx / distance, dy / distance), max(0.15, min(1.0, distance / 45.0))


def heading_degrees(here, target):
    """UE yaw of the horizontal direction here -> target (FVector::Rotation().Yaw)."""
    return math.degrees(math.atan2(target[1] - here[1], target[0] - here[0]))


def route_tick(here, target, view_yaw, dt):
    """One route tick: (movement input, next view yaw). Movement ignores view_yaw."""
    move = movement_input(here, target)
    if move is None:
        return None, view_yaw
    return move, step_yaw(view_yaw, heading_degrees(here, target), dt)


def smooth_yaw_cpp(state, ready, indent):
    """Native statements that ease `state` toward the segment heading (same math as step_yaw)."""
    i = indent
    return (
        f"{i}// View turns along the shortest arc, eased (1-exp(-4dt)) and capped at 1.8 rad/s\n"
        f"{i}// (tools/first_person_yaw.py); the movement input is unchanged.\n"
        f"{i}const float YawDt=FMath::Min(GetWorld()->GetDeltaSeconds(),.1f),TargetYaw=Delta.Rotation().Yaw;\n"
        f"{i}if(!{ready}||!FMath::IsFinite({state})){{{state}=Controller->GetControlRotation().Yaw;{ready}=true;}}\n"
        f"{i}if(YawDt>0&&FMath::IsFinite(TargetYaw)){{\n"
        f"{i} const float Turn=FMath::FindDeltaAngleDegrees({state},TargetYaw),Limit={MAX_RATE_DEG_S:.4f}f*YawDt;\n"
        f"{i} {state}=FRotator::NormalizeAxis(FMath::Abs(Turn)<={SNAP_DEG:g}f?TargetYaw:{state}+FMath::Clamp(Turn*(1-FMath::Exp(-{RESPONSE_PER_S:g}.f*YawDt)),-Limit,Limit));\n"
        f"{i}}}\n"
        f"{i}Controller->SetControlRotation(FRotator(-4,{state},0));\n"
    ).replace("0.05f", ".05f")


ROUTE = "tools/unreal_native_route.py"
LIVE = "tools/unreal_live_home_runtime.py"
NATIVE = (ROUTE, LIVE)
# (file, name, exact unique anchor, replacement)
EDITS = [
    (ROUTE, "route field",
     " float RouteBestDistance=BIG_NUMBER,RouteCaptureDelay=45;\n",
     " float RouteBestDistance=BIG_NUMBER,RouteCaptureDelay=45;\n"
     " float RouteViewYaw=0;bool RouteViewYawReady=false;\n"),
    (ROUTE, "route reset on begin",
     " RouteActive=true;\n",
     " RouteActive=true;RouteViewYawReady=false;\n"),
    (ROUTE, "route smooth yaw",
     "  Controller->SetControlRotation(FRotator(-4,Delta.Rotation().Yaw,0));\n",
     smooth_yaw_cpp("RouteViewYaw", "RouteViewYawReady", "  ")),
    (LIVE, "live field",
     " float LiveHomeBest=BIG_NUMBER;\n",
     " float LiveHomeBest=BIG_NUMBER,LiveHomeViewYaw=0;bool LiveHomeViewYawReady=false;\n"),
    (LIVE, "live reset on bind",
     " LiveHome=true;LiveHomeProgressAt=FPlatformTime::Seconds();",
     " LiveHome=true;LiveHomeViewYawReady=false;LiveHomeProgressAt=FPlatformTime::Seconds();"),
    (LIVE, "live smooth yaw",
     " if(Controller&&Distance>1){Controller->SetControlRotation(FRotator(-4,Delta.Rotation().Yaw,0));AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));}\n",
     " if(Controller&&Distance>1){\n" + smooth_yaw_cpp("LiveHomeViewYaw", "LiveHomeViewYawReady", "  ")
     + "  AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));\n }\n"),
]


def apply_edits(text, path):
    for file, name, anchor, replacement in EDITS:
        if file != path:
            continue
        if text.count(anchor) != 1:
            raise ValueError(f"anchor {name!r} found {text.count(anchor)} times in {path}")
        text = text.replace(anchor, replacement)
    return text


def build_patch():
    out = []
    for path in NATIVE:
        original = (ROOT / path).read_text()
        out += difflib.unified_diff(original.splitlines(True), apply_edits(original, path).splitlines(True),
                                    f"a/{path}", f"b/{path}")
    return "".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    patch = build_patch()
    if args.check:
        ok = PATCH.exists() and PATCH.read_text() == patch
        print("up to date" if ok else "stale: run python tools/first_person_yaw.py")
        return 0 if ok else 1
    PATCH.write_text(patch)
    print(f"wrote {PATCH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
