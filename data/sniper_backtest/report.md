# Sniper bot backtest

Window 2025-09-28 → 2026-09-28, 24 coins: BTC, ETH, BNB, SOL, XRP, DOGE, ADA, LINK, AVAX, LTC, DOT, TRX, ATOM, NEAR, FIL, UNI, AAVE, ETC, APT, ARB, OP, INJ, BCH, XLM.
Settings: min target 2R, ADX ≥ 20, max hold 48 h, at most 2 same-side altcoin trades. Fees 0.05% per side, slippage 0.02%. R includes fees (a full stop = -1R).

## Sniper vs daily trend bot

| Bot | Trades | Win | Avg | PF | Total | Worst drop | Losing streak | Account at 1% risk: return / worst drop |
|---|---|---|---|---|---|---|---|---|
| Sniper, no altcoin cap | 3751 | 50% | -0.14R | 0.73 | -517R | 530R | 15 | -100% / 100% |
| Sniper, altcoin cap 2 (as live) | 2165 | 50% | -0.14R | 0.74 | -296R | 300R | 11 | -95% / 96% |
| Trend bot, same window | 28 | 18% | -0.42R | 0.46 | -12R | 14R | 12 | -11% / 13% |
| Trend bot, all history since 2020 | 213 | 31% | +1.69R | 3.75 | +359R | 24R | 15 | +1715% / 21% |

## Sniper details (as live)

| Kind | Trades | Win | Avg | Total |
|---|---|---|---|---|
| bounce | 2007 | 50% | -0.13R | -256R |
| breakout | 158 | 46% | -0.25R | -40R |

| Exit | Trades | Win | Avg | Total |
|---|---|---|---|---|
| break-even | 739 | 100% | +0.36R | +267R |
| stop | 1088 | 0% | -1.03R | -1118R |
| target | 326 | 100% | +1.65R | +539R |
| time | 12 | 100% | +1.35R | +16R |

| Side | Trades | Win | Avg | Total |
|---|---|---|---|---|
| LONG | 991 | 48% | -0.18R | -179R |
| SHORT | 1174 | 51% | -0.10R | -117R |

| Month | Sniper | Trend bot |
|---|---|---|
| 2025-09 | -0.3R |  |
| 2025-10 | -33.0R | -2.1R |
| 2025-11 | -13.1R | -1.0R |
| 2025-12 | -34.3R | -0.6R |
| 2026-01 | -7.8R | -3.3R |
| 2026-02 | -3.3R |  |
| 2026-03 | -33.2R | +2.5R |
| 2026-04 | -18.0R | +1.1R |
| 2026-05 | -57.1R | -5.2R |
| 2026-06 | +15.9R |  |
| 2026-07 | -44.6R | -0.7R |
| 2026-08 | -38.9R | +0.7R |
| 2026-09 | -28.1R | -3.1R |

Trend bot months are by entry date. Its all-history line is partly in-sample: the exit rule was chosen on these coins.
