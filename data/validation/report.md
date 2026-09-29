# Daily trend following: stress test

Settings picked by the lab: lookback 20 days, trailing stop 2.0× ATR. Same costs as the lab (0.05% fee per side, 0.02% slippage, 0.01% funding per 8h), stops at least 1.2% away.

## 1. Every coin, all available history

| Coin | Data from | Picked settings: all history | Picked settings: never-seen part | Settings profitable |
|---|---|---|---|---|
| BTCUSDT (lab coin) | 2019-09 | 84 trades, 42% win, +0.24R, PF 1.64 | 48 trades, 38% win, +0.14R, PF 1.34 | 9/9 |
| ETHUSDT (lab coin) | 2019-11 | 83 trades, 39% win, +0.16R, PF 1.43 | 44 trades, 41% win, +0.23R, PF 1.65 | 9/9 |
| BNBUSDT | 2020-02 | 88 trades, 38% win, +0.19R, PF 1.49 | 88 trades, 38% win, +0.19R, PF 1.49 | 9/9 |
| SOLUSDT | 2020-09 | 83 trades, 41% win, +0.12R, PF 1.39 | 83 trades, 41% win, +0.12R, PF 1.39 | 9/9 |
| XRPUSDT | 2020-01 | 81 trades, 33% win, +0.06R, PF 1.16 | 81 trades, 33% win, +0.06R, PF 1.16 | 9/9 |
| DOGEUSDT | 2020-07 | 79 trades, 35% win, +0.08R, PF 1.25 | 79 trades, 35% win, +0.08R, PF 1.25 | 9/9 |
| ADAUSDT | 2020-01 | 82 trades, 39% win, +0.16R, PF 1.48 | 82 trades, 39% win, +0.16R, PF 1.48 | 9/9 |
| LINKUSDT | 2020-01 | 90 trades, 27% win, -0.07R, PF 0.81 | 90 trades, 27% win, -0.07R, PF 0.81 | 0/9 |
| AVAXUSDT | 2020-09 | 73 trades, 48% win, +0.10R, PF 1.32 | 73 trades, 48% win, +0.10R, PF 1.32 | 9/9 |
| LTCUSDT | 2020-01 | 83 trades, 31% win, -0.14R, PF 0.65 | 83 trades, 31% win, -0.14R, PF 0.65 | 0/9 |
| DOTUSDT | 2020-08 | 75 trades, 39% win, +0.01R, PF 1.02 | 75 trades, 39% win, +0.01R, PF 1.02 | 8/9 |
| TRXUSDT | 2020-01 | 89 trades, 35% win, -0.07R, PF 0.84 | 89 trades, 35% win, -0.07R, PF 0.84 | 1/9 |

## 2. All 12 coins together, every setting

| Settings | All trades | Never-seen trades only | Account (1% risk): return / worst drop | Max open at once |
|---|---|---|---|---|
| lookback 20, trail 2.0 ← picked | 990 trades, 37% win, +0.07R, PF 1.19 | 915 trades, 37% win, +0.06R, PF 1.16 | +87% / 31% | 12 |
| lookback 20, trail 3.0 | 776 trades, 38% win, +0.24R, PF 1.51 | 713 trades, 38% win, +0.25R, PF 1.52 | +443% / 39% | 12 |
| lookback 20, trail 4.0 | 648 trades, 37% win, +0.50R, PF 1.91 | 597 trades, 37% win, +0.51R, PF 1.93 | +1562% / 43% | 12 |
| lookback 40, trail 2.0 | 773 trades, 37% win, +0.06R, PF 1.16 | 718 trades, 36% win, +0.04R, PF 1.10 | +49% / 35% | 12 |
| lookback 40, trail 3.0 | 629 trades, 36% win, +0.23R, PF 1.46 | 582 trades, 36% win, +0.22R, PF 1.44 | +254% / 43% | 12 |
| lookback 40, trail 4.0 | 535 trades, 35% win, +0.52R, PF 1.92 | 499 trades, 34% win, +0.51R, PF 1.89 | +983% / 44% | 12 |
| lookback 55, trail 2.0 | 635 trades, 39% win, +0.10R, PF 1.28 | 587 trades, 38% win, +0.08R, PF 1.23 | +82% / 28% | 12 |
| lookback 55, trail 3.0 | 517 trades, 38% win, +0.30R, PF 1.63 | 477 trades, 36% win, +0.30R, PF 1.61 | +313% / 35% | 12 |
| lookback 55, trail 4.0 | 437 trades, 38% win, +0.64R, PF 2.20 | 407 trades, 36% win, +0.63R, PF 2.15 | +1067% / 35% | 12 |

## 3. Longs vs shorts (picked settings, all coins)

| Side | Result |
|---|---|
| long | 568 trades, 40% win, +0.16R, PF 1.44 |
| short | 422 trades, 33% win, -0.06R, PF 0.83 |

### By year

| Year | Result |
|---|---|
| 2020 | 100 trades, 37% win, +0.12R, PF 1.29 |
| 2021 | 180 trades, 34% win, +0.14R, PF 1.40 |
| 2022 | 135 trades, 37% win, -0.04R, PF 0.88 |
| 2023 | 170 trades, 35% win, +0.02R, PF 1.05 |
| 2024 | 168 trades, 40% win, +0.12R, PF 1.37 |
| 2025 | 159 trades, 33% win, -0.12R, PF 0.64 |
| 2026 | 78 trades, 49% win, +0.40R, PF 2.21 |

## 4. Could luck do this? (random entries, same stop and trailing exit)

|  | Avg per trade |
|---|---|
| Strategy (picked settings) | +0.069R (990 trades) |
| Strategy (median of all 9 settings) | +0.243R |
| Random direction, 300 runs: median | +0.007R (~1005 trades each) |
| Random direction: best 5% | +0.057R |
| Random LONG-only, 50 runs: median | +0.081R |
| Random runs that matched or beat the strategy | 9/300 (p = 0.030) |
