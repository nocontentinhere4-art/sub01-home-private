"""One inhabited home, stepped by the live brain server, never by viewers.

The home maps existing life activities onto collision-free 3D waypoints. Rooms,
Pong, notes and the phone persist with the same server state as the character.
Physiology and consciousness are not inferred from this simulation.
"""

import heapq
import math
import random
from console_requests import valid_choice
import home_interactions as hi
from home_native_feedback import NativeFeedback

# xyz = walking-eye positions in the rendered house, metres.
NODES = {
    "desk": (2, 1.65, -0.75),
    "aisle": (1.3, 1.65, -0.75),
    "back": (1.3, 1.65, -2.2),
    "kitchen_gate": (-0.5, 1.65, -2.2),
    "kitchen": (-1.8, 1.65, -1.8),
    # Stand in the front gap between the west-facing sofa and coffee table.
    "sofa": (-2.55, 1.65, 0.1),
    "sofa_front_approach": (-2.55, 1.65, 1.6),
    "sofa_rear_approach": (-2.55, 1.65, -1.6),
    "lounge_gate": (-0.45, 1.65, 3.2),
    "front": (1.3, 1.65, 3.2),
    "stair_approach": (0.3, 1.65, 3.2),
    "stair_bottom": (0.3, 1.65, 2.55),
    "stair_top": (0.3, 4.65, -1.7),
    "landing": (0.3, 4.65, -2.1),
    "loft": (-0.5, 4.65, -2.1),
    "bed": (-1.2, 4.65, -2.9),
    "bath_aisle": (-0.5, 4.65, -0.2),
    "bath_door": (-0.5, 4.65, 1.35),
    "bathroom": (-1.5, 4.65, 1.35),
    "balcony_gate": (-0.5, 4.65, 3.2),
    "balcony_door": (-2.2, 4.65, 3.2),
    "balcony": (-2.2, 4.65, 4.4),
    "door": (2, 1.65, 3.2),
    "outside": (2, 1.65, 7.25),
}
EDGES = [
    ("desk", "aisle"),
    ("aisle", "back"),
    ("back", "kitchen_gate"),
    ("kitchen_gate", "kitchen"),
    ("stair_approach", "lounge_gate"),
    ("lounge_gate", "sofa_front_approach"),
    ("sofa_front_approach", "sofa"),
    ("sofa", "sofa_rear_approach"),
    ("sofa_rear_approach", "kitchen_gate"),
    ("aisle", "front"),
    ("front", "stair_approach"),
    ("stair_approach", "stair_bottom"),
    ("stair_bottom", "stair_top"),
    ("stair_top", "landing"),
    ("landing", "loft"),
    ("loft", "bed"),
    ("bed", "bath_aisle"),
    ("loft", "bath_aisle"),
    ("bath_aisle", "bath_door"),
    ("bath_door", "bathroom"),
    ("bath_door", "balcony_gate"),
    ("balcony_gate", "balcony_door"),
    ("balcony_door", "balcony"),
    ("front", "door"),
    ("door", "outside"),
]
DESTINATIONS = {
    "sleep": "bed",
    "phone": "bed",
    "listen_music": "bed",
    "order_food": "bed",
    "eat": "kitchen",
    "use_bathroom": "bathroom",
    "play_console": "sofa",
    "watch_tv": "sofa",
    "window": "balcony",
    "park": "outside",
    "buy_bread": "outside",
    "buy_konbini": "outside",
    "get_delivery": "door",
    "research": "desk",
    "chart": "desk",
    "chat": "desk",
    "watch_video": "desk",
    "play_chess": "desk",
    "use_computer": "desk",
}
LOOKS = {
    "desk": (2, 1.16, -3.3),
    "sofa": (-3.85, 1.65, 0.1),
    "kitchen": (-2.2, 1.2, -3.5),
    "bed": (0, 4.1, 0),
    "bathroom": (-3.5, 4, 1.1),
    "balcony": (10, 6, 24),
    "outside": (10, 6, 24),
    "door": (2, 1.4, 4.2),
}


