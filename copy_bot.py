"""Copy bot (SHADOW ONLY, places no orders): finds the Binance lead traders worth copying by their REAL trade history,
then copies the best ones on paper to measure what a follower would actually have earned.

Scout (once a day, or "Scout now" on the page):
1. Candidates: the top of Binance's copy-trading board sorted by ROI, PnL, Sharpe and copier PnL (90 days).
2. Hard filters, each with a reason on the page: too new, deep drawdown, hides positions (can't be copied live),
   idle, small account, few trades, profit factor too low, "too perfect" win rate (losers kept open never show in
   the closed history), "no-stop" pattern (many small wins, rare huge loss), one lucky trade making most of the
   profit, very high leverage, and big unrealized losses sitting in their open positions right now.
3. Score = profit factor (max 5) x (0.5 + share of winning weeks) x (1 - drawdown) x trade-count factor.
   The board's ROI is ignored: it's the number that's easiest to game.
Shadow (every COPY_POLL seconds):
- polls the open positions of the COPY_FOLLOW best traders
- a NEW position is copied on paper at the current mark price with COPY_NOTIONAL USDT; positions they already held
  when we started following are skipped (we would have entered late)
- when they cut the position we cut the same share; when they close it we close; adds are ignored
- our own safety stop closes a copy that moves COPY_STOP_PCT % against us (many lead traders use no stop)
- fees 0.05% per side
Data comes from the endpoints behind Binance's copy-trading web pages. They are unofficial and can change any time.

  python copy_bot.py scout      # rank the lead traders now and print the result
  python copy_bot.py run        # scout daily and shadow-copy the best ones; the page is http://127.0.0.1:8000/copy
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

from client import BinanceAPIError, FuturesClient
from config import BASE_URLS

BOARD_URL = "https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade"
HEADERS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "clienttype": "web"}
DATA_DIR = Path(__file__).resolve().parent / "data"
LOG_PATH = DATA_DIR / "copy_bot.log"
STATE_PATH = DATA_DIR / "copy_state.json"
SCOUT_PATH = DATA_DIR / "copy_scout.json"
SCOUT_FLAG = DATA_DIR / "copy_scout_now.flag"  # page: "Scout now" was pressed
SORTS = ("ROI", "PNL", "SHARP_RATIO", "COPIER_PNL")
FEE = 0.0005
REQUEST_GAP = 0.35  # seconds between calls to Binance's web endpoints: stay polite
DAY_MS = 86_400_000


def setting(name: str, default: str) -> str:
    return os.getenv(name, default).split("#")[0].strip() or default


class Settings:
    def __init__(self) -> None:
        self.follow = int(setting("COPY_FOLLOW", "8"))                 # traders shadow-copied at once
        self.notional = float(setting("COPY_NOTIONAL", "100"))         # paper position size per copy, USDT
        self.stop_pct = float(setting("COPY_STOP_PCT", "8"))           # our safety stop: % against the copy
        self.poll = int(setting("COPY_POLL", "60"))                    # seconds between position checks
        self.rescout_h = float(setting("COPY_RESCOUT_H", "24"))        # hours between scouts
        self.pages = int(setting("COPY_BOARD_PAGES", "3"))             # 30 traders per page and sort
        self.min_days = int(setting("COPY_MIN_DAYS", "60"))            # portfolio age
        self.min_trades = int(setting("COPY_MIN_TRADES", "40"))
        self.max_mdd = float(setting("COPY_MAX_DRAWDOWN", "40"))       # %, 90-day max drawdown
        self.max_leverage = float(setting("COPY_MAX_LEVERAGE", "25"))  # average leverage of their trades
        self.min_balance = float(setting("COPY_MIN_BALANCE", "1000"))  # USDT in the lead account (skin in the game)
        self.max_win_rate = float(setting("COPY_MAX_WIN_RATE", "90"))  # above this, losers are likely kept open


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


# ---- Binance copy-trading board (public web endpoints) ---------------------------------------

class BoardError(Exception):
    pass


class LeadBoard:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last = 0.0

    def _call(self, method: str, path: str, **kwargs) -> object:
        wait = self._last + REQUEST_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        resp = self.session.request(method, f"{BOARD_URL}/{path}", timeout=15, **kwargs)
        try:
            body = resp.json()
        except ValueError:
            raise BoardError(f"HTTP {resp.status_code}: not JSON") from None
        if body.get("code") != "000000":
            raise BoardError(f"{path}: {body.get('message') or body.get('code')}")
        return body.get("data")

    def board(self, sort: str, page: int) -> list[dict]:
        data = self._call("POST", "home-page/query-list", json={
            "pageNumber": page, "pageSize": 30, "timeRange": "90D", "dataType": sort, "favoriteOnly": False,
            "hideFull": False, "nickname": "", "order": "DESC", "userAsset": 0, "portfolioType": "PUBLIC"})
        return (data or {}).get("list") or []

    def detail(self, portfolio_id: str) -> dict:
        return self._call("GET", "lead-portfolio/detail", params={"portfolioId": portfolio_id}) or {}

    def history(self, portfolio_id: str, limit: int = 300) -> list[dict]:
        """Closed positions, newest first."""
        out: list[dict] = []
        page = 1
        while len(out) < limit:
            data = self._call("POST", "lead-portfolio/position-history",
                              json={"portfolioId": portfolio_id, "pageNumber": page, "pageSize": 100}) or {}
            rows = data.get("list") or []
            out += rows
            if len(rows) < 100 or len(out) >= int(data.get("total") or 0):
                break
            page += 1
        return out[:limit]

    def positions(self, portfolio_id: str) -> list[dict]:
        rows = self._call("GET", "lead-data/positions", params={"portfolioId": portfolio_id}) or []
        return [p for p in rows if float(p.get("positionAmount") or 0) != 0]


# ---- scout -------------------------------------------------------------------------------------

def trade_stats(trades: list[dict]) -> dict:
    pnls = [float(t["closingPnl"]) for t in trades]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
    avg_win = statistics.mean(wins) if wins else 0.0
    profit = sum(wins)
    leverage = [float(t["leverage"]) for t in trades if t.get("leverage")]
    hold = [(t["closed"] - t["opened"]) / 3_600_000 for t in trades if t.get("closed") and t.get("opened")]
    return {"trades": len(pnls), "win_rate": len(wins) / len(pnls) * 100 if pnls else 0.0,
            "pf": profit / abs(sum(losses)) if losses and sum(losses) else (99.0 if wins else 0.0),
            "worst_in_wins": (min(losses) / avg_win * -1) if losses and avg_win else 0.0,  # biggest loss = N average wins
            "luck": max(wins) / sum(pnls) * 100 if wins and sum(pnls) > 0 else 0.0,       # best trade share of net profit
            "leverage": statistics.mean(leverage) if leverage else 0.0,
            "hold_h": statistics.median(hold) if hold else 0.0, "net": sum(pnls)}


def winning_weeks(chart: list[dict]) -> float | None:
    """Share of 7-day periods in the 90-day ROI curve that ended higher."""
    equity = [1 + float(p["value"]) / 100 for p in chart if p.get("dataType") == "ROI"]
    weeks = [(equity[i + 7], equity[i]) for i in range(0, len(equity) - 7, 7) if equity[i] > 0]
    moved = [(a, b) for a, b in weeks if abs(a / b - 1) > 1e-9]  # ignore flat weeks (not trading yet)
    return sum(a > b for a, b in moved) / len(moved) if moved else None


def reject_reason(row: dict, s: Settings) -> str:
    if row["days"] < s.min_days:
        return f"too new ({row['days']:.0f} days)"
    if row["mdd"] > s.max_mdd:
        return f"deep drawdown ({row['mdd']:.0f}%)"
    return ""


def scout(board: LeadBoard, s: Settings, progress=None) -> dict:
    now_ms = time.time() * 1000
    seen: dict[str, dict] = {}
    for sort in SORTS:
        for page in range(1, s.pages + 1):
            for item in board.board(sort, page):
                seen.setdefault(item["leadPortfolioId"], item)
    rows = []
    for n, (pid, item) in enumerate(seen.items(), 1):
        row = {"id": pid, "nickname": item.get("nickname") or pid[-6:], "roi": float(item.get("roi") or 0),
               "pnl": float(item.get("pnl") or 0), "mdd": float(item.get("mdd") or 0),
               "board_win_rate": float(item.get("winRate") or 0), "copiers": item.get("currentCopyCount") or 0,
               "days": (now_ms - float(item.get("startTime") or now_ms)) / DAY_MS,
               "weeks_up": winning_weeks(item.get("chartItems") or []), "score": None}
        reason = reject_reason(row, s)
        try:
            if not reason:
                d = board.detail(pid)
                row.update(show=bool(d.get("positionShow")), balance=float(d.get("marginBalance") or 0),
                           idle_days=(now_ms - float(d.get("lastTradeTime") or 0)) / DAY_MS, tags=d.get("tag") or [])
                if not row["show"]:
                    reason = "hides positions (can't be copied live)"
                elif d.get("status") != "ACTIVE":
                    reason = f"not active ({d.get('status')})"
                elif row["idle_days"] > 7:
                    reason = f"idle {row['idle_days']:.0f} days"
                elif row["balance"] < s.min_balance:
                    reason = f"small account ({row['balance']:,.0f} USDT)"
            if not reason:
                row.update(trade_stats(board.history(pid)))
                if row["trades"] < s.min_trades:
                    reason = f"only {row['trades']} trades"
                elif row["pf"] < 1.3:
                    reason = f"profit factor {row['pf']:.2f}"
                elif row["win_rate"] >= s.max_win_rate:
                    # closed history only shows closed trades: near-100% winners usually means losers are kept open
                    reason = f"too perfect: {row['win_rate']:.0f}% winners (losers likely held open)"
                elif row["win_rate"] >= 75 and row["worst_in_wins"] >= 5:
                    reason = f"no-stop pattern: one loss = {row['worst_in_wins']:.0f} wins"
                elif row["luck"] > 50:
                    reason = f"one lucky trade = {row['luck']:.0f}% of profit"
                elif row["leverage"] > s.max_leverage:
                    reason = f"high leverage ({row['leverage']:.0f}x avg)"
            if not reason:
                row["open_pnl"] = sum(float(p.get("unrealizedProfit") or 0) for p in board.positions(pid))
                if row["net"] > 0 and row["open_pnl"] < -0.3 * row["net"]:
                    reason = f"holding big losers (open {row['open_pnl']:,.0f} USDT vs {row['net']:,.0f} closed profit)"
        except (BoardError, requests.RequestException, ValueError, KeyError) as err:
            reason = f"data error ({err})"
        if not reason:
            weeks = row["weeks_up"] if row["weeks_up"] is not None else 0.5
            row["score"] = min(row["pf"], 5) * (0.5 + weeks) * (1 - row["mdd"] / 100) * min(1.0, row["trades"] / 100)
        row["reason"] = reason
        rows.append(row)
        if progress:
            progress(n, len(seen))
    rows.sort(key=lambda r: (bool(r["reason"]), -(r["score"] or 0), -r["roi"]))
    result = {"time": time.time(), "candidates": len(rows), "passed": sum(not r["reason"] for r in rows), "rows": rows}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCOUT_PATH.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    return result


# ---- shadow copying -------------------------------------------------------------------------------

class CopyBot:
    def __init__(self) -> None:
        self.s = Settings()
        self.board = LeadBoard()
        self.market = FuturesClient("", "", BASE_URLS["live"])  # mark prices when a leader closes
        self.state = self.load_state()
        self._scout_thread: threading.Thread | None = None
        self._scout_result: dict | None = None
        self._scout_error: str | None = None

    def load_state(self) -> dict:
        base = {"following": [], "picked": [], "traders": {}, "baseline": {}, "open": {}, "closed": [], "last_scout": None,
                "next_scout": 0, "scouting": False}
        try:
            return {**base, **json.loads(STATE_PATH.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            return base

    def save_state(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.state["closed"] = self.state["closed"][-500:]
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")
        for _ in range(10):
            try:
                tmp.replace(STATE_PATH)
                return
            except PermissionError:  # Windows: the dashboard is reading the file this instant
                time.sleep(0.1)
        # still busy: keep the old file, the next loop (3 s) saves again

    # ---- scouting in the background (it takes a few minutes), so copies keep being managed --------

    def start_scout(self) -> None:
        if self._scout_thread and self._scout_thread.is_alive():
            return
        log("Scouting: reading the lead-trader board and each candidate's trade history...")
        self.state["scouting"] = True

        def work() -> None:
            try:
                self._scout_result = scout(LeadBoard(), self.s)
            except Exception as err:  # noqa: BLE001  any failure must end the scout, or it would look busy forever
                self._scout_error = f"{type(err).__name__}: {err}"
        self._scout_thread = threading.Thread(target=work, daemon=True)
        self._scout_thread.start()

    def finish_scout(self) -> None:
        if self._scout_error:
            log(f"Scout failed ({self._scout_error}); will retry in an hour")
            self._scout_error = None
            self.state.update(scouting=False, next_scout=time.time() + 3600)
            return
        result, self._scout_result = self._scout_result, None
        if result is None:
            return
        picked = [r for r in result["rows"] if not r["reason"]][:self.s.follow]
        busy = {pos["trader"] for pos in self.state["open"].values()}  # keep following until their copies close
        picked_ids = [r["id"] for r in picked]
        following = picked_ids + [t for t in self.state["following"] if t in busy and t not in picked_ids]
        for r in picked:
            self.state["traders"][r["id"]] = {k: r.get(k) for k in ("nickname", "score", "pf", "trades", "win_rate", "mdd",
                                                                   "roi", "weeks_up", "leverage", "copiers", "days")}
        new = [r["nickname"] for r in picked if r["id"] not in self.state["following"]]
        dropped = [self.state["traders"].get(t, {}).get("nickname", t) for t in self.state["following"] if t not in following]
        for t in set(self.state["following"]) - set(following):
            self.state["baseline"].pop(t, None)
        self.state.update(following=following, picked=picked_ids, last_scout=result["time"], scouting=False,
                          next_scout=time.time() + self.s.rescout_h * 3600)
        log(f"Scout done: {result['candidates']} lead traders read, {result['passed']} passed the filters, following "
            f"{len(picked)}" + (f" | new: {', '.join(new)}" if new else "") + (f" | dropped: {', '.join(dropped)}" if dropped else ""))

    # ---- positions --------------------------------------------------------------------------------

    def poll(self) -> None:
        for trader in list(self.state["following"]):
            try:
                live = {f"{trader}:{p['symbol']}:{'LONG' if float(p['positionAmount']) > 0 else 'SHORT'}": p
                        for p in self.board.positions(trader)}
            except (BoardError, requests.RequestException, ValueError) as err:
                log(f"{self.name(trader)}: positions unavailable ({err})")
                continue
            if trader not in self.state["baseline"]:
                # first look: what they already hold was bought before we followed, so it is not copied
                self.state["baseline"][trader] = sorted(live)
                if live:
                    log(f"{self.name(trader)}: following; {len(live)} position(s) they already hold are skipped (we'd be late)")
                continue
            baseline = set(self.state["baseline"][trader]) & set(live)  # once they close it, a new one counts
            for key, p in live.items():
                if key in self.state["open"]:
                    if self.manage(key, p):
                        baseline.add(key)  # our stop closed it: don't copy the same position again
                elif key not in baseline:
                    self.open_copy(key, trader, p)
            for key in [k for k, pos in self.state["open"].items() if pos["trader"] == trader and k not in live]:
                self.close_copy(key, self.price(self.state["open"][key]), "leader closed")
            self.state["baseline"][trader] = sorted(baseline)
        # traders dropped by the last scout are followed only until their copies are closed
        busy = {pos["trader"] for pos in self.state["open"].values()}
        self.state["following"] = [t for t in self.state["following"] if t in self.state["picked"] or t in busy]
        self.state["last_poll"] = time.time()

    def name(self, trader: str) -> str:
        return self.state["traders"].get(trader, {}).get("nickname") or trader[-6:]

    def price(self, pos: dict) -> float:
        try:
            return float(self.market.mark_price(pos["symbol"]))
        except (BinanceAPIError, requests.RequestException, ValueError):
            return pos["mark"]

    def open_copy(self, key: str, trader: str, p: dict) -> None:
        mark = float(p["markPrice"])
        if mark <= 0:
            return
        side = "LONG" if float(p["positionAmount"]) > 0 else "SHORT"
        self.state["open"][key] = {
            "trader": trader, "nickname": self.name(trader), "symbol": p["symbol"], "side": side,
            "entry": mark, "mark": mark, "leader_entry": float(p["entryPrice"]), "leader_amount": abs(float(p["positionAmount"])),
            "leverage": p.get("leverage"), "share": 1.0, "realized": -self.s.notional * FEE,
            "opened_at": time.time(), "upnl": 0.0}
        log(f"{self.name(trader)}: COPY {side} {p['symbol']} @ {mark:.6g} on paper ({self.s.notional:g} USDT) | "
            f"their entry {float(p['entryPrice']):.6g}, {p.get('leverage')}x")

    def manage(self, key: str, p: dict) -> bool:
        """Follow the leader's size down and apply our safety stop. True when our stop closed the copy."""
        pos = self.state["open"][key]
        pos["mark"] = float(p["markPrice"])
        sign = 1 if pos["side"] == "LONG" else -1
        against = (pos["entry"] - pos["mark"]) / pos["entry"] * 100 * sign
        if against >= self.s.stop_pct:
            self.close_copy(key, pos["mark"], f"our {self.s.stop_pct:g}% stop")
            return True
        target = min(pos["share"], abs(float(p["positionAmount"])) / pos["leader_amount"])
        if target <= pos["share"] - 0.05:  # they took some off: we take off the same share
            self.book(pos, pos["share"] - target, pos["mark"])
            log(f"{pos['nickname']}: {pos['symbol']} cut to {target:.0%} (leader reduced)")
        pos["upnl"] = self.qty(pos) * pos["share"] * (pos["mark"] - pos["entry"]) * sign
        return False

    def qty(self, pos: dict) -> float:
        return self.s.notional / pos["entry"]

    def book(self, pos: dict, share: float, price: float) -> None:
        sign = 1 if pos["side"] == "LONG" else -1
        qty = self.qty(pos) * share
        pos["realized"] += qty * (price - pos["entry"]) * sign - qty * price * FEE
        pos["share"] -= share

    def close_copy(self, key: str, price: float, reason: str) -> None:
        pos = self.state["open"].pop(key)
        self.book(pos, pos["share"], price)
        self.state["closed"].append({k: pos[k] for k in ("trader", "nickname", "symbol", "side", "entry", "leader_entry", "opened_at")}
                                    | {"exit": price, "closed_at": time.time(), "pnl": pos["realized"], "reason": reason})
        log(f"{pos['nickname']}: {pos['side']} {pos['symbol']} CLOSED ({reason}) | net {pos['realized']:+.2f} USDT on paper")

    # ---- loop -------------------------------------------------------------------------------------

    def run(self) -> None:
        beat = self.state.get("heartbeat") or 0
        if time.time() - beat < 15:
            sys.exit(f"Another copy bot is already running (it updated {time.time() - beat:.0f} s ago). Close it first.")
        log(f"Copy bot STARTED (shadow only, no orders): follows the best {self.s.follow} lead traders, "
            f"{self.s.notional:g} USDT per paper copy, safety stop {self.s.stop_pct:g}%, checks every {self.s.poll}s")
        self.state["scouting"] = False
        next_poll = 0.0
        while True:
            try:
                if SCOUT_FLAG.exists():
                    SCOUT_FLAG.unlink(missing_ok=True)
                    self.state["next_scout"] = 0
                if time.time() >= (self.state.get("next_scout") or 0) and not self.state["scouting"]:
                    self.start_scout()
                if self._scout_result is not None or self._scout_error:
                    self.finish_scout()
                if time.time() >= next_poll and self.state["following"]:
                    self.poll()
                    next_poll = time.time() + self.s.poll
            except (BoardError, requests.RequestException, ValueError) as err:
                log(f"Error: {err}. Will retry.")
            self.state["heartbeat"] = time.time()
            self.save_state()
            time.sleep(3)


def print_scout(result: dict) -> None:
    print(f"\n{result['candidates']} lead traders read, {result['passed']} passed\n")
    for r in result["rows"][:40]:
        verdict = f"score {r['score']:.2f}  PF {r['pf']:.2f}  {r['trades']} trades" if not r["reason"] else r["reason"]
        name = r["nickname"].encode("ascii", "replace").decode()
        print(f"{name[:18]:<18} ROI {r['roi']:>8.0f}%  DD {r['mdd']:>4.0f}%  {r['days']:>4.0f}d  | {verdict}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy bot: rank Binance lead traders and shadow-copy the best (no orders)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scout", help="rank the lead traders now")
    sub.add_parser("run", help="scout daily and shadow-copy the best traders")
    args = parser.parse_args()
    try:
        if args.command == "scout":
            print_scout(scout(LeadBoard(), Settings(), progress=lambda n, total: print(f"\r  {n}/{total}", end="", flush=True)))
        else:
            CopyBot().run()
    except KeyboardInterrupt:
        log("Stopped. Nothing to close: the copy bot only trades on paper.")
    except Exception:
        log("Unexpected error:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
