# Strategy lab report

BTCUSDT + ETHUSDT · settings picked on data before 2025-01-01, judged on data after it · costs: 0.05% fee per side, 0.02% slippage, 0.01% funding per 8h · stops at least 1.2% away

**PASS** = the picked settings made ≥ +0.15R per trade on 2025–26 with ≥ 30 trades, AND at least 60% of all settings were profitable on 2025–26. **PROMISING** = profitable but not all conditions met. The RANDOM rows show what a strategy with no edge looks like.

| Strategy | TF | Settings profitable 2025–26 | Median 2025–26 | Picked: 2023–24 | Picked: 2025–26 | Account 2025–26 (return / worst drop) | Verdict |
|---|---|---|---|---|---|---|---|
| Liquidity sweep reversal | 1h | 2/12 | -0.12R | -0.01R | 416 trades, 40% win, -0.11R, PF 0.83 | -38% / 45% | ❌ FAIL |
| Liquidity sweep reversal | 4h | 5/12 | -0.05R | +0.09R | 42 trades, 45% win, +0.19R, PF 1.33 | +8% / 6% | ❌ FAIL |
| Trend pullback to EMA | 1h | 0/12 | -0.14R | -0.01R | 663 trades, 28% win, -0.14R, PF 0.81 | -65% / 67% | ❌ FAIL |
| Trend pullback to EMA | 4h | 3/12 | -0.01R | +0.20R | 151 trades, 36% win, -0.03R, PF 0.95 | -6% / 17% | ❌ FAIL |
| Breakout + retest | 1h | 0/12 | -0.10R | +0.08R | 349 trades, 28% win, -0.15R, PF 0.80 | -43% / 56% | ❌ FAIL |
| Breakout + retest | 4h | 5/12 | -0.04R | +0.28R | 105 trades, 38% win, +0.09R, PF 1.14 | +9% / 10% | ❌ FAIL |
| Trend following (trailing stop) | 4h | 6/9 | +0.02R | +0.41R | 132 trades, 30% win, +0.09R, PF 1.14 | +9% / 20% | 🟡 PROMISING |
| Trend following (trailing stop) | 1d | 9/9 | +0.38R | +0.19R | 38 trades, 45% win, +0.28R, PF 1.80 | +11% / 7% | ✅ PASS |
| Funding rate extremes | 1h | 0/12 | -0.23R | +0.07R | 278 trades, 29% win, -0.24R, PF 0.69 | -49% / 52% | ❌ FAIL |
| Funding rate extremes | 4h | 0/12 | -0.17R | +0.10R | 144 trades, 36% win, -0.18R, PF 0.73 | -24% / 25% | ❌ FAIL |
| RANDOM entries (control) | 1h | 0/6 | -0.10R | -0.12R | 428 trades, 36% win, -0.05R, PF 0.93 | -23% / 33% | control |
| RANDOM entries (control) | 4h | 5/6 | +0.12R | +0.02R | 120 trades, 44% win, +0.24R, PF 1.42 | +32% / 10% | control |
| RANDOM entries (control) | 1d | 3/6 | -0.07R | +0.72R | 15 trades, 40% win, +0.02R, PF 1.03 | +0% / 7% | control |

## Details

### Liquidity sweep reversal (1h): ❌ FAIL

