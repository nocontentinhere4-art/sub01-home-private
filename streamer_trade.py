"""Live trading on fomo.family by chat vote (owner 2026-10-28, after the ToS warning: his account, his money).
Pure, clock-injected pieces; the agent (streamer_agent.py) wires them to chat, its request runner and the model's state.
Design consult with Kimi (docs/streamer/kimi/review-20261028-trade.md, trade1: BLOCK on the platform's ToS, which the
owner accepted, and five technical changes, all taken here):
- coins only from the owner's allowlist of exact {chain, contract address} (no symbol search, nothing pasted from chat);
- a vote counts one answer per voter key (the relay's salted hash of the viewer's connection), never per typed name;
- caps are a ledger that reserves every buy BEFORE it starts and never gives money back (sells free nothing, failures
  and ambiguous attempts stay spent; only the owner resets it), one trade in flight, no automatic retry;
- the model must read the order back from the screen (side, coin, amount) and the code compares it with the voted trade
  before the one confirm click; the owner sets fomo's quick-buy presets to $10 or less once, by hand;
- neutral words: a proposal is a question, never hype; proposals are rate-limited per voter and per coin."""
from __future__ import annotations

import json
import math
import os
import re
import time
from pathlib import Path

USD_PER_TRADE = 10.0            # owner 10-28: max $10 a trade ...
USD_TOTAL = 50.0                # ... and $50 in total, until he resets the ledger himself
VOTE_S = 60.0                   # a trade vote is open this long
VOTE_MIN = 3                    # distinct voters needed, and yes must beat no
TRADE_GAP_S = 300.0             # between the end of one trade and the next vote
PROPOSER_GAP_S = 900.0          # one proposal per voter per 15 min
COIN_GAP_S = 600.0              # the same coin is proposed again only after 10 min
TRADES_PER_DAY = 10
TRADE_STEPS_MAX = 10            # the execution request: clicks to find the coin, the amount, the read-back, the confirm
TRADE_RUN_MAX_S = 180.0
DEPOSIT_SHOW_S = 60.0           # the deposit QR stays on screen this long (owner: shown live)
TRADE_HOST = "fomo.family"
TRADE_URL = "https://fomo.family"

