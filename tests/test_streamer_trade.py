"""Owner 10-28: SUB-01 trades on fomo.family by chat vote (streamer_trade.py and its wiring in streamer_agent.py;
Kimi trade1: allowlist, one vote per connection, a ledger that never gives money back, the read-back confirm)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_streamer_agent as T  # noqa: E402

SA = T.SA
TR = SA.TR
COINS = [dict(c) for c in TR.DEFAULT_COINS]
V = ["a1b2c3d4e5f60718", "b1b2c3d4e5f60718", "c1b2c3d4e5f60718", "d1b2c3d4e5f60718"]


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# ------------------------------------------------------------------ parsing and the allowlist

@pytest.mark.parametrize("text,want", [
    ("buy wif", ("buy", "WIF")), ("Buy $BONK pls", ("buy", "BONK")), ("buy dogwifhat", ("buy", "WIF")),
    ("sell all popcat", ("sell", "POPCAT")), ("dump pepe", ("sell", "PEPE")), ("hey sub01, buy some brett", ("buy", "BRETT")),
    ("buy shib", "not_listed"), ("buy 3ZvEeeLxo55nKRwHywyxqBpKVouRV4gARNDUCQpapump", "address"),
    ("buy wif at pump.fun", "address"), ("buy me a coffee", None), ("sell everything", None), ("i would buy wif", None),
    ("wif is cool", None)])
def test_parse_trade_takes_listed_coins_only(text, want):
    got = TR.parse_trade(text, COINS)
    if want is None:
        assert got is None
    elif isinstance(want, str):
        assert got["refused"] == want
    else:
        assert (got["side"], got["coin"]["symbol"]) == want


def test_load_coins_default_owner_file_and_fail_closed(tmp_path):
    assert [c["symbol"] for c in TR.load_coins(tmp_path / "none.json")][:2] == ["WIF", "BONK"]
    f = tmp_path / "coins.json"
    f.write_text(json.dumps([{"symbol": "WIF", "chain": "solana", "address": COINS[0]["address"]}]))
    assert [c["symbol"] for c in TR.load_coins(f)] == ["WIF"]
    f.write_text(json.dumps([{"symbol": "WIF", "chain": "solana", "address": "not-an-address"}]))
    assert TR.load_coins(f) is None                                   # one bad entry: no trading at all
    f.write_text("{broken")
    assert TR.load_coins(f) is None


# ------------------------------------------------------------------ ledger, vote, read-back

def test_ledger_reserves_before_and_never_gives_money_back(tmp_path):
    led = TR.Ledger(tmp_path / "l.json", lambda: 1000.0)
    assert led.next_buy_usd() == 10.0
    for i in range(5):
        led.reserve({"id": f"t{i}", "side": "buy", "coin": COINS[0], "usd": 10.0})
        led.settle(f"t{i}", "failed" if i == 0 else "done")           # a failed buy still counts (fail-safe)
    led.reserve({"id": "s", "side": "sell", "coin": COINS[0], "usd": 0.0})
    assert led.spent() == 50.0 and led.next_buy_usd() == 0.0          # a sell frees nothing
    assert TR.Ledger(tmp_path / "l.json").spent() == 50.0             # saved
    (tmp_path / "bad.json").write_text("{nope")
    assert TR.Ledger(tmp_path / "bad.json").next_buy_usd() == 0.0     # unreadable: the budget counts as spent


def test_vote_needs_three_connections_one_answer_each_and_yes_majority(tmp_path):
    c = Clock()
    desk = TR.TradeDesk(TR.Ledger(tmp_path / "l.json", c), COINS, c)
    p = TR.parse_trade("buy wif", COINS)
    assert desk.propose(p, "", "Marco", c()) == ("refused", "anonymous")
    status, t = desk.propose(p, V[0], "Marco", c())
    assert status == "open" and t["usd"] == 10.0
    assert desk.propose(TR.parse_trade("buy bonk", COINS), V[1], "Luca", c()) == ("refused", "busy")
    assert desk.answer(V[0], "yes", c()) and desk.answer(V[0], "yes", c())   # the same connection twice: one vote
    assert desk.answer(V[1], "no", c()) and not desk.answer(V[2], "yes please send it", c())
    c.t += TR.VOTE_S
    t, passed, yes, no = desk.tally(c())
    assert (passed, yes, no) == (False, 1, 1) and desk.active is None
    c.t += TR.TRADE_GAP_S
    assert desk.propose(p, V[0], "Marco", c()) == ("refused", "proposer")     # 15 min per proposer
    status, t = desk.propose(p, V[1], "Luca", c())
    assert status == "refused" and t == "coin"                                 # the same coin: 10 min
    status, t = desk.propose(TR.parse_trade("buy bonk", COINS), V[1], "Luca", c())
    for v in V[:3]:
        desk.answer(v, "yes", c())
    desk.answer(V[3], "no", c())
    c.t += TR.VOTE_S
    t, passed, yes, no = desk.tally(c())
    assert passed and (yes, no) == (3, 1) and desk.active is t and desk.ledger.spent() == 10.0   # reserved at once


def test_read_back_confirm_once_and_typed_amounts(tmp_path):
    c = Clock()
    desk = TR.TradeDesk(TR.Ledger(tmp_path / "l.json", c), COINS, c)
    desk.propose(TR.parse_trade("buy wif", COINS), V[0], "", c())
    for v in V[:3]:
        desk.answer(v, "y", c())
    c.t += TR.VOTE_S
    desk.tally(c())
    assert desk.confirm_ok(None) == "no read-back"
    assert desk.confirm_ok({"side": "buy", "symbol": "WIF", "amount_usd": 50}) == "amount above the voted amount"
    assert desk.confirm_ok({"side": "buy", "symbol": "BONK", "amount_usd": 10}) == "wrong coin"
    assert desk.confirm_ok({"side": "sell", "symbol": "WIF", "amount_usd": 10}) == "wrong side"
    assert desk.confirm_ok({"side": "buy", "symbol": "$wif", "amount_usd": "10"}) is None
    assert desk.confirm_ok({"side": "buy", "symbol": "WIF", "amount_usd": 10}) == "already confirmed (no retry)"
    assert TR.amount_typed_problem("10", desk.active) is None and TR.amount_typed_problem("$100", desk.active)
    assert TR.amount_typed_problem("e4", desk.active) is None and TR.amount_typed_problem("25", None)
    done = desk.finish("done", c())
    assert done["status"] == "done" and desk.ledger.holds("WIF")


def test_unconfirmed_trade_settles_failed_but_stays_spent(tmp_path):
    c = Clock()
    desk = TR.TradeDesk(TR.Ledger(tmp_path / "l.json", c), COINS, c)
    desk.propose(TR.parse_trade("buy wif", COINS), V[0], "", c())
    for v in V[:3]:
        desk.answer(v, "yes", c())
    c.t += TR.VOTE_S
    desk.tally(c())
    assert desk.finish("done", c())["status"] == "failed" and desk.ledger.spent() == 10.0
    assert desk.propose(TR.parse_trade("sell wif", COINS), V[1], "", c() + TR.COIN_GAP_S) == ("refused", "not_held")


@pytest.mark.parametrize("line", [TR.vote_line({"side": "buy", "usd": 10.0, "coin": COINS[0]}),
                                  TR.vote_line({"side": "sell", "usd": 0.0, "coin": COINS[0]}),
                                  TR.result_line({}, True, 4, 1), TR.result_line({}, False, 1, 0),
                                  TR.result_line({}, False, 1, 3)] + [x for x in TR.REFUSE_LINES.values() if x])
def test_every_trade_line_may_be_spoken(line):
    assert SA.reply_problem(line) is None


# ------------------------------------------------------------------ the agent

def trade_agent(tmp_path, *script):
    agent, world, prov, clock = T.pc_make(tmp_path, *script)
    (agent.dir / "trading-on").write_text("on")
    agent.pc.mode = "vagon"                                                    # as after the first look at the remote PC
    return agent, world, prov, clock


def test_trading_is_off_without_the_owners_file(tmp_path):
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision())
    agent.pc.mode = "vagon"
    agent.ingest_chat([{"seq": 1, "text": "buy wif", "nick": "Marco", "voter": V[0]}])
    assert agent.trade.vote is None and agent.counters["trade_votes_opened"] == 0


def test_a_vote_in_chat_becomes_the_next_request_and_answers_never_reach_the_model(tmp_path):
    agent, world, prov, clock = trade_agent(tmp_path, T.decision())
    agent.ingest_chat([{"seq": 1, "text": "buy wif", "nick": "Marco", "voter": V[0]}])
    assert agent.trade.vote is not None and any("Chat vote: buy 10 dollars of WIF" in x.text for x in agent.speech_q)
    agent.ingest_chat([{"seq": 2 + i, "text": "yes", "nick": f"n{i}", "voter": v} for i, v in enumerate(V[:3])])
    assert not agent.pending                                                   # vote answers are not chat
    clock.t += TR.VOTE_S
    agent.trade_tick(clock())
    assert agent.requests.waiting[0]["kind"] == "trade" and agent.trade.ledger.spent() == 10.0
    st = agent.trade.state(clock())["trade"]
    assert st["symbol"] == "WIF" and st["usd"] == 10.0 and st["address"] == COINS[0]["address"]


def test_trade_guard_refuses_a_big_amount_and_a_confirm_without_a_matching_read_back(tmp_path):
    agent, world, prov, clock = trade_agent(tmp_path, T.decision())
    agent.ingest_chat([{"seq": 1, "text": "buy wif", "nick": "Marco", "voter": V[0]}])
    agent.ingest_chat([{"seq": 2 + i, "text": "yes", "voter": v} for i, v in enumerate(V[:3])])
    clock.t += TR.VOTE_S
    agent.trade_tick(clock())
    agent.requests.current = dict(agent.requests.waiting.popleft(), started=clock(), steps=1, done=False, commented=False,
                                  phase="report")
    dec = {"dropped": [], "trade_confirm": False, "trade_check": None}
    assert agent.trade_guard(dec, {"action": "type", "text": "100"}, clock()) is None
    click = {"action": "click", "point": [10, 10]}
    dec = {"dropped": [], "trade_confirm": True, "trade_check": {"side": "buy", "symbol": "WIF", "amount_usd": 100}}
    assert agent.trade_guard(dec, click, clock()) is None and "trade confirm refused" in dec["dropped"][0]
    dec = {"dropped": [], "trade_confirm": True, "trade_check": {"side": "buy", "symbol": "WIF", "amount_usd": 10}}
    assert agent.trade_guard(dec, click, clock()) == click
    dec = {"dropped": [], "trade_confirm": True, "trade_check": {"side": "buy", "symbol": "WIF", "amount_usd": 10}}
    assert agent.trade_guard(dec, click, clock()) is None                      # no second order
    agent.requests.current.update(steps=3, done=True, commented=True)
    agent.finish_request("done", clock())
    rows = json.loads((agent.dir / "trade-ledger.json").read_text())["rows"]
    assert rows[-1]["status"] == "done" and agent.trade.active is None


def test_decision_keeps_the_trade_fields_on_the_pc():
    raw = json.dumps({"action": {"action": "click", "point": [5, 5]}, "trade_confirm": True,
                      "trade_check": {"side": "buy", "symbol": "WIF", "amount_usd": 10, "extra": "x"}})
    d = SA.validate_decision(raw, {}, pc={"allow_games": True})
    assert d["trade_confirm"] is True and d["trade_check"] == {"side": "buy", "symbol": "WIF", "amount_usd": 10}


def test_the_pc_prompt_has_the_trading_rules():
    p = SA.system_prompt(pc=True, allow_credentials=True)
    assert "trade_confirm" in p and "Never Deposit, Withdraw" in p
    assert "trade_confirm" not in SA.system_prompt(pc=False)


# ------------------------------------------------------------------ Kimi trade2

@pytest.mark.parametrize("text,ok", [("10", True), ("$9.5", True), ("7.25", True), ("1,000", False), ("100.", False),
                                     ("1e3", False), ("0x10", True), ("10 0", False), ("WIF", True), ("e4", True)])
def test_only_plain_amounts_are_typed(text, ok):
    trade = {"side": "buy", "usd": 10.0}
    assert (TR.amount_typed_problem(text, trade) is None) == ok


@pytest.mark.parametrize("rows", ['{"rows": [{"id": "a", "t": 5, "side": "buy", "symbol": "WIF", "usd": -50, "status": "done"}]}',
                                  '{"rows": [{"id": "a", "t": 5, "side": "buy", "symbol": "WIF", "usd": NaN, "status": "done"}]}',
                                  '{"rows": "x"}', '{"rows": [{"id": "a", "side": "buy", "usd": 1}]}', '[]'])
def test_any_invalid_ledger_counts_as_all_spent(tmp_path, rows):
    f = tmp_path / "l.json"
    f.write_text(rows)
    assert TR.Ledger(f).next_buy_usd() == 0.0


def test_an_unsaved_reservation_aborts_the_trade(tmp_path):
    c = Clock()
    desk = TR.TradeDesk(TR.Ledger(tmp_path / "missing-dir" / "l.json", c), COINS, c)
    desk.propose(TR.parse_trade("buy wif", COINS), V[0], "", c())
    for v in V[:3]:
        desk.answer(v, "yes", c())
    c.t += TR.VOTE_S
    t, passed, _, _ = desk.tally(c())
    assert not passed and t["error"] == "ledger" and desk.active is None and desk.ledger.next_buy_usd() == 0.0


def voted(agent, clock, text="buy wif"):
    agent.ingest_chat([{"seq": 1, "text": text, "nick": "Marco", "voter": V[0]}])
    agent.ingest_chat([{"seq": 2 + i, "text": "yes", "voter": v} for i, v in enumerate(V[:3])])
    clock.t += TR.VOTE_S
    agent.trade_tick(clock())


def test_the_kill_switch_cancels_a_vote_a_waiting_and_an_unconfirmed_trade(tmp_path):
    agent, world, prov, clock = trade_agent(tmp_path, T.decision())
    agent.ingest_chat([{"seq": 1, "text": "buy wif", "nick": "Marco", "voter": V[0]}])
    (agent.dir / "trading-on").unlink()
    agent.trade_tick(clock())
    assert agent.trade.vote is None
    (agent.dir / "trading-on").write_text("on")
    clock.t += TR.TRADE_GAP_S + TR.COIN_GAP_S + TR.PROPOSER_GAP_S
    voted(agent, clock)
    assert agent.requests.waiting and agent.trade.active
    (agent.dir / "trading-on").unlink()
    agent.trade_tick(clock())
    assert not agent.requests.waiting and agent.trade.active is None
    assert json.loads((agent.dir / "trade-ledger.json").read_text())["rows"][-1]["status"] == "failed"


def test_only_the_trade_request_itself_may_confirm(tmp_path):
    agent, world, prov, clock = trade_agent(tmp_path, T.decision())
    voted(agent, clock)
    agent.deposit_request(clock())                                             # jumps the queue
    agent.requests.current = dict(agent.requests.waiting.popleft(), started=clock(), steps=1, done=False,
                                  commented=False, phase="report")
    click = {"action": "click", "point": [10, 10]}
    dec = {"dropped": [], "trade_confirm": True, "trade_check": {"side": "buy", "symbol": "WIF", "amount_usd": 10}}
    assert agent.trade_guard(dec, click, clock()) is None and "no trade request" in dec["dropped"][0]


def test_a_payment_refusal_while_trading_explains_the_vote(tmp_path):
    agent, world, prov, clock = trade_agent(tmp_path, T.decision())
    assert SA.reply_problem(SA.TRADE_HOWTO_LINE) is None
    agent.refuse_request({"refused": "payment", "seq": 5, "nick": "Marco", "user": "Marco", "kind": "refused",
                          "text": "buy gta 6 coin"}, clock())
    assert any(x.text == SA.TRADE_HOWTO_LINE for x in agent.speech_q)


def test_the_pc_prompt_allows_likes_and_reuses_the_fomo_tab():
    p = SA.system_prompt(pc=True, allow_credentials=True)
    assert "Liking posts, comments or theses" in p and "click that tab instead of opening another" in p


def test_three_unchanged_scrolls_on_the_pc_do_not_hold_him(tmp_path):
    agent, world, prov, clock = trade_agent(tmp_path, T.decision())
    for i in range(4):
        agent.pc.pending = {"key": "scroll:down", "kind": "scroll", "sig": None, "point": None, "runner_changed": False,
                            "outcome": {"action": "scroll down", "verdict": "pending"}}
        agent.track_pc({"url": "https://app.vagon.io"}, clock())
    assert not agent.held and agent.fail_counts["scroll:down"][0] == 4