Picked on 2023–24: `lookback=24, trend_filter=True, rr=1.5`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 93 trades, 43% win, -0.07R, PF 0.89 |
| BTCUSDT short | 100 trades, 42% win, -0.07R, PF 0.89 |
| ETHUSDT long | 110 trades, 36% win, -0.18R, PF 0.74 |
| ETHUSDT short | 113 trades, 39% win, -0.11R, PF 0.84 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| lookback=24, trend_filter=True, rr=1.5 | 347 trades, 44% win, -0.01R, PF 0.98 | 416 trades, 40% win, -0.11R, PF 0.83 |
| lookback=24, trend_filter=True, rr=2.0 | 328 trades, 36% win, -0.04R, PF 0.95 | 394 trades, 32% win, -0.18R, PF 0.76 |
| lookback=24, trend_filter=False, rr=1.5 | 955 trades, 40% win, -0.10R, PF 0.85 | 1156 trades, 39% win, -0.12R, PF 0.81 |
| lookback=48, trend_filter=False, rr=1.5 | 750 trades, 39% win, -0.10R, PF 0.84 | 897 trades, 39% win, -0.12R, PF 0.81 |
| lookback=24, trend_filter=False, rr=2.0 | 829 trades, 33% win, -0.12R, PF 0.83 | 1038 trades, 34% win, -0.12R, PF 0.83 |
| lookback=96, trend_filter=True, rr=1.5 | 19 trades, 37% win, -0.13R, PF 0.81 | 28 trades, 57% win, +0.31R, PF 1.72 |
| lookback=48, trend_filter=False, rr=2.0 | 689 trades, 32% win, -0.14R, PF 0.80 | 851 trades, 34% win, -0.12R, PF 0.83 |
| lookback=96, trend_filter=True, rr=2.0 | 19 trades, 32% win, -0.15R, PF 0.79 | 28 trades, 46% win, +0.21R, PF 1.39 |
| lookback=48, trend_filter=True, rr=1.5 | 146 trades, 37% win, -0.17R, PF 0.75 | 189 trades, 42% win, -0.05R, PF 0.92 |
| lookback=96, trend_filter=False, rr=1.5 | 542 trades, 37% win, -0.18R, PF 0.74 | 635 trades, 39% win, -0.14R, PF 0.79 |
| lookback=48, trend_filter=True, rr=2.0 | 142 trades, 31% win, -0.19R, PF 0.75 | 181 trades, 35% win, -0.12R, PF 0.83 |
| lookback=96, trend_filter=False, rr=2.0 | 525 trades, 31% win, -0.19R, PF 0.74 | 625 trades, 33% win, -0.14R, PF 0.80 |


### Liquidity sweep reversal (4h): ❌ FAIL

