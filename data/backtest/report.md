# Backtest report

Signals that passed all required gates: **6135** (2023-11-04 23:00 → 2026-09-13 14:00 UTC). Costs: 0.05% fee per side, 0.02% slippage, funding 0.01%/8h. Max hold 72 candles.

✅ = at least 30 trades and +0.15R or better per trade · ➖ = small or unproven edge · ❌ = loses money


## In-sample (before 2025-01-01)

### Results by score (each setup counted once)

| Score | Trades | Win rate | Avg per trade | Profit factor | Max drawdown |
|---|---|---|---|---|---|
| ≤ 4 | 28 | 43% | +0.02R ➖ | 1.03 | 9.3R |
| 5 | 59 | 34% | -0.08R ❌ | 0.90 | 16.4R |
| 6 | 122 | 35% | -0.13R ❌ | 0.84 | 27.8R |
| 7 | 103 | 25% | -0.38R ❌ | 0.57 | 43.2R |
| 8 | 117 | 26% | -0.41R ❌ | 0.56 | 47.8R |
| 9+ | 107 | 23% | -0.42R ❌ | 0.56 | 46.7R |
| **all** | 536 | 29% | -0.28R ❌ | 0.68 | 152.0R |

### Account simulation: trade only when score ≥ threshold (1% risk, one position per coin)

| Threshold | Trades | Win rate | Avg per trade | Profit factor | Max drawdown | Account return | Worst drop |
|---|---|---|---|---|---|---|---|
| ≥ 4 | 533 | 29% | -0.29R ❌ | 0.67 | 155.3R | -80.1% | 80.2% |
| ≥ 5 | 514 | 29% | -0.29R ❌ | 0.67 | 149.7R | -78.9% | 79.0% |
| ≥ 6 | 488 | 28% | -0.33R ❌ | 0.63 | 160.1R | -80.9% | 81.0% |
| ≥ 7 | 410 | 28% | -0.32R ❌ | 0.64 | 130.8R | -74.1% | 74.2% |
| ≥ 8 | 331 | 27% | -0.35R ❌ | 0.61 | 116.0R | -69.9% | 69.9% |
| ≥ 9 | 195 | 24% | -0.43R ❌ | 0.54 | 85.7R | -57.7% | 58.6% |

### By coin and side (all scores)

| Group | Trades | Win rate | Avg per trade | Profit factor | Max drawdown |
|---|---|---|---|---|---|
| BTCUSDT long | 166 | 28% | -0.39R ❌ | 0.57 | 72.7R |
| BTCUSDT short | 127 | 26% | -0.36R ❌ | 0.62 | 51.3R |
| ETHUSDT long | 146 | 36% | -0.08R ❌ | 0.90 | 17.7R |
| ETHUSDT short | 97 | 25% | -0.31R ❌ | 0.65 | 40.9R |

### Does each confirmation help? (average result when it passed vs failed)

| Confirmation | Passed | Avg R | Failed | Avg R | Difference |
|---|---|---|---|---|---|
| htf_trend | 536 | - | 0 | - | not enough data |
| ltf_structure | 305 | -0.27R | 231 | -0.31R | +0.04R no real effect |
| location | 379 | -0.33R | 157 | -0.16R | -0.17R hurts |
| fib | 95 | -0.38R | 441 | -0.26R | -0.12R hurts |
| trigger | 177 | -0.39R | 359 | -0.23R | -0.16R hurts |
| divergence | 133 | -0.30R | 403 | -0.28R | -0.03R no real effect |
| volume | 231 | -0.42R | 305 | -0.18R | -0.24R hurts |
| rsi | 509 | -0.30R | 27 | +0.01R | -0.31R hurts |
| ema | 343 | -0.31R | 193 | -0.24R | -0.07R no real effect |

Exits: 144 hit target, 376 hit stop, 16 closed after 72 candles.

## Out-of-sample (from 2025-01-01)

### Results by score (each setup counted once)

| Score | Trades | Win rate | Avg per trade | Profit factor | Max drawdown |
|---|---|---|---|---|---|
| ≤ 4 | 39 | 36% | -0.09R ❌ | 0.88 | 9.9R |
| 5 | 86 | 34% | -0.18R ❌ | 0.78 | 23.7R |
| 6 | 172 | 27% | -0.36R ❌ | 0.59 | 65.1R |
| 7 | 157 | 28% | -0.33R ❌ | 0.65 | 57.9R |
| 8 | 140 | 24% | -0.42R ❌ | 0.55 | 61.7R |
| 9+ | 117 | 25% | -0.45R ❌ | 0.54 | 54.0R |
| **all** | 711 | 27% | -0.34R ❌ | 0.62 | 247.0R |

### Account simulation: trade only when score ≥ threshold (1% risk, one position per coin)

| Threshold | Trades | Win rate | Avg per trade | Profit factor | Max drawdown | Account return | Worst drop |
|---|---|---|---|---|---|---|---|
| ≥ 4 | 707 | 28% | -0.34R ❌ | 0.63 | 241.9R | -91.6% | 91.8% |
| ≥ 5 | 698 | 27% | -0.35R ❌ | 0.61 | 248.8R | -92.2% | 92.4% |
| ≥ 6 | 659 | 26% | -0.38R ❌ | 0.59 | 251.9R | -92.4% | 92.6% |
| ≥ 7 | 552 | 26% | -0.37R ❌ | 0.59 | 212.5R | -88.2% | 88.8% |
| ≥ 8 | 412 | 26% | -0.37R ❌ | 0.59 | 153.8R | -79.4% | 79.5% |
| ≥ 9 | 241 | 28% | -0.30R ❌ | 0.67 | 72.6R | -53.2% | 53.2% |

### By coin and side (all scores)

| Group | Trades | Win rate | Avg per trade | Profit factor | Max drawdown |
|---|---|---|---|---|---|
| BTCUSDT long | 192 | 26% | -0.45R ❌ | 0.54 | 86.6R |
| BTCUSDT short | 153 | 27% | -0.40R ❌ | 0.58 | 62.2R |
| ETHUSDT long | 203 | 25% | -0.35R ❌ | 0.60 | 76.7R |
| ETHUSDT short | 163 | 33% | -0.16R ❌ | 0.80 | 44.6R |

### Does each confirmation help? (average result when it passed vs failed)

| Confirmation | Passed | Avg R | Failed | Avg R | Difference |
|---|---|---|---|---|---|
| htf_trend | 711 | - | 0 | - | not enough data |
| ltf_structure | 337 | -0.26R | 374 | -0.42R | +0.16R helps |
| location | 505 | -0.46R | 206 | -0.07R | -0.39R hurts |
| fib | 153 | -0.29R | 558 | -0.36R | +0.07R no real effect |
| trigger | 210 | -0.43R | 501 | -0.31R | -0.12R hurts |
| divergence | 157 | -0.18R | 554 | -0.39R | +0.20R helps |
| volume | 324 | -0.39R | 387 | -0.30R | -0.09R no real effect |
| rsi | 663 | -0.36R | 48 | -0.10R | -0.26R hurts |
| ema | 450 | -0.32R | 261 | -0.38R | +0.06R no real effect |

Exits: 176 hit target, 505 hit stop, 30 closed after 72 candles.