def route(a, b):
    graph = {k: [] for k in NODES}
    for x, y in EDGES:
        cost = math.dist(NODES[x], NODES[y])
        graph[x].append((y, cost))
        graph[y].append((x, cost))
    queue = [(0, a, [])]
    seen = set()
    while queue:
        cost, node, path = heapq.heappop(queue)
        if node == b:
            return path + [node]
        if node in seen:
            continue
        seen.add(node)
        for nxt, d in graph[node]:
            heapq.heappush(queue, (cost + d, nxt, path + [node]))
    raise ValueError("unreachable home destination")


class Pong:
    """The left paddle uses the brain's live motor/attention signals and a learned response gain.

    This is a sensor/motor controller, not proof that the brain understands Pong.
    The right paddle can be challenged by viewers. Without input it is a simple opponent.
    """

    def __init__(self, state=None):
        s = state if isinstance(state, dict) else {}
        self.left = self.right = 0.5
        self.x = self.y = 0.5
        self.vx = 0.28
        self.vy = 0.17
        self.score = list(s.get("score", [0, 0]))
        self.gain = float(s.get("gain", 0.55))
        self.rally = 0
        self.clock = 0
        self.user_until = 0
        self.user_direction = 0
        self.opponent_target = .5
        self.opponent_next = 0
        self.matches = int(s.get("matches", 0))
        self.reward = 0
        self.last_result = ""
        self.active = False

    def input(self, direction):
        self.user_direction = max(-1, min(1, float(direction)))
        self.user_until = self.clock + 0.35

    def update(self, dt, rel, active):
        self.active = active
        if not active:
            return
        self.clock += dt
        self.reward = 0
        attention = max(0.2, min(2, rel.get("attention", 1)))
        motor = max(0.2, min(2, rel.get("somatomotor", rel.get("motor", 1))))
        target = self.y + self.vy * 0.16 * attention
        error = target - self.left
        self.left = max(
            0.105,
            min(
                0.895,
                self.left
                + max(
                    -0.7 * dt,
                    min(0.7 * dt, error * self.gain * motor * attention * dt * 5),
                ),
            ),
        )
        if self.clock >= self.opponent_next:
            # A finite reaction interval makes the opponent beatable, rather than a perfect tracker.
            self.opponent_target = self.y
            self.opponent_next = self.clock + .38
        direction = (
            self.user_direction
            if self.clock < self.user_until
            else max(-1, min(1, (self.opponent_target - self.right) * 7))
        )
        self.right = max(0.105, min(0.895, self.right + direction * 0.42 * dt))
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y < 0.025:
            self.y = 0.025
            self.vy = abs(self.vy)
        if self.y > 0.975:
            self.y = 0.975
            self.vy = -abs(self.vy)
        for px, paddle, sign in ((0.045, self.left, 1), (0.955, self.right, -1)):
            if (
                self.vx * sign < 0
                and (self.x <= px if sign == 1 else self.x >= px)
                and abs(self.y - paddle) < 0.115
            ):
                self.x = px
                self.vx = sign * min(0.7, abs(self.vx) * 1.035)
                self.vy = (self.y - paddle) * 3.4
                if abs(self.vy) < 0.22:
                    self.vy = 0.24 * (1 if self.rally % 2 else -1)
                self.rally += 1
                if sign == 1:
                    self.reward = 0.02
                    self.gain = min(1.4, self.gain + 0.002)
        if self.x < 0 or self.x > 1:
            won = self.x > 1
            self.score[0 if won else 1] += 1
            self.matches += 1
            self.reward = 0.12 if won else -0.08
            self.last_result = "won a point" if won else "missed the ball"
            self.gain = min(1.4, max(0.2, self.gain + (0.008 if won else 0.02)))
            self.x = self.y = 0.5
            self.vx = 0.28 if won else -0.28
            self.vy = 0.16 * (1 if self.matches % 2 else -1)
            self.rally = 0

    def view(self):
        return {
            "ball": [round(self.x, 4), round(self.y, 4)],
            "paddles": [round(self.left, 4), round(self.right, 4)],
            "score": self.score,
            "rally": self.rally,
            "active": self.active,
            "gain": round(self.gain, 3),
            "matches": self.matches,
            "last_result": self.last_result,
        }


