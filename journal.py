"""Appends every trade event to a CSV file you can open in Excel / Google Sheets."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

FIELDS = ["time", "env", "event", "symbol", "side", "qty", "price", "stop", "take_profit",
          "leverage", "risk_usdt", "pnl_usdt", "note"]


def log(path: Path, event: str, **row: object) -> None:
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow({"time": datetime.now().isoformat(timespec="seconds"), "event": event, **row})
