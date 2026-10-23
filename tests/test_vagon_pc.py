"""Offline checks for the Vagon client: no network, no credentials, no real waiting. Safe to run anywhere."""
import base64
import io
import json
import logging
import re
import urllib.error
import urllib.request

import pytest

import vagon_pc

KEY, SECRET = "test-key", "test-secret"
PREFIX = "/organization-management/v1"
REAL_OPENER = vagon_pc._OPENER                  # the production opener, before any test replaces it
# Known answers. Each signature was computed outside this code with the openssl CLI, not with Python:
#   printf '%s' '<payload>' | openssl dgst -sha256 -hmac 'test-secret'
GET_PAYLOAD = "test-keyGET/organization-management/v1/machines17000000000000123456789abcdef"
GET_SIG = "c734bd81f890e7db290e0b790dfff9cb74e90ce67a824c8871dc0985d88efe19"
POST_PAYLOAD = ('test-keyPOST/organization-management/v1/machines/machine-1/stop'
                '1700000000001fedcba9876543210{"gracefully":true}')
POST_SIG = "d74842de2377abad37a6891244565ed06910d2d4316aa916592bdb585ed6a173"
GET_HEADER = f"HMAC {KEY}:{GET_SIG}:0123456789abcdef:1700000000000"
POST_HEADER = f"HMAC {KEY}:{POST_SIG}:fedcba9876543210:1700000000001"


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Stands in for the HTTP opener: records each request, then answers with bytes or raises the given exception."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def open(self, req, timeout=None):
        self.calls.append((req, timeout))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return FakeResponse(self.answer)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class NoNetwork:
    def open(self, *args, **kwargs):
        raise AssertionError("a request was sent")


@pytest.fixture(autouse=True)
def no_credentials_and_no_network(monkeypatch):
    """Each test starts without Vagon variables (a pod shell may export them) and with an opener that fails on use."""
    for name in ("VAGON_API_KEY", "VAGON_API_SECRET", "VAGON_PC_ENABLED", "VAGON_MACHINE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(vagon_pc, "_OPENER", NoNetwork())


@pytest.fixture
def api(monkeypatch):
    """Credentials set, clock and nonce fixed to the GET known answer. Returns a function that installs a fake."""
    monkeypatch.setenv("VAGON_API_KEY", KEY)
    monkeypatch.setenv("VAGON_API_SECRET", SECRET)
    monkeypatch.setattr(vagon_pc, "_now_ms", lambda: 1700000000000)
    monkeypatch.setattr(vagon_pc, "_new_nonce", lambda: "0123456789abcdef")

    def install(answer):
        fake = FakeOpener(answer)
        monkeypatch.setattr(vagon_pc, "_OPENER", fake)
        return fake
    return install


def _http_error(code, body=b""):
    return urllib.error.HTTPError("https://api.vagon.io/x", code, "msg", {}, io.BytesIO(body))


# --- signing -------------------------------------------------------------------------------------------------------

def test_the_payload_is_key_method_path_timestamp_nonce_body():
    assert vagon_pc._payload(KEY, "GET", PREFIX + "/machines", "1700000000000", "0123456789abcdef", "") == GET_PAYLOAD
    assert vagon_pc._payload(KEY, "POST", PREFIX + "/machines/machine-1/stop", "1700000000001", "fedcba9876543210",
                             '{"gracefully":true}') == POST_PAYLOAD


def test_known_answer_get_without_body():
    assert vagon_pc.signed_header("GET", PREFIX + "/machines", "", KEY, SECRET, timestamp_ms=1700000000000,
                                  nonce="0123456789abcdef") == GET_HEADER


def test_known_answer_post_with_body():
    assert vagon_pc.signed_header("POST", PREFIX + "/machines/machine-1/stop", '{"gracefully":true}', KEY, SECRET,
                                  timestamp_ms=1700000000001, nonce="fedcba9876543210") == POST_HEADER


def test_the_header_has_the_documented_shape():
    h = vagon_pc.signed_header("GET", PREFIX + "/machines", "", KEY, SECRET, timestamp_ms=1700000000000, nonce="abc")
    scheme, rest = h.split(" ", 1)
    key, sig, nonce, ts = rest.split(":")
    assert scheme == "HMAC" and (key, nonce, ts) == (KEY, "abc", "1700000000000")
    assert re.fullmatch(r"[0-9a-f]{64}", sig)


def test_the_body_is_part_of_the_signature():
    a = vagon_pc.signed_header("POST", "/x", '{"a":1}', KEY, SECRET, timestamp_ms=1, nonce="n")
    b = vagon_pc.signed_header("POST", "/x", '{"a":2}', KEY, SECRET, timestamp_ms=1, nonce="n")
    assert a != b


def test_call_signs_exactly_the_bytes_it_sends(api, monkeypatch):
    monkeypatch.setattr(vagon_pc, "_now_ms", lambda: 1700000000001)
    monkeypatch.setattr(vagon_pc, "_new_nonce", lambda: "fedcba9876543210")
    fake = api(b'{"ok": true}')
    assert vagon_pc.call("POST", "/machines/machine-1/stop", {"gracefully": True}) == {"ok": True}
    req, timeout = fake.calls[0]
    assert req.get_method() == "POST"
    assert req.full_url == vagon_pc.BASE + PREFIX + "/machines/machine-1/stop"
    assert req.data == b'{"gracefully":true}'
    assert req.get_header("Authorization") == POST_HEADER
    assert timeout == vagon_pc.TIMEOUT_S


def test_the_query_string_is_sent_but_not_signed(api):
    fake = api(b"{}")
    vagon_pc.call("GET", "/machines", query={"q": "a b"})
    req, _ = fake.calls[0]
    assert req.full_url == vagon_pc.BASE + PREFIX + "/machines?q=a+b"
    assert req.get_header("Authorization") == GET_HEADER


def test_without_credentials_no_request_is_made():
    with pytest.raises(vagon_pc.VagonError, match="VAGON_API_KEY"):
        vagon_pc.call("GET", "/machines")


# --- call(): errors, retries, redirects, answers ------------------------------------------------------------------

def test_a_429_is_raised_once_and_never_retried(api):
    fake = api(_http_error(429, b'{"message":"slow down"}'))
    with pytest.raises(vagon_pc.VagonError, match="HTTP 429") as info:
        vagon_pc.call("GET", "/machines")
    assert len(fake.calls) == 1
    assert "not retried" in str(info.value)


def test_error_text_holds_no_credential_signature_or_link(api):
    vendor = json.dumps({"message": f"bad {SECRET} {KEY} HMAC {KEY}:abc:def:1 https://x.test/?t=1"}).encode()
    api(_http_error(401, vendor))
    with pytest.raises(vagon_pc.VagonError) as info:
        vagon_pc.call("GET", "/machines")
    text = str(info.value)
    assert "HTTP 401" in text
    for leaked in (SECRET, KEY, "HMAC", "abc:def", "x.test"):
        assert leaked not in text


def test_a_long_vendor_message_is_cut_short(api):
    api(_http_error(500, json.dumps({"message": "x" * 500}).encode()))
    with pytest.raises(vagon_pc.VagonError) as info:
        vagon_pc.call("GET", "/machines")
    assert len(str(info.value)) < 250


def test_redirects_are_not_followed():
    assert any(isinstance(h, vagon_pc._NoRedirect) for h in REAL_OPENER.handlers)
    assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in REAL_OPENER.handlers)
    # urllib builds the redirected request only when this returns something: None means the 302 becomes an HTTPError
    req = urllib.request.Request(vagon_pc.BASE + PREFIX + "/machines")
    headers = {"location": "https://elsewhere.test/"}
    assert vagon_pc._NoRedirect().http_error_302(req, None, 302, "Found", headers) is None


