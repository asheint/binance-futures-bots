"""Loads settings from .env and applies the safety limits."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_URLS = {
    "demo": "https://demo-fapi.binance.com",  # fake money, real prices
    "live": "https://fapi.binance.com",       # REAL money
}


@dataclass(frozen=True)
class Config:
    env: str
    base_url: str
    api_key: str
    api_secret: str
    risk_pct: float
    rr: float
    leverage: int
    max_risk_pct: float
    max_leverage: int
    journal_path: Path


def load_config() -> Config:
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")

    env = os.getenv("BINANCE_ENV", "demo").strip().lower()
    if env not in BASE_URLS:
        sys.exit(f"BINANCE_ENV must be 'demo' or 'live', got '{env}'.")
    if env == "live" and os.getenv("ALLOW_LIVE_TRADING", "").strip().lower() != "yes":
        sys.exit("BINANCE_ENV=live needs ALLOW_LIVE_TRADING=yes in .env. Stay on demo until you are consistent.")

    return Config(
        env=env,
        base_url=os.getenv("BINANCE_BASE_URL") or BASE_URLS[env],
        api_key=os.getenv("BINANCE_API_KEY", "").strip(),
        api_secret=os.getenv("BINANCE_API_SECRET", "").strip(),
        risk_pct=float(os.getenv("RISK_PCT", "1")),
        rr=float(os.getenv("REWARD_RISK", "2")),
        leverage=int(os.getenv("LEVERAGE", "3")),
        max_risk_pct=float(os.getenv("MAX_RISK_PCT", "2")),
        max_leverage=int(os.getenv("MAX_LEVERAGE", "5")),
        journal_path=root / os.getenv("JOURNAL_FILE", "trades.csv"),
    )
