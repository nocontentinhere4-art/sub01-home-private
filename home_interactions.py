"""Server-authoritative house interactions: doors, room lights, presence and privacy.

Pure logic with no I/O. HomeWorld feeds it the actor's walking state each tick
and exposes the result in view(); the page only animates what the server says.
Geometry matches the client modules (front_door_access.mjs,
bathroom_access.mjs, balcony_access.mjs and the bathroom bounds in home.js).

Operator modes live in HomeWorld.settings (`doors`, `lights`) and persist with
the other settings. Door/light runtime state persists through to_dict() but is
always re-derived from the actor's position, so a stale snapshot cannot hold a
bathroom door open or leave privacy off.

Door states (view()["doors"][name]["state"]):
  "open"    the leaf is open; anyone may pass.
  "closed"  the leaf is shut but not latched. The character opens it when his
            route passes through; a visitor may not enter through it until it
            is opened (operator mode "open" via /api/home/settings).
  "locked"  shut and latched: the front door while the house is away, the
            bathroom door while it is occupied (privacy). Operator "open" does
            not override an occupied bathroom.
Each door separates the house from a dead end (street, bathroom, balcony). A
visitor already on the dead-end side or in the doorway may always come back
into the house, whatever the state: nobody is ever shut in
(house_interactions.mjs, visitorDoorAllows).
Operator modes: "auto" (closed unless the character passes or is near),
"open" (held open), "closed" (closed except while the character passes).
"""

import math

# Same rectangle as `bathroomBounds` in home.js and the original server rule.
BATHROOM_BOUNDS = (-3.78, -0.85, 0.5, 2.7)  # x0, x1, z0, z1 on the upper floor
# Upper floor eye height is 4.65 and ground 1.65; 3 m separates the levels.
UPPER_FLOOR = 3
# The sliding bathroom leaf needs the actor this far past its plane before it
# can close behind him (leaf plane x=-0.85, body radius .16 plus clearance).
BATHROOM_CLOSE_X = -1.2
# Past the front door plane on the ground floor the actor is out of the house.
FRONT_DOOR_PLANE_Z = 3.9

DOORS = {
    # centre (x, z), approach radius, upper floor?, the walking edge through it
    "front": {"centre": (2.0, 3.9), "radius": 1.8, "upper": False, "edge": ("door", "outside")},
    "bathroom": {"centre": (-0.85, 1.35), "radius": 1.6, "upper": True, "edge": ("bath_door", "bathroom")},
    "balcony": {"centre": (-2.2, 3.85), "radius": 1.7, "upper": True, "edge": ("balcony_door", "balcony")},
}
DOOR_NAMES = tuple(DOORS)
DOOR_MODES = ("auto", "open", "closed")
DOOR_STATES = ("open", "closed", "locked")
LIGHT_ROOMS = ("living", "kitchen", "bedroom", "bathroom")
LIGHT_MODES = ("auto", "on", "off")
PRESENCE = ("home", "leaving", "away", "returning")
# Seconds a door stays open after the actor has cleared it, and a light stays
# on after he has left its room (real seconds of the home tick).
CLOSE_DELAY = 1.2
LIGHT_LINGER = 90.0
# Life places out on the streets (life.py PLACES); they keep the 3D actor out
# until the life walk is back at the door (door_out, just outside it).
OUTDOOR_PLACES = frozenset({
    "street_home", "street_bakery", "bakery_door", "bakery_in",
    "counter", "street_park", "park_gate", "bench",
})


def finite_position(position):
    return (isinstance(position, (list, tuple)) and len(position) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in position))


def in_bathroom(position):
    if not finite_position(position):
        return False
    x, y, z = position
    x0, x1, z0, z1 = BATHROOM_BOUNDS
    return y > UPPER_FLOOR and x0 < x < x1 and z0 < z < z1


def outside_house(position):
    return finite_position(position) and position[1] < UPPER_FLOOR and position[2] > FRONT_DOOR_PLANE_Z