def test_an_answer_that_is_not_json_is_a_vagon_error(api):
    api(b"<html>maintenance</html>")
    with pytest.raises(vagon_pc.VagonError, match="not JSON"):
        vagon_pc.call("GET", "/machines")


def test_an_empty_answer_is_an_empty_dict(api):
    api(b"  \n")
    assert vagon_pc.call("POST", "/machines/m1/start") == {}


def test_an_oversized_answer_is_refused(api, monkeypatch):
    monkeypatch.setattr(vagon_pc, "MAX_RESPONSE_BYTES", 10)
    api(b'{"machines": []}  ')
    with pytest.raises(vagon_pc.VagonError, match="more than 10 bytes"):
        vagon_pc.call("GET", "/machines")


@pytest.mark.parametrize("exc, expected", [
    (TimeoutError("read timed out"), "timed out after 20 s"),
    (urllib.error.URLError(TimeoutError("connect timed out")), "could not reach the API"),
    (ConnectionResetError("reset by peer"), "failed: ConnectionResetError"),
])
def test_network_failures_become_vagon_errors(api, exc, expected):
    api(exc)
    with pytest.raises(vagon_pc.VagonError, match=re.escape(expected)):
        vagon_pc.call("GET", "/machines")


def test_list_machines_reads_the_wrapped_and_the_bare_list(api):
    api(b'{"machines": [{"id": "m1"}, "junk"]}')
    assert vagon_pc.list_machines() == [{"id": "m1"}]
    api(b'[{"id": "m1"}]')
    assert vagon_pc.list_machines() == [{"id": "m1"}]


@pytest.mark.parametrize("answer", [b'{"items": []}', b'"text"'])
def test_an_unexpected_list_shape_is_an_error(api, answer):
    api(answer)
    with pytest.raises(vagon_pc.VagonError):
        vagon_pc.list_machines()


