"""Downloads historical candles from the REAL Binance futures market (public data, no keys needed).

  python data.py                                  # BTCUSDT + ETHUSDT, 1h + 4h, 3 years
  python data.py SOLUSDT --intervals 15m 1h --years 1

Files go to data/<SYMBOL>_<interval>.csv. Running again only downloads the new candles.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from client import FuturesClient
from config import BASE_URLS
from models import Candle

DATA_DIR = Path(__file__).resolve().parent / "data"
FIELDS = ["time", "open", "high", "low", "close", "volume"]
UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
BATCH = 1500


def csv_path(symbol: str, interval: str, directory: Path = DATA_DIR) -> Path:
    return directory / f"{symbol}_{interval}.csv"


def load_candles(symbol: str, interval: str, directory: Path = DATA_DIR) -> list[Candle]:
    path = csv_path(symbol, interval, directory)
    if not path.exists():
        raise FileNotFoundError(f"No data for {symbol} {interval}. Run: python data.py {symbol} --intervals {interval}")
    with path.open(newline="") as f:
        return [Candle(int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                       float(r["volume"])) for r in csv.DictReader(f)]


def download(client: FuturesClient, symbol: str, interval: str, years: float,
             directory: Path = DATA_DIR) -> tuple[int, int]:
    """Returns (new candles, total candles)."""
    path = csv_path(symbol, interval, directory)
    step = int(interval[:-1]) * UNIT_MS[interval[-1]]
    now = client.now_ms()
    existing = load_candles(symbol, interval, directory) if path.exists() else []
    start = existing[-1].time * 1000 + step if existing else now - int(years * 365 * 86_400_000)

    directory.mkdir(parents=True, exist_ok=True)
    added = 0
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if not existing and f.tell() == 0:
            writer.writerow(FIELDS)
        while start < now:
            rows = client.klines(symbol, interval, limit=BATCH, start_time=start)
            closed = [r for r in rows if r[6] < now]  # skip the candle that is still forming
            writer.writerows([r[0] // 1000, r[1], r[2], r[3], r[4], r[5]] for r in closed)
            added += len(closed)
            if len(rows) < BATCH or not closed:
                break
            start = rows[-1][0] + step
            time.sleep(0.2)  # stay far below Binance rate limits
    return added, len(existing) + added


def funding_path(symbol: str) -> Path:
    return DATA_DIR / f"{symbol}_funding.csv"


def load_funding(symbol: str) -> list[tuple[int, float]]:
    """[(funding time in unix seconds, rate)] oldest first."""
    path = funding_path(symbol)
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [(int(r["time"]), float(r["rate"])) for r in csv.DictReader(f)]


def download_funding(client: FuturesClient, symbol: str, years: float) -> tuple[int, int]:
    """Funding rate history (every 8h). Positive = longs pay shorts (crowded longs). Returns (new, total)."""
    existing = load_funding(symbol)
    start = (existing[-1][0] + 1) * 1000 if existing else client.now_ms() - int(years * 365 * 86_400_000)
    DATA_DIR.mkdir(exist_ok=True)
    added = 0
    with funding_path(symbol).open("a", newline="") as f:
        writer = csv.writer(f)
        if not existing and f.tell() == 0:
            writer.writerow(["time", "rate"])
        while True:
            rows = client.funding_rates(symbol, start_time=start)
            writer.writerows([r["fundingTime"] // 1000, r["fundingRate"]] for r in rows)
            added += len(rows)
            if len(rows) < 1000:
                break
            start = rows[-1]["fundingTime"] + 1
            time.sleep(0.2)
    return added, len(existing) + added


def main() -> None:
    parser = argparse.ArgumentParser(description="Download historical Binance futures candles")
    parser.add_argument("symbols", nargs="*", default=["BTCUSDT", "ETHUSDT"], type=str.upper)
    parser.add_argument("--intervals", nargs="+", default=["1h", "4h"])
    parser.add_argument("--years", type=float, default=3)
    args = parser.parse_args()

    client = FuturesClient("", "", BASE_URLS["live"])
    client.sync_time()
    for symbol in args.symbols:
        for interval in args.intervals:
            added, total = download(client, symbol, interval, args.years)
            print(f"{symbol} {interval}: +{added} new, {total} total -> {csv_path(symbol, interval).name}")
        added, total = download_funding(client, symbol, args.years)
        print(f"{symbol} funding: +{added} new, {total} total -> {funding_path(symbol).name}")


if __name__ == "__main__":
    main()