def privacy(position, node, path, bathroom_locked=False):
    """The single bathroom privacy decision.

    True while the actor is inside the bathroom rectangle, while he is on the
    doorway edge into or out of it, and while the bathroom door is locked.
    Anything that can show a device, screen or the actor reads this one flag.
    """
    path = list(path or [])
    return bool(
        in_bathroom(position)
        or node == "bathroom"
        or (node == "bath_door" and path[:1] == ["bathroom"])
        or bathroom_locked
    )


def room_of(position):
    """Light room for a position: living, kitchen, bedroom, bathroom, or None outside."""
    if not finite_position(position):
        return None
    x, y, z = position
    if y > UPPER_FLOOR:
        return "bathroom" if in_bathroom(position) else "bedroom"
    if z > FRONT_DOOR_PLANE_Z:
        return None
    # Same zoning as the page: the desk/office side counts as living space.
    return "kitchen" if x <= 0.7 and z < -1 else "living"


def presence(position, path, target):
    if not outside_house(position):
        return "home"
    if path:
        return "leaving" if target == "outside" else "returning"
    return "away"


def daylight(now):
    """The page's homeLighting daylight (lighting.mjs) for a server timestamp."""
    if now is None or not isinstance(now, (int, float)) or not math.isfinite(now):
        return None
    hour = ((now / 3600 + 9) % 24 + 24) % 24
    elevation = math.sin((hour - 6) / 12 * math.pi)
    t = max(0.0, min(1.0, (elevation + 0.08) / 0.28))
    return t * t * (3 - 2 * t)


def is_dark(now):
    level = daylight(now)
    # Unknown time behaves like the original always-available lamps.
    return True if level is None else level < 0.5


def normalise_modes(raw, names, modes):
    raw = raw if isinstance(raw, dict) else {}
    return {n: raw[n] if raw.get(n) in modes else modes[0] for n in names}


def validate_modes(value, names, modes, label):
    """Validate a partial operator patch; return it or raise ValueError."""
    if not isinstance(value, dict) or not value:
        raise ValueError(f"Expected an object of {label} modes")
    for key, mode in value.items():
        if key not in names or mode not in modes:
            raise ValueError(f"Unknown {label} or mode: use {'/'.join(names)} with {'/'.join(modes)}")
    return dict(value)


def near(door, position):
    if not finite_position(position):
        return False
    d = DOORS[door]
    if (position[1] > UPPER_FLOOR) != d["upper"]:
        return False
    return math.hypot(position[0] - d["centre"][0], position[2] - d["centre"][1]) < d["radius"]


def crossing(door, node, path):
    """True while the actor walks the edge that passes through this door."""
    if not path:
        return False
    return {node, path[0]} == set(DOORS[door]["edge"])