def test_the_machine_id_cannot_change_the_path(monkeypatch):
    seen = []
    monkeypatch.setattr(vagon_pc, "call", lambda method, path, body=None, **kw: seen.append(path) or {})
    vagon_pc.start_machine("m1/../../x?y")
    assert seen == ["/machines/m1%2F..%2F..%2Fx%3Fy/start"]


def test_reset_is_not_exposed():
    assert not [name for name in dir(vagon_pc) if "reset" in name.lower() or "delete" in name.lower()]


# --- status and waiting -------------------------------------------------------------------------------------------

def _machines(value):
    return [{"id": "m1", "attributes": {"friendly_status": value}}]


def test_status_returns_the_string_as_it_is(monkeypatch):
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: _machines("turning_on"))
    assert vagon_pc.status("m1") == "turning_on"


def test_an_unknown_status_is_returned_and_logged_once(monkeypatch, caplog):
    monkeypatch.setattr(vagon_pc, "_logged", set())
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: _machines("paused-by-vendor"))
    with caplog.at_level(logging.WARNING, logger="vagon_pc"):
        assert vagon_pc.status("m1") == "paused-by-vendor"
        assert vagon_pc.status("m1") == "paused-by-vendor"
    assert caplog.text.count("paused-by-vendor") == 1


def test_a_status_with_control_characters_is_logged_as_plain_text(monkeypatch, caplog):
    monkeypatch.setattr(vagon_pc, "_logged", set())
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: _machines("ready\n\x1b[2Jfake"))
    with caplog.at_level(logging.WARNING, logger="vagon_pc"):
        vagon_pc.status("m1")
    assert "\x1b" not in caplog.text and "\n\x1b" not in caplog.text and "fake" in caplog.text


def test_a_missing_status_is_none_and_the_log_names_the_fields(monkeypatch, caplog):
    monkeypatch.setattr(vagon_pc, "_logged", set())
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: [{"id": "m1", "attributes": {"state_text": "x"}}])
    with caplog.at_level(logging.WARNING, logger="vagon_pc"):
        assert vagon_pc.status("m1") is None
    assert "state_text" in caplog.text


def test_a_machine_without_attributes_has_no_status():
    assert vagon_pc.status_of({"id": "m1"}) is None


class _StatusSource:
    """Gives wait_ready one status per poll, from a list; the last value repeats."""

    def __init__(self, values):
        self.values = list(values)

    def __call__(self, machine_id):
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def test_wait_ready_gives_up_at_the_bound(monkeypatch):
    clock, polls = FakeClock(), []
    monkeypatch.setattr(vagon_pc, "status", lambda m: polls.append(m) or "off")
    with pytest.raises(vagon_pc.VagonError, match="not ready after 300 s"):
        vagon_pc.wait_ready("m1", poll_s=15, max_wait_s=300, clock=clock, sleep=clock.sleep)
    assert len(polls) == 21 and clock.now == 300


@pytest.mark.parametrize("value", vagon_pc.READY_STATUSES)
def test_wait_ready_returns_at_once_for_each_ready_value(monkeypatch, value):
    monkeypatch.setattr(vagon_pc, "status", lambda m: value)
    vagon_pc.wait_ready("m1", clock=FakeClock(), sleep=lambda s: pytest.fail("it slept"))


