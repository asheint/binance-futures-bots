"""News bot (DEMO ONLY): shorts a coin right after Binance announces it will be delisted.

Why: an event study on every Binance delisting announcement since 2023 (133 coin trades, 56 announcements) found that
shorting the coin's USDT perpetual 1 minute after the news and closing 4 hours later made +5.6% per trade on average
after costs, with 70% winners, using a 25% stop-loss (without a stop, one squeeze cost -400%). Entering 15 minutes
late still worked, so speed is not the bottleneck. See LEARNING.md.

Rules:
- watches Binance's "Delisting" announcements every NEWS_POLL_SECONDS
- trades "Binance Will Delist A, B, C on <date>" (spot delisting) and "Binance Futures Will Delist ...USDT"
  (margin-only delistings lost money in the study and are ignored)
- only coins that already have a USDT perpetual on the account's exchange, only news younger than NEWS_MAX_AGE_MIN
- SHORT at market, stop-loss NEWS_STOP_PCT above entry (isolated, NEWS_LEVERAGE), closed after NEWS_HOLD_MIN minutes
- sized so the stop-loss loses NEWS_RISK_USDT
- if the crazy bot holds a LONG on that coin, the news bot closes it first and takes over the coin

  python news_bot.py run                      # watch and trade
  python news_bot.py check                    # recent delisting news and what the bot would do (no trades)
  python news_bot.py test "Binance Will Delist ABC on 2026-10-20"           # dry run of the rules on a headline
  python news_bot.py test "Binance Will Delist ABC on 2026-10-20" --trade   # really trades it on demo, 2-minute hold
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

import bot
import journal
from client import BinanceAPIError
from config import Config, load_config
from models import price_text
from risk import TAKER_FEE, SymbolRules, dec, fmt

NOTE = "news"
DATA_DIR = Path(__file__).resolve().parent / "data"
LOG_PATH = DATA_DIR / "news_bot.log"
STATE_PATH = DATA_DIR / "news_state.json"
CMS_LIST = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
CMS_DETAIL = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query"
DELISTING_CATALOG = 161
HOUSEKEEPING_SECONDS = 20
FEED_SIZE = 30


def setting(name: str, default: str) -> str:
    return os.getenv(name, default).split("#")[0].strip() or default


class Settings:
    def __init__(self) -> None:
        self.risk = float(setting("NEWS_RISK_USDT", "50"))           # lost when the stop-loss is hit
        self.stop = float(setting("NEWS_STOP_PCT", "25")) / 100       # stop-loss this far above the entry
        self.hold = float(setting("NEWS_HOLD_MIN", "240"))           # close this many minutes after entry
        self.leverage = int(setting("NEWS_LEVERAGE", "2"))
        self.poll = float(setting("NEWS_POLL_SECONDS", "2"))
        self.max_age = float(setting("NEWS_MAX_AGE_MIN", "30"))      # older announcements are not traded


def log(message: str) -> None:
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {message}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---- reading the news -------------------------------------------------------------

def parse(title: str, body: str | None = None) -> tuple[str | None, list[str]]:
    """(kind, coins) for a delisting headline the strategy trades; (None, []) for anything else.
    Coins are tickers ("ABC") or, for futures delistings, full symbols ("ABCUSDT")."""
    if re.match(r"Binance Will Delist ", title):
        names = re.sub(r" on \d{4}-\d{2}-\d{2}.*", "", title.replace("Binance Will Delist ", ""))
        coins = [t.strip() for t in re.split(r",\s*|\s+and\s+|\s*&\s*", names)]
        return "spot delisting", [t for t in coins if re.fullmatch(r"[A-Z0-9]{2,15}", t)]
    if "Futures Will Delist" in title:
        symbols = re.findall(r"\b([A-Z0-9]{2,20}USDT)\b", title)
        if not symbols and body:
            symbols = re.findall(r"\b([A-Z0-9]{2,20}USDT)\b", body)
        return "futures delisting", sorted(set(symbols))
    return None, []


class NewsBot:
    def __init__(self, cfg: Config):
        if cfg.env != "demo":
            sys.exit("news_bot.py only runs on the demo account (BINANCE_ENV=demo).")
        self.cfg = cfg
        self.s = Settings()
        self.client = bot.make_client(cfg)
        self.web = requests.Session()
        self.web.headers["User-Agent"] = "Mozilla/5.0"
        self.state = self.load_state()
        self._prepared: dict[str, int] = {}

    # ---- state ------------------------------------------------------------------------

    def load_state(self) -> dict:
        try:
            return {"positions": {}, "seen": [], "feed": [], **json.loads(STATE_PATH.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            return {"positions": {}, "seen": [], "feed": []}

    def save_state(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.state["seen"] = self.state["seen"][-300:]
        self.state["feed"] = self.state["feed"][-FEED_SIZE:]
        STATE_PATH.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def feed(self, item: dict, action: str) -> None:
        self.state["feed"].append({"time": item["time"] / 1000, "title": item["title"], "action": action})

    # ---- Binance announcements ----------------------------------------------------------

    def latest(self, size: int = 10) -> list[dict]:
        data = self.web.get(CMS_LIST, params={"type": 1, "catalogId": DELISTING_CATALOG, "pageNo": 1, "pageSize": size},
                            timeout=10).json()["data"]
        items = data["catalogs"][0]["articles"] if data.get("catalogs") else []
        return [{"code": a["code"], "title": a["title"], "time": a["releaseDate"]} for a in items]

    def body(self, code: str) -> str:
        try:
            data = self.web.get(CMS_DETAIL, params={"articleCode": code}, timeout=10).json()["data"]
            return json.dumps(data.get("body") or "")
        except (requests.RequestException, ValueError, KeyError):
            return ""

    # ---- exchange -------------------------------------------------------------------------

    def resolve(self, kind: str, coins: list[str]) -> dict[str, str]:
        """coin -> USDT perpetual symbol that is trading right now (coins without one are left out)."""
        self.client._symbols = None  # new contracts appear often; read the latest list
        out = {}
        for coin in coins:
            candidates = [coin] if kind == "futures delisting" else [coin + "USDT", "1000" + coin + "USDT"]
            for symbol in candidates:
                try:
                    info = self.client.symbol_info(symbol)
                except ValueError:
                    continue
                if info.get("status") == "TRADING" and info.get("contractType") == "PERPETUAL":
                    out[coin] = symbol
                    break
        return out

    def size(self, symbol: str, price: Decimal) -> tuple[Decimal, int]:
        """Quantity so the stop-loss loses NEWS_RISK_USDT including fees, and the leverage to use."""
        rules = SymbolRules.from_symbol_info(self.client.symbol_info(symbol))
        qty = rules.round_qty(dec(self.s.risk) / (price * (dec(self.s.stop) + TAKER_FEE * 2)))
        if qty * price < rules.min_notional:
            raise ValueError(f"position too small for {symbol} (minimum {fmt(rules.min_notional)} USDT)")
        if qty < rules.min_qty:
            raise ValueError(f"quantity below the minimum for {symbol}")
        leverage = self.s.leverage
        try:
            brackets = next(b["brackets"] for b in self.client.leverage_brackets() if b["symbol"] == symbol)
            leverage = min(leverage, int(brackets[0]["initialLeverage"]))
            if 1 / leverage - float(brackets[0]["maintMarginRatio"]) <= self.s.stop * 1.15:
                raise ValueError(f"liquidation at {leverage}x would be too close to a {self.s.stop:.0%} stop")
        except StopIteration:
            pass
        return qty, leverage

    def take_over(self, symbol: str, pos: dict) -> bool:
        """A LONG from another bot on this coin: close it so the short can be opened. Returns False to skip the coin."""
        amount = float(pos["positionAmt"])
        if amount < 0:
            log(f"{symbol}: already SHORT on the account, nothing to add")
            return False
        log(f"{symbol}: closing an existing LONG ({pos['positionAmt']}) before shorting on the news")
        bot.cancel_symbol_orders(self.client, symbol)
        self.client.new_order(symbol=symbol, side="SELL", type="MARKET", quantity=pos["positionAmt"].lstrip("-"),
                              reduceOnly=True, newOrderRespType="RESULT")
        return True

    def open_short(self, symbol: str, headline: str, hold_minutes: float, test: bool = False) -> str:
        """Returns a short description of what happened (shown in the feed)."""
        if symbol in self.state["positions"]:
            return "already shorting it"
        existing = bot.open_position(self.client, symbol)
        if existing and not self.take_over(symbol, existing):
            return "skipped: already short"
        mark = dec(self.client.mark_price(symbol))
        try:
            qty, leverage = self.size(symbol, mark)
        except ValueError as err:
            log(f"{symbol}: skipped ({err})")
            return f"skipped: {err}"
        _, available = bot.wallet(self.client)
        if qty * mark / leverage > dec(available) * dec("0.95"):
            log(f"{symbol}: skipped, needs {qty * mark / leverage:.2f} USDT margin, {available:.2f} free")
            return "skipped: not enough free margin"
        if self._prepared.get(symbol) != leverage:
            bot.prepare_account(self.client, symbol, leverage)
            self._prepared[symbol] = leverage
        bot.cancel_symbol_orders(self.client, symbol)

        self.client.new_order(symbol=symbol, side="SELL", type="MARKET", quantity=fmt(qty), newOrderRespType="RESULT")
        pos = bot.open_position(self.client, symbol)
        if pos is None or float(pos["positionAmt"]) >= 0:
            log(f"{symbol}: the short did not open")
            return "failed: order did not open a position"
        entry = dec(pos["entryPrice"])
        qty = abs(dec(pos["positionAmt"]))
        rules = SymbolRules.from_symbol_info(self.client.symbol_info(symbol))
        sl = rules.round_price(entry * (1 + dec(self.s.stop)))
        try:
            order = self.place_stop(symbol, sl)
        except BinanceAPIError as err:
            log(f"{symbol}: could not place the stop-loss ({err.msg}); closing the short")
            self.close(symbol, qty)
            return "failed: stop-loss rejected, closed"
        loss = qty * (sl - entry) + entry * qty * TAKER_FEE * 2
        now = time.time()
        self.state["positions"][symbol] = {
            "entry": float(entry), "qty": fmt(qty), "sl": float(sl), "leverage": leverage, "headline": headline,
            "opened_at": int(now * 1000), "close_at": now + hold_minutes * 60, "algo_id": order.get("algoId"),
            "test": test,
        }
        self.save_state()
        journal.log(self.cfg.journal_path, "OPEN", env=self.cfg.env, symbol=symbol, side="SHORT", qty=fmt(qty),
                    price=fmt(rules.round_price(entry)), stop=fmt(sl), leverage=leverage, risk_usdt=f"{loss:.2f}",
                    note=f"{NOTE}{' self-test' if test else ''}: {headline[:90]}")
        log(f"{symbol}: SHORT {fmt(qty)} @ {price_text(float(entry))} {leverage}x | stop {fmt(sl)} (-{loss:.2f}) | "
            f"closes in {hold_minutes:g} min")
        return f"SHORT @ {price_text(float(entry))}, stop {price_text(float(sl))}"

    def place_stop(self, symbol: str, sl: Decimal) -> dict:
        # no priceProtect: in a squeeze the stop must fire even if mark and last price drift apart
        return self.client.new_algo_order(symbol=symbol, side="BUY", type="STOP_MARKET", triggerPrice=fmt(sl),
                                          closePosition=True, workingType="MARK_PRICE")

    def close(self, symbol: str, qty: Decimal | str) -> None:
        bot.cancel_symbol_orders(self.client, symbol)
        pos = bot.open_position(self.client, symbol)
        if pos and float(pos["positionAmt"]) < 0:
            self.client.new_order(symbol=symbol, side="BUY", type="MARKET", quantity=pos["positionAmt"].lstrip("-"),
                                  reduceOnly=True, newOrderRespType="RESULT")

    # ---- a new announcement ------------------------------------------------------------------

    def handle(self, item: dict, trade: bool = True, hold: float | None = None, test: bool = False) -> list[str]:
        kind, coins = parse(item["title"])
        if kind == "futures delisting" and not coins:
            kind, coins = parse(item["title"], self.body(item["code"]) if item.get("code") else "")
        if not kind:
            self.feed(item, "not a trade (margin/other notice)")
            return []
        if not coins:
            self.feed(item, "no coins found in the notice")
            return []
        symbols = self.resolve(kind, coins)
        missing = [c for c in coins if c not in symbols]
        log(f"NEWS ({kind}): {item['title']} -> tradable: {', '.join(symbols.values()) or 'none'}"
            + (f" | no futures contract: {', '.join(missing)}" if missing else ""))
        results = []
        for coin, symbol in symbols.items():
            if not trade:
                try:
                    qty, lev = self.size(symbol, dec(self.client.mark_price(symbol)))
                    mark = self.client.mark_price(symbol)
                    results.append(f"{symbol}: would SHORT {fmt(qty)} (~{float(qty) * mark:.0f} USDT) at {lev}x, "
                                   f"stop +{self.s.stop:.0%}, lose ~{self.s.risk:g} if stopped, close after {hold or self.s.hold:g} min")
                except ValueError as err:
                    results.append(f"{symbol}: would skip ({err})")
                continue
            try:
                results.append(f"{coin}: {self.open_short(symbol, item['title'], hold or self.s.hold, test)}")
            except BinanceAPIError as err:
                log(f"{symbol}: order failed ({err.msg})")
                results.append(f"{coin}: failed ({err.msg})")
        if missing:
            results.append(f"no futures contract: {', '.join(missing)}")
        if trade and not test:
            self.feed(item, " · ".join(results) or "nothing tradable")
        if trade:
            self.save_state()
        return results

    def poll(self) -> None:
        items = self.latest()
        seen = set(self.state["seen"])
        for item in sorted(items, key=lambda a: a["time"]):
            if item["code"] in seen:
                continue
            self.state["seen"].append(item["code"])
            age_min = (time.time() * 1000 - item["time"]) / 60000
            if age_min > self.s.max_age:
                self.feed(item, f"too old to trade ({age_min:.0f} min)")
                continue
            self.handle(item)
        self.state["last_poll"] = time.time()  # the news page shows "last check 2 s ago"
        self.save_state()

    # ---- housekeeping ------------------------------------------------------------------------

    def realized(self, symbol: str, since_ms: int) -> float | None:
        rows = self.client.income(symbol, start_time=since_ms)
        if not any(r["incomeType"] == "REALIZED_PNL" for r in rows):
            # closed at exactly the entry price: zero PnL gets no REALIZED_PNL row, so look for the closing fill
            if not any(t["side"] == "BUY" for t in self.client.user_trades(symbol, start_time=since_ms)):
                return None
        return sum(float(r["income"]) for r in rows if r["incomeType"] in ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE"))

    def housekeeping(self) -> None:
        self.state["heartbeat"] = time.time()
        tracked = self.state["positions"]
        if tracked:
            open_now = {p["symbol"]: p for p in self.client.position_risk() if float(p["positionAmt"]) != 0}
            algo = self.client.open_algo_orders()
            for symbol, pos in list(tracked.items()):
                live = open_now.get(symbol)
                if not live or float(live["positionAmt"]) > 0:
                    if live is None:
                        bot.cancel_symbol_orders(self.client, symbol)
                    pnl = self.realized(symbol, pos["opened_at"])
                    if pnl is None and time.time() * 1000 - pos["opened_at"] < 86_400_000:
                        continue  # closing PnL not booked yet
                    outcome = pos.get("closing") or "stop-loss"
                    journal.log(self.cfg.journal_path, "CLOSE", env=self.cfg.env, symbol=symbol, side="SHORT",
                                qty=pos["qty"], pnl_usdt=f"{(pnl or 0):.2f}",
                                note=f"{NOTE}{' self-test' if pos.get('test') else ''} {outcome}")
                    log(f"{symbol}: news short CLOSED ({outcome}) | net {(pnl or 0):+.2f} USDT after fees")
                    tracked.pop(symbol)
                    continue
                if time.time() >= pos["close_at"] and not pos.get("closing"):
                    log(f"{symbol}: hold time over, closing the short")
                    pos["closing"] = "time exit"
                    self.close(symbol, pos["qty"])
                    continue
                if not any(o["symbol"] == symbol and o.get("orderType") == "STOP_MARKET" for o in algo):
                    log(f"{symbol}: stop-loss missing, re-placing at {price_text(pos['sl'])}")
                    try:
                        pos["algo_id"] = self.place_stop(symbol, dec(pos["sl"])).get("algoId")
                    except BinanceAPIError as err:
                        log(f"{symbol}: re-place failed ({err.msg}); closing the short")
                        pos["closing"] = "protection failed"
                        self.close(symbol, pos["qty"])
        self.save_state()

    # ---- loop --------------------------------------------------------------------------------

    def run(self) -> None:
        log(f"News bot STARTED on DEMO: watching Binance delisting news every {self.s.poll:g}s | short on the news, "
            f"stop +{self.s.stop:.0%}, lose {self.s.risk:g} USDT if stopped, close after {self.s.hold:g} min, "
            f"{self.s.leverage}x isolated")
        if not self.state["seen"]:  # first start: today's older notices are history, not signals
            first = self.latest(20)
            self.state["seen"] = [a["code"] for a in first]
            for a in sorted(first, key=lambda a: a["time"])[-8:]:
                self.feed(a, "before the bot started")
            log(f"First start: marked {len(first)} existing announcements as already seen")
            self.save_state()
        next_housekeeping, errors = 0.0, 0
        while True:
            try:
                self.poll()
                if time.time() >= next_housekeeping:
                    self.housekeeping()
                    next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
                errors = 0
            except (BinanceAPIError, requests.RequestException, ValueError, KeyError) as err:
                errors += 1
                log(f"Error: {err}. Will retry.")
                time.sleep(min(30, 2 * errors))
            time.sleep(self.s.poll)

    def check(self) -> None:
        for item in self.latest(10):
            when = datetime.fromtimestamp(item["time"] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
            print(f"\n{when} UTC  {item['title']}")
            for line in self.handle(item, trade=False) or ["  (the bot would not trade this notice)"]:
                print("   ", line)

    def test(self, headline: str, trade: bool) -> None:
        item = {"code": "", "title": headline, "time": time.time() * 1000}
        results = self.handle(item, trade=trade, hold=2 if trade else None, test=True)
        for line in results or ["the bot would not trade this headline"]:
            print("  ", line)
        if trade and self.state["positions"]:
            log("TEST: waiting for the 2-minute hold to end, then closing")
            while self.state["positions"]:
                time.sleep(HOUSEKEEPING_SECONDS)
                self.housekeeping()
            log("TEST done")


def main() -> None:
    parser = argparse.ArgumentParser(description="Delisting-news short bot (demo only)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="watch Binance delisting news and trade")
    sub.add_parser("check", help="show recent delisting news and what the bot would do")
    t = sub.add_parser("test", help="run the rules on a made-up headline")
    t.add_argument("headline")
    t.add_argument("--trade", action="store_true", help="really open the trades on demo (2-minute hold)")
    args = parser.parse_args()

    news = NewsBot(load_config())
    try:
        if args.command == "run":
            news.run()
        elif args.command == "check":
            news.check()
        else:
            news.test(args.headline, args.trade)
    except KeyboardInterrupt:
        log("Stopped. Open news shorts keep their stop-loss on Binance; restart to handle the time exit.")
    except Exception:
        log("Unexpected error:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