Picked on 2023–24: `lookback=48, trend_filter=True, rr=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 12 trades, 25% win, -0.36R, PF 0.57 |
| BTCUSDT short | 12 trades, 75% win, +1.02R, PF 4.70 |
| ETHUSDT long | 10 trades, 30% win, -0.07R, PF 0.89 |
| ETHUSDT short | 8 trades, 50% win, +0.09R, PF 1.17 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| lookback=96, trend_filter=True, rr=1.5 | 5 trades, 80% win, +0.63R, PF 3.98 | 10 trades, 70% win, +0.77R, PF 4.12 |
| lookback=96, trend_filter=True, rr=2.0 | 5 trades, 80% win, +0.59R, PF 3.79 | 10 trades, 60% win, +0.81R, PF 3.31 |
| lookback=48, trend_filter=True, rr=2.0 | 36 trades, 42% win, +0.09R, PF 1.15 | 42 trades, 45% win, +0.19R, PF 1.33 |
| lookback=24, trend_filter=False, rr=1.5 | 287 trades, 43% win, -0.02R, PF 0.97 | 349 trades, 40% win, -0.09R, PF 0.85 |
| lookback=96, trend_filter=False, rr=1.5 | 143 trades, 42% win, -0.04R, PF 0.94 | 176 trades, 37% win, -0.17R, PF 0.74 |
| lookback=48, trend_filter=False, rr=1.5 | 211 trades, 42% win, -0.04R, PF 0.93 | 254 trades, 39% win, -0.12R, PF 0.81 |
| lookback=48, trend_filter=True, rr=1.5 | 36 trades, 42% win, -0.04R, PF 0.92 | 44 trades, 52% win, +0.21R, PF 1.42 |
| lookback=24, trend_filter=False, rr=2.0 | 262 trades, 34% win, -0.09R, PF 0.87 | 327 trades, 35% win, -0.09R, PF 0.87 |
| lookback=24, trend_filter=True, rr=2.0 | 96 trades, 34% win, -0.10R, PF 0.86 | 123 trades, 37% win, -0.01R, PF 0.98 |
| lookback=24, trend_filter=True, rr=1.5 | 99 trades, 38% win, -0.13R, PF 0.80 | 128 trades, 47% win, +0.09R, PF 1.16 |
| lookback=48, trend_filter=False, rr=2.0 | 203 trades, 33% win, -0.16R, PF 0.78 | 248 trades, 34% win, -0.13R, PF 0.82 |
| lookback=96, trend_filter=False, rr=2.0 | 139 trades, 32% win, -0.16R, PF 0.77 | 173 trades, 33% win, -0.13R, PF 0.82 |


### Trend pullback to EMA (1h): ❌ FAIL

Picked on 2023–24: `fast=20, stop_atr=0.5, rr=3.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 157 trades, 28% win, -0.13R, PF 0.83 |
| BTCUSDT short | 153 trades, 30% win, -0.08R, PF 0.89 |
| ETHUSDT long | 171 trades, 27% win, -0.15R, PF 0.81 |
| ETHUSDT short | 182 trades, 26% win, -0.21R, PF 0.72 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| fast=20, stop_atr=0.5, rr=3.0 | 494 trades, 34% win, -0.01R, PF 0.99 | 663 trades, 28% win, -0.14R, PF 0.81 |
| fast=20, stop_atr=1.0, rr=3.0 | 451 trades, 35% win, -0.03R, PF 0.96 | 600 trades, 29% win, -0.15R, PF 0.79 |
| fast=20, stop_atr=0.5, rr=2.0 | 560 trades, 39% win, -0.03R, PF 0.95 | 746 trades, 33% win, -0.15R, PF 0.79 |
| fast=50, stop_atr=0.5, rr=3.0 | 364 trades, 33% win, -0.05R, PF 0.93 | 468 trades, 31% win, -0.11R, PF 0.85 |
| fast=50, stop_atr=0.5, rr=2.0 | 389 trades, 38% win, -0.06R, PF 0.91 | 504 trades, 36% win, -0.10R, PF 0.86 |
| fast=20, stop_atr=1.0, rr=2.0 | 497 trades, 38% win, -0.06R, PF 0.90 | 657 trades, 33% win, -0.15R, PF 0.78 |
| fast=50, stop_atr=1.0, rr=1.5 | 378 trades, 43% win, -0.07R, PF 0.89 | 462 trades, 40% win, -0.11R, PF 0.81 |
| fast=50, stop_atr=1.0, rr=2.0 | 352 trades, 39% win, -0.07R, PF 0.89 | 436 trades, 38% win, -0.07R, PF 0.89 |
| fast=20, stop_atr=0.5, rr=1.5 | 608 trades, 42% win, -0.08R, PF 0.88 | 824 trades, 38% win, -0.15R, PF 0.77 |
| fast=50, stop_atr=0.5, rr=1.5 | 413 trades, 42% win, -0.08R, PF 0.87 | 536 trades, 39% win, -0.14R, PF 0.78 |
| fast=50, stop_atr=1.0, rr=3.0 | 332 trades, 34% win, -0.08R, PF 0.88 | 418 trades, 34% win, -0.06R, PF 0.91 |
| fast=20, stop_atr=1.0, rr=1.5 | 543 trades, 42% win, -0.09R, PF 0.86 | 712 trades, 37% win, -0.16R, PF 0.75 |


### Trend pullback to EMA (4h): ❌ FAIL

