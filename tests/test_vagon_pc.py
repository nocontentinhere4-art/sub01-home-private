"""Offline checks for the Vagon client: no network, no credentials. Run on the pod, not locally."""
import pytest

import vagon_pc


def test_header_has_the_documented_shape():
    h = vagon_pc.signed_header("GET", "/organization-management/v1/machines", "", "key", "secret",
                               timestamp_ms=1700000000000, nonce="abc")
    scheme, rest = h.split(" ", 1)
    key, sig, nonce, ts = rest.split(":")
    assert scheme == "HMAC"
    assert (key, nonce, ts) == ("key", "abc", "1700000000000")
    assert len(sig) == 64 and all(c in "0123456789abcdef" for c in sig)


def test_the_body_is_part_of_the_signature():
    a = vagon_pc.signed_header("POST", "/x", '{"a":1}', "k", "s", timestamp_ms=1, nonce="n")
    b = vagon_pc.signed_header("POST", "/x", '{"a":2}', "k", "s", timestamp_ms=1, nonce="n")
    assert a != b


def test_open_url_quotes_apostrophes_and_keeps_the_query(monkeypatch):
    sent = []
    monkeypatch.setattr(vagon_pc, "run_script", lambda machine_id, script: sent.append(script) or "")
    vagon_pc.open_url("m1", "https://example.com/it's?x=1&y=2")
    assert sent == ["Start-Process 'https://example.com/it''s?x=1&y=2'"]


@pytest.mark.parametrize("bad", ["file:///etc/passwd", "https://a.com/ b", "javascript:alert(1)", "https://a.com/\n",
                                 "https://a.com/" + "x" * 2000])
def test_open_url_refuses_other_schemes_spaces_and_newlines(monkeypatch, bad):
    monkeypatch.setattr(vagon_pc, "run_script", lambda machine_id, script: "")
    with pytest.raises(vagon_pc.VagonError):
        vagon_pc.open_url("m1", bad)


def test_auto_stop_only_accepts_the_vendor_steps(monkeypatch):
    monkeypatch.setattr(vagon_pc, "call", lambda *a, **k: {})
    with pytest.raises(vagon_pc.VagonError):
        vagon_pc.set_auto_stop("m1", 600)
    vagon_pc.set_auto_stop("m1", 900)