class HomeWorld:
    def __init__(self, state=None):
        s = state if isinstance(state, dict) else {}
        self.console_game = s.get("console_game", "pong")
        self.last_console_choice = valid_choice(s.get('last_console_choice'))
        self.pending_console_game = None
        if self.console_game not in ("pong", "chess", "minecraft"):
            self.console_game = "pong"
        self.settings = {"lamp": True, "curtain": False, **s.get("settings", {})}
        for key in ("cabinets", "lowerCabinets"):
            doors = self.settings.get(key)
            self.settings[key] = (list(doors) if isinstance(doors, list)
                                  and len(doors) == 4
                                  and all(isinstance(v, bool) for v in doors)
                                  else [False] * 4)
        # Additive operator modes (auto/open/closed doors, auto/on/off lights).
        self.settings["doors"] = hi.normalise_modes(
            self.settings.get("doors"), hi.DOOR_NAMES, hi.DOOR_MODES)
        self.settings["lights"] = hi.normalise_modes(
            self.settings.get("lights"), hi.LIGHT_ROOMS, hi.LIGHT_MODES)
        self.node = s.get("node", "desk") if s.get("node") in NODES else "desk"
        self.position = list(NODES[self.node])
        self.target = self.node
        self.path = []
        self.activity = "research"
        self.look = list(LOOKS.get(self.node, LOOKS["desk"]))
        self.speed = 0
        self.seated = max(0, min(1, float(s.get("seated", 0))))
        self.time = float(s.get("time", 0))
        self.sequence = int(s.get("sequence", 0))
        self.native_feedback = NativeFeedback()
        if (
            s.get("path")
            and all(n in NODES for n in s["path"])
            and s.get("target") in NODES
            and len(s.get("position", [])) == 3
            and all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in s["position"]
            )
        ):
            self.position = list(s["position"])
            self.path = list(s["path"])
            self.target = s["target"]
            self.activity = s.get("activity", "research")
        if s.get("navigation_version") != 2 and self.path and (
            self.node == "sofa" or "sofa" in self.path
        ):
            # The old route crossed the sofa back. Resume that legacy journey
            # from its last safe waypoint, then take the new front approach.
            # A fully seated sofa snapshot keeps the same visible seat pose.
            self.position = list(NODES[self.node])
            self.path = route(self.node, self.target)[1:]
        self.bladder = max(0, min(1, float(s.get("bladder", 0.1))))
        self.last_bathroom = s.get("last_bathroom", 0)
        self.pong = Pong(s.get("pong"))
        self.notes = list(s.get("notes", []))[-100:]
        self.memories = list(s.get("memories", []))[-100:]
        self.last_activity = ""
        self.last_game_matches = self.pong.matches
        self.memories = self.memories[-100:]
        self.phone = {
            "app": s.get("phone_app", "home"),
            "battery": int(s.get("battery", 100)),
        }
        self.phone_elapsed = 0
        self.now = None
        self.interactions = hi.HouseInteractions(s.get("interactions"))
        self.interactions.update(0, self._actor(), self.settings, None)

    def _actor(self):
        return {"position": self.position, "node": self.node, "path": self.path,
                "target": self.target, "activity": self.activity, "seated": self.seated}

    def privacy(self):
        """The one authoritative bathroom privacy decision (view, devices, API)."""
        return hi.privacy(self.position, self.node, self.path,
                          self.interactions.doors["bathroom"]["locked"])

    def desired(self, activity):
        return DESTINATIONS.get(activity, "desk")

    def activity_ready(self, activity=None):
        """Finish both the walking route and the real seated camera transition."""
        expected = self.activity if activity is None else activity
        return (self.activity == expected and not self.path
                and self.node == self.desired(expected)
                and (self.node not in ("desk", "sofa", "bed") or self.seated == 1)
                and self.native_feedback.ready(sequence=self.sequence, activity=expected, target=self.target)
                and (self.native_feedback.epoch is None or not self.privacy()))

    def update(self, dt, sim_dt, life, rel, now=None):
        self.time += dt
        if now is not None:
            self.now = now
        activity = life.get("activity", "research")
        pending = valid_choice(life.get('console_wish'))
        self.pending_console_game = pending[0] if pending else None
        choice = valid_choice(life.get('console_choice'))
        if activity == 'play_console' and choice and choice != self.last_console_choice:
            self.console_game = choice[0]
            self.last_console_choice = choice
        target = self.desired(activity)
        if (target != "outside" and life.get("place") in hi.OUTDOOR_PLACES
                and (self.target == "outside" or self.node == "outside")):
            # Still out on the real streets: stay outside the front door
            # until the life walk is back at it, then return through it.
            target = "outside"
        self.bladder = min(1, self.bladder + max(0, sim_dt) / 18000)
        if target != self.target:
            # Finish current edge before replanning; no teleports through furniture.
            origin = self.path[0] if self.path else self.node
            self.path = ([origin] if self.path else []) + route(origin, target)[1:]
            self.target = target
            self.sequence += 1
        self.activity = activity
        if self.path and self.seated > 0:
            # Finish getting up at a human pace before the first walking edge.
            self.seated = max(0, self.seated - dt * 0.55)
            self.speed = 0
        elif self.path:
            n = self.path[0]
            end = NODES[n]
            distance = math.dist(self.position, end)
            arrival_speed = 0.08
            if len(self.path) > 1:
                following = NODES[self.path[1]]
                incoming = [b - a for a, b in zip(self.position, end)]
                outgoing = [b - a for a, b in zip(end, following)]
                length = math.hypot(*incoming) * math.hypot(*outgoing)
                cosine = sum(a * b for a, b in zip(incoming, outgoing)) / length if length > 1e-8 else 1
                arrival_speed = 0.4 + 0.85 * max(0, min(1, cosine))
            # Brake ahead of a corner or seat, instead of stopping abruptly
            # at the waypoint. Straight segments preserve walking momentum.
            desired_speed = min(1.25, math.sqrt(arrival_speed ** 2 + 2 * 1.4 * distance))
            if self.speed < desired_speed:
                self.speed = min(desired_speed, self.speed + dt * 1.15)
            else:
                self.speed = max(desired_speed, self.speed - dt * 1.8)
            step = self.speed * dt
            if distance <= step:
                self.position = list(end)
                self.node = n
                self.path.pop(0)
            else:
                self.position = [
                    p + (q - p) * step / distance for p, q in zip(self.position, end)
                ]
            self.look = [end[0], self.position[1], end[2]]
        else:
            self.speed = max(0, self.speed - dt * 1.8)
            self.look = list(LOOKS.get(self.node, LOOKS["desk"]))
            self.seated = (
                min(1, self.seated + dt * 0.65)
                if self.node in ("desk", "sofa", "bed")
                else 0
            )
            if self.node == "bathroom":
                self.bladder = max(0, self.bladder - dt * 0.06)
                self.last_bathroom = self.time
            if activity != self.last_activity and self.activity_ready(activity):
                self.memories.append(
                    {
                        "at": round(self.time, 1),
                        "activity": activity,
                        "place": self.node,
                    }
                )
                self.memories = self.memories[-100:]
                self.last_activity = activity
        self.pong.update(
            min(dt, 0.05), rel, activity == "play_console" and self.activity_ready(activity) and self.console_game == "pong"
        )
        if self.pong.matches != self.last_game_matches:
            self.memories.append(
                {
                    "at": round(self.time, 1),
                    "activity": "play_console",
                    "what": self.pong.last_result,
                    "score": list(self.pong.score),
                }
            )
            self.last_game_matches = self.pong.matches
            self.memories = self.memories[-100:]
        self.phone_elapsed += dt
        if self.phone_elapsed >= 60:
            self.phone_elapsed = 0
            self.phone["battery"] = max(
                1, min(100, self.phone["battery"] + (-1 if activity == "phone" else 2))
            )
        screen = life.get("screen") or {}
        self.phone["app"] = (
            screen.get("kind", "browser") if activity == "phone" else self.phone["app"]
        )
        self.interactions.update(dt, self._actor(), self.settings, self.now)

    def settings_view(self):
        view = dict(self.settings)
        for key in ("cabinets", "lowerCabinets"):
            view[key] = list(view[key])
        for key in ("doors", "lights"):
            view[key] = dict(view[key])
        return view

    def add_note(self, text):
        text = str(text).strip()[:2000]
        if not text:
            return False
        self.notes.append(
            {"id": self.sequence, "at": round(self.time, 1), "text": text}
        )
        self.sequence += 1
        self.notes = self.notes[-100:]
        return True

    def view(self, compact=False):
        p = list(self.position)
        if self.node == "desk":
            p[1] -= 0.42 * self.seated
            p[2] -= 1.15 * self.seated
        if self.node == "sofa":
            p[1] -= 0.2845 * self.seated  # HAVEN seat .503m; preserve the prior seated torso height.
            p[0] += 0.75 * self.seated
        if self.node == "bed":
            p[1] -= 0.6 * self.seated
            p[0] -= 1.2 * self.seated
            p[2] += 0.3 * self.seated
        privacy = self.privacy()
        house = self.interactions.view(self.settings)
        view = {
            "version": 1,
            "position": [round(v, 4) for v in p],
            "look": self.look,
            "entry_position": [round(v, 4) for v in self.position],
            "walking": bool(self.path) and self.seated == 0,
            "speed": round(self.speed, 3),
            "activity": self.activity,
            "place": self.node,
            "destination": self.target,
            # Remaining route waypoints (node names), so native clients follow
            # the server's own plan instead of re-planning it.
            "path": [] if privacy else list(self.path),
            "privacy": privacy,
            "seated": round(self.seated, 3),
            "sequence": self.sequence,
            "native_consumer": None if privacy else self.native_feedback.view(
                sequence=self.sequence, activity=self.activity, target=self.target),
            # Legacy flag, now the server front door state (approach included).
            "door_open": house["doors"]["front"]["open"],
            "doors": house["doors"],
            "lights": house["lights"],
            "presence": house["presence"],
            "settings": self.settings_view(),
            "console_game": self.console_game,
            "pending_console_game": self.pending_console_game,
            "phone": dict(self.phone),
            "pong": self.pong.view(),
            "notes": self.notes[-10:] if not compact else [],
            "memories": self.memories[-20:] if not compact else [],
        }
        # One privacy decision masks the actor for every viewer (WS and API).
        return hi.private_view(view) if privacy else view

    def to_dict(self):
        return {
            "navigation_version": 2,
            "node": self.node,
            "last_console_choice": self.last_console_choice,
            "console_game": self.console_game,
            "position": self.position,
            "path": self.path,
            "target": self.target,
            "activity": self.activity,
            "seated": self.seated,
            "time": self.time,
            "sequence": self.sequence,
            "bladder": self.bladder,
            "last_bathroom": self.last_bathroom,
            "pong": {
                "score": self.pong.score,
                "gain": self.pong.gain,
                "matches": self.pong.matches,
            },
            "settings": self.settings_view(),
            "interactions": self.interactions.to_dict(),
            "notes": self.notes,
            "memories": self.memories[-100:],
            "phone_app": self.phone["app"],
            "battery": self.phone["battery"],
        }