Picked on 2023–24: `fast=50, stop_atr=0.5, rr=3.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 33 trades, 33% win, -0.07R, PF 0.90 |
| BTCUSDT short | 40 trades, 32% win, -0.26R, PF 0.64 |
| ETHUSDT long | 39 trades, 36% win, +0.14R, PF 1.23 |
| ETHUSDT short | 39 trades, 41% win, +0.07R, PF 1.11 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| fast=50, stop_atr=0.5, rr=3.0 | 91 trades, 45% win, +0.20R, PF 1.38 | 151 trades, 36% win, -0.03R, PF 0.95 |
| fast=50, stop_atr=1.0, rr=3.0 | 88 trades, 45% win, +0.17R, PF 1.33 | 136 trades, 40% win, +0.06R, PF 1.11 |
| fast=20, stop_atr=0.5, rr=3.0 | 140 trades, 39% win, +0.13R, PF 1.23 | 214 trades, 34% win, -0.00R, PF 1.00 |
| fast=50, stop_atr=1.0, rr=2.0 | 88 trades, 47% win, +0.09R, PF 1.18 | 141 trades, 42% win, +0.03R, PF 1.06 |
| fast=20, stop_atr=1.0, rr=3.0 | 127 trades, 39% win, +0.05R, PF 1.10 | 186 trades, 35% win, -0.00R, PF 1.00 |
| fast=50, stop_atr=0.5, rr=2.0 | 92 trades, 46% win, +0.05R, PF 1.09 | 159 trades, 36% win, -0.08R, PF 0.87 |
| fast=50, stop_atr=0.5, rr=1.5 | 94 trades, 49% win, +0.03R, PF 1.07 | 168 trades, 41% win, -0.09R, PF 0.85 |
| fast=20, stop_atr=0.5, rr=2.0 | 144 trades, 42% win, +0.03R, PF 1.05 | 228 trades, 37% win, -0.04R, PF 0.93 |
| fast=20, stop_atr=0.5, rr=1.5 | 160 trades, 45% win, +0.02R, PF 1.03 | 237 trades, 41% win, -0.09R, PF 0.85 |
| fast=50, stop_atr=1.0, rr=1.5 | 89 trades, 48% win, +0.01R, PF 1.02 | 148 trades, 44% win, -0.00R, PF 1.00 |
| fast=20, stop_atr=1.0, rr=2.0 | 134 trades, 40% win, -0.01R, PF 0.99 | 199 trades, 40% win, +0.01R, PF 1.03 |
| fast=20, stop_atr=1.0, rr=1.5 | 139 trades, 43% win, -0.03R, PF 0.95 | 208 trades, 43% win, -0.02R, PF 0.96 |


### Breakout + retest (1h): ❌ FAIL

Picked on 2023–24: `lookback=55, window=5, rr=3.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 91 trades, 27% win, -0.31R, PF 0.60 |
| BTCUSDT short | 86 trades, 33% win, +0.03R, PF 1.04 |
| ETHUSDT long | 98 trades, 22% win, -0.24R, PF 0.70 |
| ETHUSDT short | 74 trades, 31% win, -0.03R, PF 0.96 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| lookback=55, window=5, rr=3.0 | 260 trades, 35% win, +0.08R, PF 1.12 | 349 trades, 28% win, -0.15R, PF 0.80 |
| lookback=55, window=10, rr=3.0 | 273 trades, 34% win, +0.06R, PF 1.09 | 369 trades, 28% win, -0.12R, PF 0.84 |
| lookback=55, window=5, rr=1.5 | 303 trades, 44% win, +0.02R, PF 1.03 | 417 trades, 42% win, -0.06R, PF 0.91 |
| lookback=55, window=5, rr=2.0 | 279 trades, 38% win, +0.00R, PF 1.00 | 376 trades, 35% win, -0.10R, PF 0.86 |
| lookback=55, window=10, rr=1.5 | 319 trades, 43% win, +0.00R, PF 1.00 | 446 trades, 41% win, -0.07R, PF 0.89 |
| lookback=20, window=5, rr=3.0 | 425 trades, 32% win, -0.00R, PF 1.00 | 579 trades, 27% win, -0.15R, PF 0.80 |
| lookback=55, window=10, rr=2.0 | 295 trades, 37% win, -0.01R, PF 0.99 | 402 trades, 34% win, -0.10R, PF 0.85 |
| lookback=20, window=10, rr=3.0 | 435 trades, 31% win, -0.01R, PF 0.98 | 601 trades, 28% win, -0.12R, PF 0.84 |
| lookback=20, window=5, rr=1.5 | 524 trades, 42% win, -0.04R, PF 0.93 | 724 trades, 41% win, -0.06R, PF 0.90 |
| lookback=20, window=10, rr=1.5 | 542 trades, 42% win, -0.04R, PF 0.93 | 760 trades, 41% win, -0.06R, PF 0.90 |
| lookback=20, window=5, rr=2.0 | 471 trades, 35% win, -0.09R, PF 0.87 | 639 trades, 34% win, -0.10R, PF 0.86 |
| lookback=20, window=10, rr=2.0 | 485 trades, 34% win, -0.11R, PF 0.85 | 664 trades, 34% win, -0.09R, PF 0.87 |


