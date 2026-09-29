# Intraday momentum lab (volume-spike breakout)

24 coins · long only · settings picked on data before 2025-09-13, judged on the 12 months after · fees 0.05%/side, slippage 0.02%, funding · stops ≥ 1.2% · max 6 open at 0.75% risk

| TF | Settings profitable (last 12 months) | Median | Picked on older data | Picked: older | Picked: last 12 months | Account (return / worst drop) | Random, same exit | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1h | 18/24 | +0.08R | volume ≥3×, 96-candle high, trend filter on, trail 20-candle low | +0.11R | 486 trades, 29% win, -0.02R, PF 0.97 | -19% / 48% | -0.18R | ❌ FAIL |
| 15m | 12/24 | -0.00R | volume ≥5×, 96-candle high, trend filter on, trail 20-candle low | +0.03R | 973 trades, 36% win, +0.10R, PF 1.21 | +35% / 39% | -0.14R | 🟡 PROMISING |


## 1h: all settings (sorted by older-data result)

| Settings | Older data | Last 12 months |
|---|---|---|
| vol ≥3×, 96-candle high, trend on, trail 20-candle low | 1071 trades, 34% win, +0.11R, PF 1.21 | 486 trades, 29% win, -0.02R, PF 0.97 |
| vol ≥3×, 96-candle high, trend off, trail 20-candle low | 1074 trades, 33% win, +0.11R, PF 1.20 | 490 trades, 29% win, -0.03R, PF 0.95 |
| vol ≥3×, 48-candle high, trend on, trail 20-candle low | 1276 trades, 32% win, +0.08R, PF 1.14 | 588 trades, 30% win, +0.04R, PF 1.06 |
| vol ≥3×, 48-candle high, trend off, trail 20-candle low | 1320 trades, 32% win, +0.07R, PF 1.12 | 630 trades, 30% win, +0.01R, PF 1.01 |
| vol ≥3×, 96-candle high, trend on, trail 10-candle low | 1113 trades, 36% win, +0.07R, PF 1.14 | 495 trades, 30% win, +0.06R, PF 1.11 |
| vol ≥3×, 96-candle high, trend off, trail 10-candle low | 1116 trades, 36% win, +0.06R, PF 1.14 | 499 trades, 30% win, +0.05R, PF 1.10 |
| vol ≥3×, 48-candle high, trend on, trail 10-candle low | 1329 trades, 36% win, +0.04R, PF 1.08 | 599 trades, 32% win, +0.11R, PF 1.22 |
| vol ≥3×, 48-candle high, trend off, trail 10-candle low | 1374 trades, 36% win, +0.03R, PF 1.07 | 642 trades, 32% win, +0.08R, PF 1.16 |
| vol ≥3×, 96-candle high, trend on, 2R target | 1126 trades, 39% win, +0.02R, PF 1.03 | 511 trades, 36% win, -0.10R, PF 0.85 |
| vol ≥3×, 96-candle high, trend off, 2R target | 1129 trades, 39% win, +0.01R, PF 1.02 | 515 trades, 36% win, -0.10R, PF 0.85 |
| vol ≥5×, 96-candle high, trend off, trail 10-candle low | 423 trades, 38% win, -0.00R, PF 0.99 | 162 trades, 37% win, +0.32R, PF 1.76 |
| vol ≥5×, 96-candle high, trend on, trail 10-candle low | 423 trades, 38% win, -0.00R, PF 0.99 | 162 trades, 37% win, +0.32R, PF 1.76 |
| vol ≥3×, 48-candle high, trend on, 2R target | 1342 trades, 39% win, -0.01R, PF 0.99 | 625 trades, 36% win, -0.06R, PF 0.90 |
| vol ≥3×, 48-candle high, trend off, 2R target | 1387 trades, 39% win, -0.01R, PF 0.98 | 667 trades, 36% win, -0.07R, PF 0.89 |
| vol ≥5×, 96-candle high, trend off, trail 20-candle low | 417 trades, 35% win, -0.02R, PF 0.96 | 162 trades, 36% win, +0.22R, PF 1.44 |
| vol ≥5×, 96-candle high, trend on, trail 20-candle low | 417 trades, 35% win, -0.02R, PF 0.96 | 162 trades, 36% win, +0.22R, PF 1.44 |
| vol ≥5×, 48-candle high, trend on, trail 10-candle low | 502 trades, 37% win, -0.04R, PF 0.90 | 185 trades, 36% win, +0.36R, PF 1.84 |
| vol ≥5×, 48-candle high, trend off, trail 10-candle low | 517 trades, 36% win, -0.05R, PF 0.89 | 186 trades, 37% win, +0.36R, PF 1.86 |
| vol ≥5×, 48-candle high, trend on, trail 20-candle low | 495 trades, 34% win, -0.05R, PF 0.89 | 185 trades, 36% win, +0.26R, PF 1.50 |
| vol ≥5×, 48-candle high, trend off, trail 20-candle low | 510 trades, 33% win, -0.06R, PF 0.88 | 186 trades, 37% win, +0.28R, PF 1.55 |
| vol ≥5×, 96-candle high, trend off, 2R target | 424 trades, 38% win, -0.07R, PF 0.88 | 165 trades, 44% win, +0.08R, PF 1.16 |
| vol ≥5×, 96-candle high, trend on, 2R target | 424 trades, 38% win, -0.07R, PF 0.88 | 165 trades, 44% win, +0.08R, PF 1.16 |
| vol ≥5×, 48-candle high, trend off, 2R target | 517 trades, 37% win, -0.11R, PF 0.82 | 194 trades, 44% win, +0.10R, PF 1.18 |
| vol ≥5×, 48-candle high, trend on, 2R target | 502 trades, 37% win, -0.11R, PF 0.81 | 192 trades, 43% win, +0.09R, PF 1.16 |