class HouseInteractions:
    def __init__(self, state=None):
        s = state if isinstance(state, dict) else {}
        doors = s.get("doors") if isinstance(s.get("doors"), dict) else {}
        self.doors = {}
        for name in DOOR_NAMES:
            d = doors.get(name) if isinstance(doors.get(name), dict) else {}
            self.doors[name] = {
                "open": d.get("open") is True,
                "locked": d.get("locked") is True and name in ("front", "bathroom"),
            }
        self.clear = {name: 0.0 for name in DOOR_NAMES}
        lights = s.get("lights") if isinstance(s.get("lights"), dict) else {}
        self.recent = {
            room: float(lights[room]) if isinstance(lights.get(room), (int, float))
            and not isinstance(lights.get(room), bool) and math.isfinite(lights[room])
            and 0 <= lights[room] <= LIGHT_LINGER else 0.0
            for room in LIGHT_ROOMS
        }
        self.lights = {room: False for room in LIGHT_ROOMS}
        self.dark = True
        self.presence = "home"

    # ---- doors -------------------------------------------------------------
    def _door_target(self, name, actor, mode):
        """(open, locked, immediate) wanted for one door this tick."""
        pos, node, path = actor["position"], actor["node"], actor["path"]
        passing = crossing(name, node, path)
        if name == "bathroom":
            occupied = in_bathroom(pos) or node == "bathroom"
            leaving = node == "bathroom" and bool(path)
            entering = node == "bath_door" and path[:1] == ["bathroom"]
            if leaving:
                return True, False, True        # unlock and open to step out
            if entering and pos[0] > BATHROOM_CLOSE_X:
                return True, False, True        # open while stepping in
            if occupied or entering:
                return False, True, True        # inside: closed and locked
        if passing:
            return True, False, True
        if mode == "open":
            return True, False, True
        locked = name == "front" and actor["presence"] == "away"
        if mode == "closed":
            return False, locked, True
        if near(name, pos):
            return True, False, True
        return False, locked, False

    def _update_doors(self, dt, actor, modes):
        for name in DOOR_NAMES:
            want_open, locked, immediate = self._door_target(name, actor, modes[name])
            door = self.doors[name]
            if want_open:
                door["open"], door["locked"], self.clear[name] = True, False, 0.0
                continue
            if door["open"] and not immediate:
                self.clear[name] += max(0.0, dt)
                if self.clear[name] < CLOSE_DELAY:
                    door["locked"] = False   # an open leaf is never locked
                    continue
            door["open"], door["locked"] = False, locked
            self.clear[name] = 0.0

    # ---- lights ------------------------------------------------------------
    def _update_lights(self, dt, actor, lamp, modes, now):
        self.dark = is_dark(now)
        here = room_of(actor["position"])
        asleep = actor["activity"] == "sleep" and actor["node"] == "bed" and actor["seated"] >= 1
        for room in LIGHT_ROOMS:
            if room == here and actor["presence"] == "home":
                self.recent[room] = LIGHT_LINGER
            else:
                self.recent[room] = max(0.0, self.recent[room] - max(0.0, dt))
            auto = self.recent[room] > 0 and (room == "bathroom" or self.dark)
            if room == "bedroom" and asleep:
                auto = False
            mode = modes[room]
            on = True if mode == "on" else False if mode == "off" else auto
            self.lights[room] = bool(lamp) and on

    def update(self, dt, actor, settings, now=None):
        """actor: position, node, path, target, activity, seated."""
        actor = dict(actor)
        actor["path"] = list(actor.get("path") or [])
        self.presence = presence(actor["position"], actor["path"], actor.get("target"))
        actor["presence"] = self.presence
        self._update_doors(dt, actor, normalise_modes(settings.get("doors"), DOOR_NAMES, DOOR_MODES))
        self._update_lights(dt, actor, settings.get("lamp", True) is not False,
                            normalise_modes(settings.get("lights"), LIGHT_ROOMS, LIGHT_MODES), now)

    def door_state(self, name):
        door = self.doors[name]
        return "open" if door["open"] else "locked" if door["locked"] else "closed"

    def view(self, settings):
        door_modes = normalise_modes(settings.get("doors"), DOOR_NAMES, DOOR_MODES)
        light_modes = normalise_modes(settings.get("lights"), LIGHT_ROOMS, LIGHT_MODES)
        return {
            "doors": {n: {**self.doors[n], "state": self.door_state(n), "mode": door_modes[n]}
                      for n in DOOR_NAMES},
            "lights": {
                "master": settings.get("lamp", True) is not False,
                "dark": self.dark,
                "rooms": {r: {"on": self.lights[r], "mode": light_modes[r]} for r in LIGHT_ROOMS},
            },
            "presence": self.presence,
        }

    def to_dict(self):
        return {
            "doors": {n: dict(self.doors[n]) for n in DOOR_NAMES},
            "lights": {r: round(self.recent[r], 3) for r in LIGHT_ROOMS},
        }