### Breakout + retest (4h): ❌ FAIL

Picked on 2023–24: `lookback=55, window=5, rr=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 32 trades, 44% win, +0.24R, PF 1.40 |
| BTCUSDT short | 25 trades, 28% win, -0.23R, PF 0.70 |
| ETHUSDT long | 24 trades, 42% win, +0.17R, PF 1.30 |
| ETHUSDT short | 24 trades, 38% win, +0.14R, PF 1.24 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| lookback=55, window=5, rr=2.0 | 82 trades, 48% win, +0.28R, PF 1.53 | 105 trades, 38% win, +0.09R, PF 1.14 |
| lookback=55, window=10, rr=2.0 | 85 trades, 47% win, +0.28R, PF 1.53 | 111 trades, 40% win, +0.11R, PF 1.18 |
| lookback=55, window=10, rr=3.0 | 80 trades, 38% win, +0.20R, PF 1.33 | 100 trades, 34% win, +0.15R, PF 1.22 |
| lookback=55, window=5, rr=3.0 | 78 trades, 37% win, +0.17R, PF 1.27 | 94 trades, 33% win, +0.12R, PF 1.17 |
| lookback=20, window=5, rr=2.0 | 147 trades, 41% win, +0.13R, PF 1.22 | 187 trades, 34% win, -0.06R, PF 0.91 |
| lookback=20, window=10, rr=2.0 | 151 trades, 41% win, +0.13R, PF 1.22 | 197 trades, 34% win, -0.08R, PF 0.89 |
| lookback=55, window=10, rr=1.5 | 92 trades, 46% win, +0.10R, PF 1.19 | 118 trades, 43% win, +0.03R, PF 1.05 |
| lookback=55, window=5, rr=1.5 | 87 trades, 46% win, +0.10R, PF 1.18 | 111 trades, 41% win, -0.03R, PF 0.95 |
| lookback=20, window=10, rr=3.0 | 137 trades, 34% win, +0.08R, PF 1.12 | 185 trades, 30% win, -0.05R, PF 0.93 |
| lookback=20, window=5, rr=3.0 | 134 trades, 34% win, +0.08R, PF 1.12 | 176 trades, 30% win, -0.06R, PF 0.92 |
| lookback=20, window=5, rr=1.5 | 159 trades, 45% win, +0.05R, PF 1.08 | 203 trades, 38% win, -0.11R, PF 0.83 |
| lookback=20, window=10, rr=1.5 | 167 trades, 44% win, +0.04R, PF 1.08 | 214 trades, 38% win, -0.11R, PF 0.83 |


### Trend following (trailing stop) (4h): 🟡 PROMISING

Picked on 2023–24: `lookback=55, trail=4.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 36 trades, 25% win, -0.13R, PF 0.79 |
| BTCUSDT short | 32 trades, 28% win, +0.04R, PF 1.06 |
| ETHUSDT long | 30 trades, 33% win, +0.47R, PF 1.80 |
| ETHUSDT short | 34 trades, 32% win, +0.03R, PF 1.05 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| lookback=55, trail=4.0 | 96 trades, 38% win, +0.41R, PF 1.77 | 132 trades, 30% win, +0.09R, PF 1.14 |
| lookback=40, trail=4.0 | 114 trades, 39% win, +0.33R, PF 1.61 | 152 trades, 30% win, +0.16R, PF 1.25 |
| lookback=40, trail=3.0 | 119 trades, 42% win, +0.28R, PF 1.66 | 169 trades, 30% win, +0.01R, PF 1.01 |
| lookback=55, trail=3.0 | 101 trades, 38% win, +0.27R, PF 1.60 | 145 trades, 28% win, +0.02R, PF 1.03 |
| lookback=20, trail=3.0 | 154 trades, 40% win, +0.25R, PF 1.55 | 227 trades, 31% win, +0.07R, PF 1.14 |
| lookback=20, trail=4.0 | 144 trades, 34% win, +0.24R, PF 1.43 | 200 trades, 32% win, +0.23R, PF 1.37 |
| lookback=40, trail=2.0 | 154 trades, 39% win, +0.09R, PF 1.26 | 201 trades, 31% win, -0.02R, PF 0.95 |
| lookback=20, trail=2.0 | 200 trades, 37% win, +0.06R, PF 1.18 | 280 trades, 31% win, -0.03R, PF 0.92 |
| lookback=55, trail=2.0 | 131 trades, 37% win, +0.04R, PF 1.10 | 172 trades, 31% win, -0.01R, PF 0.99 |