# owner-approved coins (verified 10-28 on DexScreener: exact contract, top-liquidity pair). The file
# streamer/trade-coins.json, written by the owner, replaces this list; a malformed file means no trading at all.
DEFAULT_COINS = (
    {"symbol": "WIF", "name": "dogwifhat", "chain": "solana", "address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"},
    {"symbol": "BONK", "name": "Bonk", "chain": "solana", "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
    {"symbol": "POPCAT", "name": "Popcat", "chain": "solana", "address": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"},
    {"symbol": "PENGU", "name": "Pudgy Penguins", "chain": "solana", "address": "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv"},
    {"symbol": "FARTCOIN", "name": "Fartcoin", "chain": "solana", "address": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"},
    {"symbol": "MEW", "name": "cat in a dogs world", "chain": "solana", "address": "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5"},
    {"symbol": "BRETT", "name": "Brett", "chain": "base", "address": "0x532f27101965dd16442E59d40670FaF5eBB142E4"},
    {"symbol": "PEPE", "name": "Pepe", "chain": "ethereum", "address": "0x6982508145454Ce325dDbE47a25d4ec3d2311933"},
)
CHAINS = ("solana", "base", "ethereum", "bsc")
SYMBOL_RE = re.compile(r"[A-Z0-9]{2,10}")
ADDRESS_RE = re.compile(r"\b(?:0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})\b")
LINK_RE = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|io|fun|xyz|app|net|org|gg|so|family)\b", re.I)

# "buy wif", "buy $BONK", "trade popcat", "sell wif", "sell all bonk": the whole line is the proposal (no "and then")
TRADE_REQ = re.compile(r"^\W*(?:(?:hey\s+)?sub-?01\W+)?(?:(?:can|could|will)\s+you\s+|let'?s\s+|pls\s+|please\s+)?"
                       r"(buy|trade|purchase|get\s+some|sell(?:\s+(?:all|everything|our|your|the|my))?|dump)\s+"
                       r"(?:some\s+|of\s+)?\$?([A-Za-z][A-Za-z0-9 ]{1,24}?)(?:\s+(?:coin|token|now|pls|please))*\W*$", re.I)
TRADE_VERB = re.compile(r"^\W*(?:(?:hey\s+)?sub-?01\W+)?(?:(?:can|could|will)\s+you\s+|let'?s\s+|pls\s+|please\s+)?"
                        r"(?:buy|trade|purchase|get\s+some|sell|dump)\b", re.I)
YES = re.compile(r"^\W*(?:yes|y|yeah|yep|yup|ye|si|sì|do\s+it|go)\W*$", re.I)
NO = re.compile(r"^\W*(?:no|n|nah|nope|don'?t|skip)\W*$", re.I)


# what he says (neutral: a vote is a question, the result a fact; Kimi trade1 d). None: refused silently (spam)
REFUSE_LINES = {
    "address": "No contract addresses from chat. I only trade the coins on my list.",
    "not_listed": "That coin is not on my list, so no trade on that one.",
    "budget": "The trading budget is used up for now.",
    "cooldown": "One trade every few minutes, chat. Hold on.",
    "daily": "That's enough trades for today.",
    "not_held": "We don't hold that one, nothing to sell.",
    "busy": None, "proposer": None, "coin": None, "anonymous": None, "off": None,
}


LEDGER_LINE = "Trading is paused, my budget notes failed to save. No trade."


def vote_line(t):
    s = t["coin"]["symbol"]
    if t["side"] == "buy":
        return f"Chat vote: buy {t['usd']:g} dollars of {s}? Type yes or no, one minute."
    return f"Chat vote: sell all of our {s}? Type yes or no, one minute."


def result_line(t, passed, yes, no):
    if passed:
        return f"Chat voted yes, {yes} to {no}. Placing it now. Chat's call, not financial advice."
    if yes + no < VOTE_MIN:
        n = yes + no
        return f"Only {n} vote{'s' if n != 1 else ''}, not enough. No trade."
    return f"Chat voted no, {yes} to {no}. No trade."


def load_coins(path):
    """The allowlist: the owner's file if it exists (every entry valid, else None: no trading), else DEFAULT_COINS."""
    p = Path(path)
    if not p.exists():
        return [dict(c) for c in DEFAULT_COINS]
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    out = []
    for c in data if isinstance(data, list) else []:
        if not isinstance(c, dict):
            return None
        sym, chain, addr = str(c.get("symbol") or "").upper(), str(c.get("chain") or ""), str(c.get("address") or "")
        if not SYMBOL_RE.fullmatch(sym) or chain not in CHAINS or not ADDRESS_RE.fullmatch(addr):
            return None
        out.append({"symbol": sym, "name": str(c.get("name") or sym)[:40], "chain": chain, "address": addr})
    return out or None


def find_coin(coins, word):
    w = " ".join(str(word or "").lower().replace("$", "").split())
    for c in coins or ():
        if w in (c["symbol"].lower(), c["name"].lower()):
            return c
    return None


def parse_trade(text, coins):
    """A chat line -> {"side": "buy"|"sell", "coin": {...}} | {"refused": why} | None (not a trade line).
    why: address (a contract or link pasted), not_listed (a coin outside the owner's list)."""
    t = " ".join(str(text or "").split())
    if TRADE_VERB.match(t) and (ADDRESS_RE.search(t) or LINK_RE.search(t)):
        return {"refused": "address"}                   # "buy 3Zv...pump": a pasted contract, never looked up
    m = TRADE_REQ.match(t)
    if not m:
        return None
    verb = m.group(1).lower()
    side = "sell" if verb.startswith(("sell", "dump")) else "buy"
    coin = find_coin(coins, m.group(2))
    if coin is None:                                    # "buy shib" gets one line; "buy me a coffee" is not a trade
        word = m.group(2).strip()
        if " " in word or len(word) > 10 or word.lower() in ("everything", "all", "it", "this", "that", "them", "now"):
            return None
        return {"refused": "not_listed", "side": side}
    return {"side": side, "coin": coin}


def vote_answer(text):
    if YES.match(str(text or "")):
        return "yes"
    if NO.match(str(text or "")):
        return "no"
    return None


def read_back_problem(check, trade):
    """The model's reading of fomo's order screen just before the confirm click, compared with the voted trade.
    None when it matches; else why (the confirm click is then refused)."""
    if not isinstance(check, dict):
        return "no read-back"
    side = str(check.get("side") or "").lower()
    sym = str(check.get("symbol") or "").upper().lstrip("$")
    try:
        usd = float(check.get("amount_usd"))
    except (TypeError, ValueError):
        return "no amount read"
    if side != trade["side"]:
        return "wrong side"
    if sym != trade["coin"]["symbol"]:
        return "wrong coin"
    if trade["side"] == "buy" and not 0 < usd <= trade["usd"] + 0.01:
        return "amount above the voted amount"
    if trade["side"] == "sell" and not usd >= 0:
        return "bad amount"
    return None


NUMBERISH = re.compile(r"[\s$€£.,'_+\-0-9]*[0-9][\s$€£.,'_+\-0-9]*|[\s$]*[0-9.]+[eE][+-]?[0-9]+\s*")   # a number, "1e3" too
CANONICAL = re.compile(r"\$?\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)")             # "10", "$9.5", "7.25": nothing else


def amount_typed_problem(text, trade):
    """A number typed while trading is on: only a plain amount (Kimi trade2 3: "1,000", "100.", "1e3" are refused as
    ambiguous), at most the voted amount during a buy and never above USD_PER_TRADE. Text with letters is not an amount."""
    t = str(text or "").strip()
    if not NUMBERISH.fullmatch(t):
        return None
    m = CANONICAL.fullmatch(t)
    if not m:
        return "ambiguous amount"
    cap = trade["usd"] if trade and trade.get("side") == "buy" else USD_PER_TRADE
    return None if float(m.group(1)) <= cap + 1e-9 else f"amount above ${cap:g}"


class Ledger:
    """Money committed to trades. reserve() before a buy starts; the amount stays spent whatever happens (Kimi trade1
    e: pending and ambiguous count, sells never give budget back). Only the owner resets it (by editing the file).
    Saved atomically; a malformed file counts as the whole budget spent (fail closed)."""

    STATUSES = ("pending", "done", "failed", "unknown")

    def __init__(self, path, wall=time.time):
        self.path, self.wall = Path(path), wall
        self.rows, self.broken = [], False
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                rows = data["rows"]
                if not isinstance(rows, list) or not all(self.row_ok(r) for r in rows):
                    raise ValueError("bad rows")
                self.rows = rows
            except (OSError, ValueError, KeyError, AttributeError, TypeError):
                self.rows, self.broken = [], True     # Kimi trade2 5: anything invalid means the whole budget is spent

    @classmethod
    def row_ok(cls, r):
        try:
            usd, t = r["usd"], r["t"]
            return (isinstance(r, dict) and isinstance(r["id"], str) and r["side"] in ("buy", "sell")
                    and r["status"] in cls.STATUSES and isinstance(r["symbol"], str)
                    and type(usd) in (int, float) and math.isfinite(usd) and 0 <= usd <= USD_TOTAL
                    and type(t) in (int, float) and math.isfinite(t) and t > 0)
        except (KeyError, TypeError):
            return False

    def spent(self):
        if self.broken:
            return USD_TOTAL
        return round(sum(float(r.get("usd") or 0) for r in self.rows if r.get("side") == "buy"), 2)

    def next_buy_usd(self):
        """The amount the next buy may use: min(per trade, what is left), or 0."""
        left = USD_TOTAL - self.spent()
        return round(min(USD_PER_TRADE, left), 2) if left >= 1.0 else 0.0

    def trades_today(self):
        day = time.strftime("%Y-%m-%d", time.gmtime(self.wall()))
        return sum(1 for r in self.rows if time.strftime("%Y-%m-%d", time.gmtime(float(r.get("t") or 0))) == day)

    def holds(self, symbol):
        """A coin with a buy since its last sell (what a sell vote may sell)."""
        state = False
        for r in self.rows:
            if r.get("symbol") == symbol and r.get("status") in ("done", "pending", "unknown"):
                state = r.get("side") == "buy"
        return state

    def reserve(self, trade):
        """The row, saved before anything is ordered; None when it could not be saved (Kimi trade2 4: the trade is
        aborted and the ledger counts as broken, so a restart cannot reuse the budget)."""
        row = {"id": trade["id"], "t": self.wall(), "side": trade["side"], "symbol": trade["coin"]["symbol"],
               "chain": trade["coin"]["chain"], "usd": trade["usd"] if trade["side"] == "buy" else 0.0, "status": "pending"}
        self.rows.append(row)
        if not self.save():
            self.broken = True
            return None
        return row

    def settle(self, trade_id, status):
        for r in self.rows:
            if r["id"] == trade_id:
                r["status"] = status                 # done | failed | unknown: the money stays counted either way
        self.save()

    def save(self):
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as f:
                f.write(json.dumps({"schema": "sub01.trade-ledger.v1", "usd_total": USD_TOTAL, "rows": self.rows}))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            return True
        except OSError:
            self.broken = True
            return False

    def public(self):
        return {"spent": self.spent(), "cap": USD_TOTAL, "per_trade": USD_PER_TRADE}


class TradeDesk:
    """Proposals, the vote and the hand-over to the request runner. One vote or one trade at a time."""

    def __init__(self, ledger, coins, clock):
        self.ledger, self.coins, self.clock = ledger, coins, clock
        self.vote = None                     # {"trade", "until", "votes": {voter: yes|no}}
        self.active = None                   # the trade being executed (request kind "trade")
        self.last_end = -1e9
        self.by_voter, self.by_coin = {}, {}
        self.seq = 0

    def propose(self, parsed, voter, nick, now):
        """-> ("open", trade) | ("refused", why). why: off, busy, cooldown, proposer, coin, daily, budget, not_held."""
        if self.coins is None:
            return "refused", "off"
        if self.vote is not None or self.active is not None:
            return "refused", "busy"
        if now - self.last_end < TRADE_GAP_S:
            return "refused", "cooldown"
        if not voter:
            return "refused", "anonymous"
        if now - self.by_voter.get(voter, -1e9) < PROPOSER_GAP_S:
            return "refused", "proposer"
        sym = parsed["coin"]["symbol"]
        if now - self.by_coin.get(sym, -1e9) < COIN_GAP_S:
            return "refused", "coin"
        if self.ledger.trades_today() >= TRADES_PER_DAY:
            return "refused", "daily"
        if parsed["side"] == "buy":
            usd = self.ledger.next_buy_usd()
            if usd <= 0:
                return "refused", "budget"
        else:
            if not self.ledger.holds(sym):
                return "refused", "not_held"
            usd = 0.0
        self.seq += 1
        trade = {"id": f"t{int(self.clock())}-{self.seq}", "side": parsed["side"], "coin": parsed["coin"], "usd": usd,
                 "nick": nick or ""}
        self.by_voter[voter], self.by_coin[sym] = now, now
        self.vote = {"trade": trade, "until": now + VOTE_S, "votes": {}}
        return "open", trade

    def answer(self, voter, text, now):
        """A chat line during the vote: counted (latest answer per voter) -> True, or not a vote answer -> False."""
        if self.vote is None or now >= self.vote["until"] or not voter:
            return False
        a = vote_answer(text)
        if a is None:
            return False
        self.vote["votes"][voter] = a
        return True

    def tally(self, now):
        """When the vote is over: (trade, passed, yes, no), and the trade becomes active if it passed. Else None."""
        v = self.vote
        if v is None or now < v["until"]:
            return None
        self.vote = None
        yes = sum(1 for a in v["votes"].values() if a == "yes")
        no = len(v["votes"]) - yes
        passed = len(v["votes"]) >= VOTE_MIN and yes > no
        trade = v["trade"]
        if passed:
            if trade["side"] == "buy":                       # the budget may have moved: re-checked, then reserved
                trade["usd"] = min(trade["usd"], self.ledger.next_buy_usd())
                if trade["usd"] <= 0:
                    passed = False
            if passed:
                trade.update(confirmed=False, check=None)
                if self.ledger.reserve(trade) is None:      # not saved: nothing is ordered
                    passed = False
                    trade["error"] = "ledger"
                else:
                    self.active = trade
        if not passed:
            self.last_end = now
        return trade, passed, yes, no

    def cancel(self, now):
        """The kill switch (Kimi trade2 1): an open vote is dropped and an unconfirmed active trade ends as failed.
        -> the ended trade (or None)."""
        self.vote = None
        t = self.active
        if t is not None and not t["confirmed"]:
            return self.finish("failed", now)
        return None

    def confirm_ok(self, check):
        """The one confirm click: allowed once, only after a matching read-back."""
        t = self.active
        if t is None or t["confirmed"]:
            return "no trade to confirm" if t is None else "already confirmed (no retry)"
        why = read_back_problem(check, t)
        if why is None:
            t["confirmed"], t["check"] = True, dict(check)
        return why

    def finish(self, status, now):
        """The trade request ended: done (the model saw it filled), failed (never confirmed) or unknown."""
        t, self.active = self.active, None
        if t is not None:
            st = status if t["confirmed"] else "failed"
            self.ledger.settle(t["id"], st)
            self.last_end = now
            return dict(t, status=st)
        return None

    def state(self, now):
        """What the model sees."""
        out = {}
        if self.vote is not None:
            t = self.vote["trade"]
            out["trade_vote"] = {"side": t["side"], "symbol": t["coin"]["symbol"], "usd": t["usd"],
                                 "votes": len(self.vote["votes"]), "seconds_left": round(max(0.0, self.vote["until"] - now))}
        if self.active is not None:
            t = self.active
            out["trade"] = {"side": t["side"], "symbol": t["coin"]["symbol"], "name": t["coin"]["name"],
                            "chain": t["coin"]["chain"], "address": t["coin"]["address"], "usd": t["usd"],
                            "confirmed": t["confirmed"]}
        return out
