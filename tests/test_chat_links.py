"""The chat's link rule and the filter around it. A link is refused unless check(links_open=True) (the PC can open
links); then the other rules judge the message as they judge any other. Nicknames and taught words refuse links always.
Also here: the bypasses a viewer can try (invisible characters, unicode dots, defanged forms, "example . com"), the
ordinary text that must pass (e.g., "e.g.", "v1.2", "life.py", "spicy"), and the limits over a long run.

    python -m pytest tests/test_chat_links.py
No network.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chat  # noqa: E402

# invisible characters and look-alikes, written as code points (they cannot be seen in the source)
ZWSP, WORD_JOINER, SOFT_HYPHEN, BOM = chr(0x200B), chr(0x2060), chr(0x00AD), chr(0xFEFF)
IDEO_STOP, HALFWIDTH_STOP, FULLWIDTH_STOP, NBSP = chr(0x3002), chr(0xFF61), chr(0xFF0E), chr(0x00A0)
FIRE, SKULL = chr(0x1F525), chr(0x1F480)


def fullwidth(text):
    return "".join(chr(0xFEE0 + ord(c)) if "!" <= c <= "~" else c for c in text)


LINKS = ["https://example.com", "http://example.com/a?b=1", "ftp://files.example.org/x", "ftp://files.zz/x",
         "www.example.com", "example.com", "example.com/page", "pump.fun", "sub01.xyz", "t.me/group", "discord.gg/abc",
         "bit.ly/x", "youtu.be/abc", "linktr.ee/x", "goo.gl/x", "sub01.de", "sub01.uk", "tiny.cc/x"]
LINKS_OPEN_OK = ["https://example.com", "http://example.com/a?b=1", "www.example.com", "example.com",
                 "example.com/page", "youtu.be/abc", "https://en.wikipedia.org/wiki/Inokashira_Park"]
# a link with another rule broken: that rule's reason, and the viewer keeps the turn
LINKS_OPEN_REFUSED = [
    ("https://example.com you idiot", "insults are not allowed"),
    ("https://example.com kys", "insults are not allowed"),
    ("https://example.com $PEPE", "tickers are not allowed"),
    ("https://example.com 0x52908400098527886E0F7030069857D2E4169EE7", "addresses are not allowed"),
    ("https://example.com 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "addresses are not allowed"),
    ("https://example.com send me 5 sol", "no requests for money"),
    ("https://pump.fun/abc", "no trading or get-rich talk"),
    ("https://example.com porn", "keep it clean"),
    ("https://example.com +39 333 123 4567", "no personal data"),
]
# links a viewer's browser still reads as links, written so that the plain text does not show them
OBFUSCATED_LINKS = [
    "example" + ZWSP + ".com",                      # zero-width space before the dot
    "youtu" + SOFT_HYPHEN + ".be/abc",              # soft hyphen inside the name
    "example" + WORD_JOINER + ".de",                # word joiner
    "example" + BOM + ".youtu.be",                  # byte order mark
    "example" + IDEO_STOP + "com",                  # ideographic full stop
    "example" + HALFWIDTH_STOP + "com",             # halfwidth ideographic full stop
    "example" + FULLWIDTH_STOP + "com",             # full-width full stop
    fullwidth("example") + ".com",                  # full-width letters
    "hxxp://example.de",                            # defanged scheme
    "hXXps://sub01.de/x",
    "evil[.]com", "evil(.)com", "evil[dot]com", "evil{dot}de",
    "example . com", "example" + NBSP + "." + NBSP + "com",       # spaces round the dot
]
# ordinary text: dots, version numbers, file names, abbreviations and plain words that contain a slur
ORDINARY = ["e.g. the lamp", "see you at 5 a.m. tomorrow", "v1.2 is out", "life.py and mind.py",
            "Ciao, ti voglio bene.", "Vado a Roma. Ci vediamo domani.", "Dr. Smith", "the U.S. and the U.K.",
            "Ph.D. in physics", "node.js and vue.js", "spicy ramen", "a spiced cider", "retarding force",
            "the chinking of logs", "the top of the hill", "go to sleep."]


@pytest.mark.parametrize("text", LINKS)
def test_links_are_refused_by_default(text):
    lim, dd = chat.RateLimiter(), chat.Dedupe()
    assert chat.check(text, "k", lim, dd) == (False, "links are not allowed"), text
    assert chat.check(text, "k", lim, dd, links_open=False) == (False, "links are not allowed"), text
    assert chat.blocked(text) == "links are not allowed" and chat.message_blocked(text) == "links are not allowed", text
    assert "k" not in lim.last                          # refused before the rate limit: the viewer may write again


@pytest.mark.parametrize("text", LINKS_OPEN_OK)
def test_links_are_accepted_when_the_pc_can_open_them(text):
    assert chat.check(text, "k", chat.RateLimiter(), chat.Dedupe(), links_open=True) == (True, None), text


@pytest.mark.parametrize("text, reason", LINKS_OPEN_REFUSED)
def test_a_link_with_another_rule_broken_is_refused_for_that_reason(text, reason):
    lim = chat.RateLimiter()
    assert chat.check(text, "k", lim, chat.Dedupe(), links_open=True) == (False, reason), text
    assert "k" not in lim.last                          # a refused message does not use the viewer's turn


def test_nicknames_and_taught_words_refuse_links_whatever_links_open_says():
    lim = chat.TeachLimits()
    assert chat.clean_nick("t.me/me") == ("", "nickname: links are not allowed")
    assert chat.clean_nick("example" + IDEO_STOP + "com") == ("", "nickname: links are not allowed")
    assert chat.check_teach("https://example.com", "", "k", lim, "d1", []) == (False, "links are not allowed", "", "")
    assert chat.check_teach("visit youtu.be/abc", "", "k", lim, "d1", [])[1] == "links are not allowed"
    assert lim.keys == set()                            # refused before the one-per-day note


def test_skip_links_leaves_only_the_link_rule_out():
    assert chat.message_blocked("example.com", skip_links=True) is None
    assert chat.message_blocked("example.com") == "links are not allowed"
    assert chat.blocked("pump.fun", skip_links=True) == "no trading or get-rich talk"


def test_rate_limit_and_duplicates_apply_to_links_too():
    clock = [0.0]
    lim, dd = chat.RateLimiter(clock=lambda: clock[0]), chat.Dedupe()
    assert chat.check("https://example.com", "a", lim, dd, links_open=True) == (True, None)
    assert chat.check("hello", "a", lim, dd, links_open=True) == (False, "one message every 10 s")
    clock[0] = 11
    assert chat.check("https://example.com", "a", lim, dd, links_open=True) == (False, "duplicate")
    assert chat.check("https://example.com", "b", lim, dd, links_open=True) == (False, "duplicate")
    clock[0] = 22
    assert chat.check("https://example.com/other", "a", lim, dd, links_open=True) == (True, None)


def test_refused_links_do_not_use_the_viewers_turn():
    clock = [0.0]
    lim, dd = chat.RateLimiter(clock=lambda: clock[0]), chat.Dedupe()
    assert chat.check("see https://x.io", "c", lim, dd) == (False, "links are not allowed")
    assert chat.check("https://a.com idiot", "c", lim, dd, links_open=True) == (False, "insults are not allowed")
    assert "c" not in lim.last
    assert chat.check("hello", "c", lim, dd)[0]


@pytest.mark.parametrize("text", OBFUSCATED_LINKS)
def test_obfuscated_links_are_refused_by_default(text):
    assert chat.check(text, "k", chat.RateLimiter(), chat.Dedupe()) == (False, "links are not allowed"), repr(text)
    assert chat.blocked(text) == "links are not allowed", repr(text)


def test_link_text_reads_the_link_a_browser_would():
    assert chat.link_text("hxxp://evil[.]com") == "http://evil.com"
    assert chat.link_text("example " + IDEO_STOP + " com" + ZWSP) == "example.com"
    assert chat.link_text("Ciao. Come stai?") == "Ciao. Come stai?"    # a sentence stop is not a dot in a name


@pytest.mark.parametrize("text, reason", [
    ("$" + ZWSP + "PEPE to the moon", "tickers are not allowed"),
    ("s" + ZWSP + "end 5 sol", "no requests for money"),
    ("5€ for you", "no requests for money"),
    ("€5 for a coffee", "no requests for money"),
    ("kill yourselves", "insults are not allowed"),
    ("hang yourselves", "insults are not allowed"),
    ("spic", "insults are not allowed"),
])
def test_invisible_characters_and_forms_the_filter_missed(text, reason):
    assert chat.blocked(text) == reason, text


def test_invisible_only_message_is_empty():
    assert chat.check(ZWSP + WORD_JOINER, "k", chat.RateLimiter(), chat.Dedupe()) == (False, "empty")
    assert chat.check_teach(ZWSP, "", "k", chat.TeachLimits(), "d1", []) == (False, "empty", "", "")


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_text_with_dots_and_words_passes(text):
    assert chat.blocked(text) is None, text
    assert chat.check(text, "k", chat.RateLimiter(), chat.Dedupe())[0], text


def test_emoji_and_punctuation_only_messages_are_not_duplicates_of_each_other():
    lim, dd = chat.RateLimiter(), chat.Dedupe()
    assert chat.check(FIRE, "a", lim, dd) == (True, None)
    assert chat.check(SKULL, "b", lim, dd) == (True, None)
    assert chat.check(FIRE, "c", lim, dd) == (False, "duplicate")     # the same emoji is still a duplicate
    assert chat.check("!!!", "d", lim, dd) == (True, None)
    assert chat.check("???", "e", lim, dd) == (True, None)
    assert chat.dedupe_key("HELLO!") == chat.dedupe_key("hello") == "hello"


def test_rate_limiter_forgets_viewers_over_a_long_run():
    clock = [0.0]
    lim = chat.RateLimiter(clock=lambda: clock[0])
    peak = 0
    for i in range(3 * 3600 * 2):                       # three hours, a new viewer every half second
        clock[0] = i * 0.5
        assert lim.allow(f"ip{i}")
        peak = max(peak, len(lim.last))
    assert peak <= 21                                   # only the last RATE_S seconds are kept
    clock[0] += chat.RATE_S
    assert lim.allow("ip0") and len(lim.last) <= 21     # a viewer seen long ago is allowed again


def test_duplicate_check_and_teach_limits_stay_small_over_a_long_run():
    dd = chat.Dedupe()
    for i in range(50_000):
        dd.seen(f"message number {i}")
    assert len(dd.recent) == 200
    assert dd.seen("message number 49999") and not dd.seen("message number 0")
    lim = chat.TeachLimits(per_day=30)
    for i in range(5000):
        chat.check_teach(f"word {i}", "", f"ip{i}", lim, "d1", [])
    assert len(lim.keys) == 30 and lim.count == 30