### Trend following (trailing stop) (1d): ✅ PASS

Picked on 2023–24: `lookback=20, trail=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 8 trades, 62% win, +0.40R, PF 2.36 |
| BTCUSDT short | 8 trades, 50% win, +0.57R, PF 2.68 |
| ETHUSDT long | 10 trades, 40% win, +0.13R, PF 1.29 |
| ETHUSDT short | 12 trades, 33% win, +0.12R, PF 1.40 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| lookback=55, trail=4.0 | 11 trades, 36% win, +0.59R, PF 2.02 | 19 trades, 68% win, +0.47R, PF 2.67 |
| lookback=55, trail=2.0 | 17 trades, 35% win, +0.32R, PF 1.83 | 27 trades, 52% win, +0.22R, PF 1.70 |
| lookback=55, trail=3.0 | 14 trades, 29% win, +0.31R, PF 1.57 | 22 trades, 59% win, +0.38R, PF 2.37 |
| lookback=20, trail=2.0 | 29 trades, 34% win, +0.19R, PF 1.49 | 38 trades, 45% win, +0.28R, PF 1.80 |
| lookback=40, trail=4.0 | 15 trades, 27% win, +0.19R, PF 1.29 | 21 trades, 62% win, +0.60R, PF 2.94 |
| lookback=40, trail=2.0 | 21 trades, 33% win, +0.19R, PF 1.47 | 30 trades, 50% win, +0.36R, PF 2.14 |
| lookback=20, trail=4.0 | 21 trades, 29% win, +0.15R, PF 1.21 | 27 trades, 48% win, +0.39R, PF 1.86 |
| lookback=20, trail=3.0 | 25 trades, 24% win, +0.10R, PF 1.18 | 31 trades, 48% win, +0.37R, PF 1.87 |
| lookback=40, trail=3.0 | 18 trades, 22% win, +0.09R, PF 1.17 | 25 trades, 56% win, +0.47R, PF 2.55 |


### Funding rate extremes (1h): ❌ FAIL

Picked on 2023–24: `pct=95, confirm=False, rr=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 93 trades, 28% win, -0.28R, PF 0.65 |
| BTCUSDT short | 35 trades, 43% win, +0.17R, PF 1.27 |
| ETHUSDT long | 113 trades, 24% win, -0.37R, PF 0.54 |
| ETHUSDT short | 37 trades, 32% win, -0.11R, PF 0.84 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| pct=95, confirm=False, rr=2.0 | 206 trades, 39% win, +0.07R, PF 1.11 | 278 trades, 29% win, -0.24R, PF 0.69 |
| pct=98, confirm=False, rr=2.0 | 140 trades, 39% win, +0.04R, PF 1.07 | 109 trades, 28% win, -0.24R, PF 0.69 |
| pct=90, confirm=False, rr=2.0 | 255 trades, 38% win, +0.03R, PF 1.05 | 550 trades, 31% win, -0.17R, PF 0.77 |
| pct=95, confirm=False, rr=1.5 | 232 trades, 44% win, +0.00R, PF 1.00 | 312 trades, 35% win, -0.22R, PF 0.68 |
| pct=98, confirm=True, rr=2.0 | 120 trades, 38% win, -0.00R, PF 1.00 | 98 trades, 27% win, -0.29R, PF 0.63 |
| pct=90, confirm=False, rr=1.5 | 296 trades, 42% win, -0.03R, PF 0.95 | 621 trades, 38% win, -0.15R, PF 0.77 |
| pct=95, confirm=True, rr=1.5 | 213 trades, 42% win, -0.03R, PF 0.95 | 274 trades, 33% win, -0.27R, PF 0.63 |
| pct=98, confirm=True, rr=1.5 | 138 trades, 42% win, -0.04R, PF 0.94 | 107 trades, 32% win, -0.28R, PF 0.62 |
| pct=90, confirm=True, rr=1.5 | 270 trades, 42% win, -0.04R, PF 0.93 | 547 trades, 37% win, -0.16R, PF 0.77 |
| pct=95, confirm=True, rr=2.0 | 184 trades, 35% win, -0.04R, PF 0.94 | 256 trades, 28% win, -0.25R, PF 0.68 |
| pct=90, confirm=True, rr=2.0 | 234 trades, 35% win, -0.04R, PF 0.94 | 497 trades, 31% win, -0.16R, PF 0.79 |
| pct=98, confirm=False, rr=1.5 | 153 trades, 41% win, -0.06R, PF 0.91 | 118 trades, 35% win, -0.20R, PF 0.71 |


