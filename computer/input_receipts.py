"""Bounded correlation futures on the existing VM stdio, never an input queue."""
import asyncio
import math
import secrets
import time

MAX_NATIVE_ID = 2**53 - 1
LEVELS = {"GuestKeyboardInjected", "GuestMouseInjected"}


def native_receipt(value):
    if (not isinstance(value, dict) or set(value) != {"input_id", "generation"}
            or any(type(value[k]) is not int or not 1 <= value[k] <= MAX_NATIVE_ID for k in value)):
        raise ValueError("Expected bounded native input identity")
    return dict(value)


class InputReceipts:
    def __init__(self, capacity=32):
        self.capacity = capacity
        self.generation = secrets.randbelow(2**52) + 1
        self.pending = {}

    def begin(self, process, native, level):
        native = native_receipt(native)
        if level not in LEVELS or len(self.pending) >= self.capacity:
            return None
        identifier = secrets.token_hex(16)
        future = asyncio.get_running_loop().create_future()
        entry = {"future": future, "process": process, "generation": self.generation,
                 "native": native, "level": level, "queued_at": time.monotonic()}
        self.pending[identifier] = entry
        return identifier, {"id": identifier, "generation": self.generation,
                            "deadline_ms": time.time() * 1000 + 1400}, future

    def complete(self, message, process):
        if not isinstance(message, dict) or message.get("type") != "graphical-input-ack":
            return False
        identifier = message.get("id")
        if not isinstance(identifier, str):
            return False
        entry = self.pending.get(identifier)
        if not entry or process is not entry["process"] or type(message.get("generation")) is not int or message["generation"] != entry["generation"]:
            return False
        stamps = [message.get(k) for k in ("started_ms", "finished_ms")]
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in stamps) or stamps[1] < stamps[0] or stamps[1] - stamps[0] > 1500:
            return False
        ok = message.get("ok") is True and message.get("level") == entry["level"]
        # A false/unknown-level ACK is terminal, never promoted to guest injection.
        self.pending.pop(identifier)
        if not entry["future"].done():
            entry["future"].set_result({"ok": ok, "native_receipt": entry["native"],
                "ack_level": entry["level"] if ok else "Rejected", "queued_at": entry["queued_at"],
                "ack_received_at": time.monotonic(), "worker_started_ms": stamps[0], "worker_finished_ms": stamps[1]})
        return True

    def discard(self, identifier):
        entry = self.pending.pop(identifier, None)
        if entry and not entry["future"].done():
            entry["future"].set_result({"ok": False})
        return {"type": "graphical-input-cancel", "id": identifier,
                "generation": entry["generation"]} if entry else None

    def cancel_all(self):
        packets = [self.discard(identifier) for identifier in list(self.pending)]
        self.generation = self.generation % MAX_NATIVE_ID + 1
        return packets