## 15m: all settings (sorted by older-data result)

| Settings | Older data | Last 12 months |
|---|---|---|
| vol ≥5×, 96-candle high, trend on, trail 20-candle low | 906 trades, 37% win, +0.03R, PF 1.06 | 973 trades, 36% win, +0.10R, PF 1.21 |
| vol ≥5×, 96-candle high, trend off, trail 20-candle low | 909 trades, 37% win, +0.03R, PF 1.05 | 984 trades, 36% win, +0.10R, PF 1.21 |
| vol ≥3×, 96-candle high, trend off, trail 20-candle low | 2233 trades, 33% win, +0.02R, PF 1.03 | 2182 trades, 31% win, -0.02R, PF 0.96 |
| vol ≥5×, 48-candle high, trend on, trail 20-candle low | 1012 trades, 37% win, +0.02R, PF 1.03 | 1163 trades, 34% win, +0.06R, PF 1.13 |
| vol ≥3×, 96-candle high, trend on, trail 20-candle low | 2227 trades, 33% win, +0.02R, PF 1.03 | 2155 trades, 31% win, -0.02R, PF 0.97 |
| vol ≥5×, 96-candle high, trend on, trail 10-candle low | 925 trades, 39% win, +0.01R, PF 1.02 | 991 trades, 37% win, +0.05R, PF 1.12 |
| vol ≥5×, 96-candle high, trend off, trail 10-candle low | 928 trades, 39% win, +0.01R, PF 1.02 | 1002 trades, 37% win, +0.05R, PF 1.12 |
| vol ≥5×, 48-candle high, trend off, trail 20-candle low | 1051 trades, 36% win, +0.00R, PF 1.00 | 1212 trades, 34% win, +0.05R, PF 1.10 |
| vol ≥5×, 48-candle high, trend on, 2R target | 1012 trades, 38% win, -0.00R, PF 1.00 | 1167 trades, 40% win, +0.01R, PF 1.02 |
| vol ≥5×, 48-candle high, trend on, trail 10-candle low | 1033 trades, 38% win, -0.00R, PF 0.99 | 1184 trades, 36% win, +0.02R, PF 1.05 |
| vol ≥3×, 48-candle high, trend on, trail 20-candle low | 2654 trades, 32% win, -0.01R, PF 0.99 | 2716 trades, 30% win, -0.05R, PF 0.92 |
| vol ≥5×, 96-candle high, trend on, 2R target | 909 trades, 38% win, -0.01R, PF 0.98 | 979 trades, 40% win, +0.04R, PF 1.07 |
| vol ≥5×, 96-candle high, trend off, 2R target | 912 trades, 38% win, -0.01R, PF 0.98 | 990 trades, 40% win, +0.04R, PF 1.07 |
| vol ≥5×, 48-candle high, trend off, 2R target | 1051 trades, 38% win, -0.01R, PF 0.98 | 1215 trades, 40% win, +0.00R, PF 1.01 |
| vol ≥5×, 48-candle high, trend off, trail 10-candle low | 1072 trades, 38% win, -0.02R, PF 0.96 | 1234 trades, 36% win, +0.02R, PF 1.04 |
| vol ≥3×, 48-candle high, trend off, trail 20-candle low | 2763 trades, 32% win, -0.02R, PF 0.96 | 2874 trades, 30% win, -0.05R, PF 0.91 |
| vol ≥3×, 96-candle high, trend off, 2R target | 2311 trades, 37% win, -0.03R, PF 0.95 | 2255 trades, 38% win, -0.01R, PF 0.98 |
| vol ≥3×, 96-candle high, trend on, 2R target | 2305 trades, 37% win, -0.03R, PF 0.95 | 2226 trades, 38% win, -0.01R, PF 0.98 |
| vol ≥3×, 96-candle high, trend off, trail 10-candle low | 2346 trades, 34% win, -0.04R, PF 0.93 | 2284 trades, 33% win, -0.02R, PF 0.96 |
| vol ≥3×, 96-candle high, trend on, trail 10-candle low | 2340 trades, 34% win, -0.04R, PF 0.93 | 2255 trades, 33% win, -0.01R, PF 0.97 |
| vol ≥3×, 48-candle high, trend on, 2R target | 2736 trades, 36% win, -0.05R, PF 0.93 | 2793 trades, 37% win, -0.06R, PF 0.91 |
| vol ≥3×, 48-candle high, trend on, trail 10-candle low | 2788 trades, 34% win, -0.05R, PF 0.90 | 2846 trades, 33% win, -0.04R, PF 0.91 |
| vol ≥3×, 48-candle high, trend off, 2R target | 2844 trades, 36% win, -0.05R, PF 0.92 | 2954 trades, 37% win, -0.06R, PF 0.91 |
| vol ≥3×, 48-candle high, trend off, trail 10-candle low | 2899 trades, 33% win, -0.06R, PF 0.88 | 3010 trades, 33% win, -0.04R, PF 0.91 |

## FIL trades in the last few days (picked settings)

- 1h: entry 2026-09-13 15:00 UTC → 19 candles, result +1.48R
- 15m: entry 2026-09-11 14:00 UTC → 15 candles, result -1.04R
- 15m: entry 2026-09-13 14:15 UTC → 32 candles, result +1.39R