def test_wait_ready_polls_unknown_values_until_one_is_ready(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(vagon_pc, "status", _StatusSource(["weird", "turning_on", "ready"]))
    vagon_pc.wait_ready("m1", poll_s=5, max_wait_s=60, clock=clock, sleep=clock.sleep)
    assert clock.now == 10


# --- run-script and links -----------------------------------------------------------------------------------------

HOSTILE_LINKS = [                          # no space in any of them: all pass WEB_LINK and reach open_url
    "https://example.com/it's?x=1&y=2",
    'https://example.com/"quoted"',
    "https://example.com/$(Remove-Item,-Recurse,C:\\)",
    "https://example.com/`whoami`",
    "https://example.com/a;calc|more&&echo%PATH%^x<y>z",
    "https://example.com/${env:USERPROFILE}",
    "https://example.com/');Remove-Item,-Recurse,C:\\#",
    "https://example.com/%0a%0dStart-Process%20calc",
    "https://example.com/" + "a" * 1980,      # exactly MAX_LINK characters: accepted
]


@pytest.mark.parametrize("url", HOSTILE_LINKS)
def test_a_hostile_link_reaches_the_script_only_as_base64(monkeypatch, url):
    sent = []
    monkeypatch.setattr(vagon_pc, "run_script", lambda machine_id, script: sent.append(script) or "")
    vagon_pc.open_url("m1", url)
    (script,) = sent
    literal = re.search(r"FromBase64String\('([A-Za-z0-9+/=]+)'\)", script).group(1)
    assert base64.b64decode(literal).decode("ascii") == url
    assert script == vagon_pc.OPEN_SCRIPT.format(encoded=literal)
    outside = script.replace(literal, "")
    assert not set(outside) & set('"$`&|;%^<>!{}\r\n\t')


@pytest.mark.parametrize("bad", [
    "file:///etc/passwd", "javascript:alert(1)", "https://a.com/ b", "https://a.com/$(Remove-Item -Recurse C:\\)",
    "https://a.com/');Remove-Item C:\\ #", "https://a.com/\n", "https://a.com/\r",
    "https://a.com/\t", "https://a.com/\x00", "https://a.com/\u00fc", "https://a.com/" + "x" * 2000, "", None, 42,
])
def test_open_url_refuses_anything_that_is_not_a_plain_link(monkeypatch, bad):
    monkeypatch.setattr(vagon_pc, "run_script", lambda machine_id, script: pytest.fail("a refused link reached the PC"))
    with pytest.raises(vagon_pc.VagonError):
        vagon_pc.open_url("m1", bad)


def test_is_plain_link_is_the_one_gate():
    assert vagon_pc.is_plain_link("https://example.com/a?b=1")
    assert not vagon_pc.is_plain_link(b"https://example.com/")
    assert not vagon_pc.is_plain_link("https://example.com/" + "a" * 2000)


def test_run_script_returns_the_result_text(monkeypatch):
    monkeypatch.setattr(vagon_pc, "call", lambda *a, **k: {"result": "hello\r\n"})
    assert vagon_pc.run_script("m1", "Write-Output hello") == "hello\r\n"
    monkeypatch.setattr(vagon_pc, "call", lambda *a, **k: ["odd"])
    assert vagon_pc.run_script("m1", "x") == ""


REFUSED_HOSTS = [                       # SUB01-S03: addresses, numbers, userinfo, local names, wildcard DNS, odd marks
    "http://127.0.0.1/", "http://10.0.0.5/admin", "http://192.168.1.1/", "http://172.16.0.9/",
    "http://169.254.169.254/latest/meta-data/", "http://0.0.0.0/", "http://[::1]/", "http://[fe80::1]/",
    "http://[::ffff:10.0.0.1]/", "http://0x7f000001/", "http://2130706433/", "http://0177.0.0.1/", "http://127.1/",
    "http://0x7f.0.0.1/", "https://user:pw@formo.family/", "https://formo.family@203.0.113.9/",
    "https://a.com\\@b.com/", "https://example.com\\b.com/", "https://localhost\\.example.com/",
    "http://localhost/", "http://localhost:8080/admin",
    "http://printer.local/", "http://metadata.google.internal/", "http://metadata/", "http://box.lan/",
    "http://intranet.corp/", "http://1.0.0.127.in-addr.arpa/", "http://169.254.169.254.nip.io/",
    "http://127.0.0.1.sslip.io/", "http://a.localtest.me/", "http://example.com:8080/", "http://example.com:22/",
    "http://exa%6Dple.com/", "http://exa_mple.com/", "http://a..b.com/", "http://a-.com/", "http://[::1/",
]
PUBLIC_LINKS = ["https://example.com/", "http://example.com:80/x", "https://example.com:443/", "https://example.com./",
                "https://formo.family/?q=1", "https://xn--80ak6aa92e.com/", "https://a.example/",
                "https://EXAMPLE.org/Path", "https://sub.domain-name.co.uk/x?y=z&w=1#frag"]


@pytest.mark.parametrize("url", REFUSED_HOSTS)
def test_a_link_to_an_address_or_a_local_name_is_not_plain(url):
    assert vagon_pc.is_plain_link(url) is False, url


@pytest.mark.parametrize("url", PUBLIC_LINKS)
def test_a_link_to_a_public_name_is_plain(url):
    assert vagon_pc.is_plain_link(url) is True, url


def test_open_url_sends_nothing_to_the_pc_for_a_private_host(monkeypatch):
    monkeypatch.setattr(vagon_pc, "run_script", lambda machine_id, script: pytest.fail("a private link reached the PC"))
    for url in REFUSED_HOSTS:
        with pytest.raises(vagon_pc.VagonError):
            vagon_pc.open_url("m1", url)


def test_auto_stop_only_accepts_the_vendor_steps(monkeypatch):
    sent = []
    monkeypatch.setattr(vagon_pc, "call", lambda *a, **k: sent.append(a) or {})
    with pytest.raises(vagon_pc.VagonError):
        vagon_pc.set_auto_stop("m1", 600)
    assert sent == []
    vagon_pc.set_auto_stop("m1", 900)
    assert sent == [("PATCH", "/machines/m1", {"auto_stop_threshold": 900})]
