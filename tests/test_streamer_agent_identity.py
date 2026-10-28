"""Owner 10-28: "one password he uses everywhere". His one identity lives in a file the owner writes on the pod; the model
writes {{email}} / {{username}} / {{password}} and the code fills them in at dispatch (Kimi login1)."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_streamer_agent as T  # noqa: E402

SA = T.SA
PASSWORD = "Sub01-one-Pass-77"


def identity(tmp_path, **fields):
    path = tmp_path / "sub01-login.json"
    path.write_text(json.dumps(fields or {"email": "sub01.streamer@example.com", "username": "sub01live",
                                          "password": PASSWORD}))
    os.chmod(path, 0o600)
    return path


def test_placeholders_are_whole_texts_and_need_credentials_on():
    a, why = SA.clean_pc_action({"action": "type", "text": "{{password}}", "submit": True}, allow_credentials=True)
    assert why is None and a["identity"] == "password" and a["secret"] and a["credential"] and a["submit"]
    assert SA.clean_pc_action({"action": "type", "text": "{{password}}"}, allow_credentials=False)[0] is None
    for text in ("my {{password}}", "{{password}}{{email}}", "{{ password }}", "{{token}}"):
        a, _ = SA.clean_pc_action({"action": "type", "text": text}, allow_credentials=True)
        assert a is None or "identity" not in a, text
    assert SA.clean_action({"action": "type", "text": "{{email}}"}, {}, allow_credentials=True)[0]["identity"] == "email"
    assert SA.public_action({"action": "type", "text": "{{email}}", "secret": True})["text"] != "{{email}}"


def test_read_identity_is_strict(tmp_path):
    path = identity(tmp_path)
    assert SA.read_identity("password", path) == PASSWORD and SA.read_identity("email", path).endswith("@example.com")
    assert SA.read_identity("phone", path) is None and SA.read_identity("password", tmp_path / "missing.json") is None
    link = tmp_path / "link.json"
    link.symlink_to(path)
    assert SA.read_identity("password", link) is None                     # never through a symlink
    (tmp_path / "big.json").write_text(json.dumps({"password": "x" * 5000}))
    assert SA.read_identity("password", tmp_path / "big.json") is None
    (tmp_path / "bad.json").write_text("not json")
    assert SA.read_identity("password", tmp_path / "bad.json") is None


def test_the_password_is_filled_in_at_dispatch_only_on_a_private_page_and_never_logged(tmp_path):
    steps = [T.decision(state="typing", action={"action": "type", "text": "{{password}}", "submit": True}, say=""),
             T.decision(state="idle", action=None, say="", private_screen=True),
             T.decision(state="typing", action={"action": "type", "text": "{{password}}", "submit": True}, say="",
                        private_screen=True)]
    agent, world, prov, clock = T.pc_make(tmp_path, *steps)
    agent.identity_file = identity(tmp_path)
    asyncio.run(T.decide_once(agent, clock, dt=3))                         # not marked private: refused
    assert not world.acts and "marked private_screen" in agent.last_outcome["errors"][0]
    asyncio.run(T.decide_once(agent, clock, dt=3))
    assert agent.privacy
    T.ack_director(world, agent)
    asyncio.run(T.decide_once(agent, clock, dt=3))
    assert world.acts == [{"action": "type", "text": PASSWORD, "submit": True}]
    logged = "".join(p.read_text() for p in agent.dir.rglob("*") if p.is_file() and p != agent.identity_file)
    assert PASSWORD not in logged and PASSWORD in agent.typed_secrets


def test_no_identity_file_is_a_generic_refusal(tmp_path):
    step = T.decision(state="typing", action={"action": "type", "text": "{{email}}"}, say="", private_screen=True)
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision(state="idle", action=None, say="", private_screen=True), step)
    agent.identity_file = tmp_path / "missing.json"
    asyncio.run(T.decide_once(agent, clock, dt=3))
    T.ack_director(world, agent)
    asyncio.run(T.decide_once(agent, clock, dt=3))
    assert not world.acts and agent.last_outcome["errors"][0] == "no login identity on this PC"


def test_the_prompt_tells_the_model_the_placeholders_only_with_credentials_on():
    on, off = SA.system_prompt(pc=True, allow_credentials=True), SA.system_prompt(pc=True)
    assert "{{password}}" in on and "Continue/Sign in with Google" in on and "{{password}}" not in off