### Funding rate extremes (4h): ❌ FAIL

Picked on 2023–24: `pct=95, confirm=True, rr=1.5`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 50 trades, 34% win, -0.22R, PF 0.69 |
| BTCUSDT short | 22 trades, 45% win, +0.05R, PF 1.08 |
| ETHUSDT long | 53 trades, 40% win, -0.12R, PF 0.81 |
| ETHUSDT short | 19 trades, 21% win, -0.54R, PF 0.36 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| pct=95, confirm=True, rr=1.5 | 72 trades, 47% win, +0.10R, PF 1.18 | 144 trades, 36% win, -0.18R, PF 0.73 |
| pct=95, confirm=True, rr=2.0 | 71 trades, 37% win, +0.02R, PF 1.03 | 129 trades, 34% win, -0.17R, PF 0.76 |
| pct=90, confirm=True, rr=1.5 | 91 trades, 43% win, -0.00R, PF 0.99 | 242 trades, 37% win, -0.15R, PF 0.77 |
| pct=90, confirm=False, rr=1.5 | 115 trades, 41% win, -0.05R, PF 0.93 | 311 trades, 39% win, -0.12R, PF 0.82 |
| pct=95, confirm=False, rr=1.5 | 94 trades, 40% win, -0.06R, PF 0.90 | 173 trades, 37% win, -0.17R, PF 0.75 |
| pct=95, confirm=False, rr=2.0 | 85 trades, 33% win, -0.10R, PF 0.86 | 158 trades, 34% win, -0.17R, PF 0.77 |
| pct=90, confirm=True, rr=2.0 | 87 trades, 32% win, -0.11R, PF 0.84 | 214 trades, 35% win, -0.10R, PF 0.85 |
| pct=98, confirm=True, rr=1.5 | 52 trades, 37% win, -0.11R, PF 0.82 | 56 trades, 32% win, -0.28R, PF 0.61 |
| pct=90, confirm=False, rr=2.0 | 100 trades, 32% win, -0.12R, PF 0.83 | 269 trades, 34% win, -0.12R, PF 0.83 |
| pct=98, confirm=True, rr=2.0 | 51 trades, 31% win, -0.12R, PF 0.83 | 53 trades, 34% win, -0.18R, PF 0.75 |
| pct=98, confirm=False, rr=2.0 | 68 trades, 28% win, -0.22R, PF 0.71 | 66 trades, 33% win, -0.13R, PF 0.82 |
| pct=98, confirm=False, rr=1.5 | 71 trades, 32% win, -0.23R, PF 0.67 | 69 trades, 33% win, -0.25R, PF 0.65 |


### RANDOM entries (control) (1h): control

Picked on 2023–24: `seed=3, rr=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 102 trades, 34% win, -0.12R, PF 0.83 |
| BTCUSDT short | 105 trades, 39% win, +0.08R, PF 1.11 |
| ETHUSDT long | 112 trades, 31% win, -0.19R, PF 0.75 |
| ETHUSDT short | 109 trades, 38% win, +0.03R, PF 1.04 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| seed=3, rr=2.0 | 316 trades, 34% win, -0.12R, PF 0.84 | 428 trades, 36% win, -0.05R, PF 0.93 |
| seed=5, rr=2.0 | 322 trades, 33% win, -0.15R, PF 0.80 | 480 trades, 35% win, -0.09R, PF 0.88 |
| seed=2, rr=2.0 | 335 trades, 31% win, -0.16R, PF 0.78 | 443 trades, 30% win, -0.22R, PF 0.71 |
| seed=1, rr=2.0 | 327 trades, 31% win, -0.16R, PF 0.78 | 483 trades, 34% win, -0.11R, PF 0.85 |
| seed=4, rr=2.0 | 341 trades, 29% win, -0.25R, PF 0.68 | 427 trades, 29% win, -0.24R, PF 0.69 |
| seed=6, rr=2.0 | 344 trades, 27% win, -0.30R, PF 0.63 | 423 trades, 37% win, -0.01R, PF 0.99 |


### RANDOM entries (control) (4h): control

Picked on 2023–24: `seed=2, rr=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 35 trades, 46% win, +0.23R, PF 1.38 |
| BTCUSDT short | 24 trades, 54% win, +0.60R, PF 2.38 |
| ETHUSDT long | 35 trades, 40% win, +0.08R, PF 1.12 |
| ETHUSDT short | 26 trades, 38% win, +0.15R, PF 1.25 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| seed=2, rr=2.0 | 91 trades, 37% win, +0.02R, PF 1.03 | 120 trades, 44% win, +0.24R, PF 1.42 |
| seed=3, rr=2.0 | 91 trades, 36% win, -0.02R, PF 0.97 | 117 trades, 47% win, +0.28R, PF 1.50 |
| seed=6, rr=2.0 | 90 trades, 34% win, -0.07R, PF 0.90 | 137 trades, 31% win, -0.19R, PF 0.74 |
| seed=5, rr=2.0 | 89 trades, 34% win, -0.10R, PF 0.85 | 123 trades, 41% win, +0.13R, PF 1.21 |
| seed=1, rr=2.0 | 89 trades, 30% win, -0.17R, PF 0.77 | 114 trades, 41% win, +0.12R, PF 1.18 |
| seed=4, rr=2.0 | 78 trades, 27% win, -0.29R, PF 0.63 | 122 trades, 38% win, +0.01R, PF 1.02 |


### RANDOM entries (control) (1d): control

Picked on 2023–24: `seed=6, rr=2.0`

| 2025–26 group | Result |
|---|---|
| BTCUSDT long | 5 trades, 40% win, +0.09R, PF 1.14 |
| BTCUSDT short | 3 trades, 67% win, +0.43R, PF 2.20 |
| ETHUSDT long | 5 trades, 20% win, -0.47R, PF 0.44 |
| ETHUSDT short | 2 trades, 50% win, +0.45R, PF 1.86 |

All settings (sorted by 2023–24 result):

| Settings | 2023–24 | 2025–26 |
|---|---|---|
| seed=6, rr=2.0 | 10 trades, 60% win, +0.72R, PF 2.61 | 15 trades, 40% win, +0.02R, PF 1.03 |
| seed=4, rr=2.0 | 9 trades, 56% win, +0.59R, PF 2.24 | 19 trades, 26% win, -0.31R, PF 0.61 |
| seed=1, rr=2.0 | 14 trades, 36% win, +0.01R, PF 1.02 | 20 trades, 20% win, -0.52R, PF 0.40 |
| seed=3, rr=2.0 | 12 trades, 33% win, -0.06R, PF 0.92 | 19 trades, 32% win, -0.15R, PF 0.80 |
| seed=5, rr=2.0 | 3 trades, 33% win, -0.13R, PF 0.83 | 26 trades, 42% win, +0.18R, PF 1.30 |
| seed=2, rr=2.0 | 2 trades, 0% win, -1.05R, PF 0.00 | 14 trades, 57% win, +0.62R, PF 2.33 |
