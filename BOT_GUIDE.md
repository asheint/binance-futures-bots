# Trend Bot: Complete Guide

*Last updated: 14 September 2026*

---

## 1. What this bot is

A trading bot for **Binance USDⓈ-M Futures** that follows **one tested strategy: daily trend following**.

- It buys a coin when it **breaks out to a new 55-day high** in an uptrend.
- It **holds** while the trend continues.
- It **sells** when the trend breaks, meaning price falls below its lowest point of the last 20 days.

It only trades **while you run it**, it's set to your **demo (fake money) account** by default, and every trade risks a **fixed 0.75%** of your balance.

> ⚠️ **Honest warning:** the strategy made money over 6 years of history, but past results don't guarantee future ones. Most of its profit came in a few strong bull-market years, and 2026 so far is **−12%**. Stay on demo until the live results match the backtest for several months.

---

## 2. Quick start

### Start the bot
1. Open the project folder (where you cloned or downloaded it)
2. Double-click **`start.cmd`**

This opens:
- the **"Trend Bot"** window (the bot itself: leave it open while you want it trading)
- a minimized **"Trend Bot dashboard"** window
- your browser at **http://127.0.0.1:8000**

If Windows says *"Windows protected your PC"*, click **More info → Run anyway**.

### Stop the bot
1. Click the "Trend Bot" window and press **Ctrl+C** (or close it)
2. Close the minimized "Trend Bot dashboard" window

When the bot is off, **open positions stay protected**: their stop orders sit on Binance's servers.

### Just look, don't trade
From a terminal in the bot folder:
```powershell
.\.venv\Scripts\python.exe dashboard.py          # dashboard only
.\.venv\Scripts\python.exe trend_bot.py scan     # signals in the terminal
```

---

## 3. The strategy, step by step

### Which chart
**Daily candles (1D).** Each candle closes at **00:00 UTC = 5:30 AM Sri Lanka time**. The bot decides only on finished daily candles. The 15m/1H/4H buttons on the dashboard are for looking only.

### Which coins (24)
BTC, ETH, BNB, SOL, XRP, DOGE, ADA, LINK, AVAX, LTC, DOT, TRX, ATOM, NEAR, FIL, UNI, AAVE, ETC, APT, ARB, OP, INJ, BCH, XLM (all against USDT, perpetual futures).

### Rule 1: When it BUYS
All of these must be true on a **closed daily candle**:

| Check | Meaning |
|---|---|
| Close **above the highest high of the previous 55 days** | A real breakout: price is doing something new |
| Close **above EMA 100** | The coin is in a longer-term uptrend |
| Fewer than **6 positions** open | Limits total risk |
| No position already open on that coin | One trade per coin |

It buys at the **next daily open** (or as soon as you start the bot that day).

**Catch-up rule:** if you didn't run the bot on the signal day, it still buys a signal from **up to 3 days ago**, as long as price hasn't fallen back to where the stop would be. The backtest showed joining up to 3 days late works as well as joining on time.

**Long only:** the bot never shorts. Shorts lost money in every test.

### Rule 2: How MUCH it buys (position size)
The size is set so that **if the first stop is hit, you lose exactly 0.75% of your balance**:

```
First stop   = entry − 2 × ATR          (ATR = the coin's normal daily move; at least 1.2% away)
Risk (USDT)  = balance × 0.75%
Size         = risk ÷ (entry − first stop)
```

**Example:** balance 5,000 USDT → risk 37.50 USDT. BTC entry 80,000, ATR 2,000 → stop 76,000 (4,000 away) → size = 37.50 ÷ 4,000 = **0.0094 BTC** (≈ 750 USDT position, ≈ 250 USDT margin at 3x).

Leverage doesn't change the risk. It only decides how much margin is locked.

### Rule 3: When it SELLS (the moment profit is taken)
After every daily close, the bot moves the stop to **the lowest low of the last 20 days**, but **only if that's higher than the current stop**. The stop **never moves down**.

**Profit is taken when price falls below that stop.** Binance closes the position instantly, at any time of day.

- If the stop is still **below** your entry → it's a **loss** (at most about −1R)
- If the stop has risen **above** your entry → it's a **profit** (locked in)

**Locked profit = (stop − entry) × size**

A safety limit closes any trade still open after **120 days**.

### Example trade
| Day | What happens | Stop |
|---|---|---|
| 0 | BTC closes above its 55-day high → buy at 80,000 | 76,000 (2 × ATR) |
| 10 | Price 88,000; 20-day low is 77,500 | 77,500 ↑ |
| 25 | Price 97,000; 20-day low is 84,000 | 84,000 ↑ 🔒 profit locked |
| 40 | Price 104,000; 20-day low is 92,000 | 92,000 ↑ 🔒 |
| 46 | Price drops to 92,000 | **Sold: +12,000 per BTC (+3R)** |

### What "R" means
**R = the amount risked on a trade** (0.75% of balance). +3R means you made 3 × what you risked; −1R means the first stop was hit.

---

## 4. What to expect

Backtest of the exact live rules: 24 coins, max 6 open, 0.75% risk, after fees, slippage and funding.

### Last 3 years (Sep 2023 → Sep 2026): the most realistic guide
| | |
|---|---|
| Trades per month | **~3** |
| Win rate | **~27%** (most trades are small losses) |
| Average per trade | **+0.64R** |
| Average holding time | **~24 days** |
| Yearly return | **~+16%** |
| Worst drop | **−16%** |

### Year by year (2020 → Sep 2026)
| 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (so far) |
|---|---|---|---|---|---|---|
| +22% | +443% | −12% | +4% | +67% | +2% | −12% |

### How to read this
- **Profit comes in bursts.** Big bull markets (2021, 2024) make almost all the money. Other years are flat or negative.
- **The 2021 number is exceptional** (crypto mania). Don't expect it again. The all-history average (+39%/yr) is inflated by it; the last-3-years figure (+16%/yr) is more realistic.
- **About 7 out of 10 trades lose.** Losing streaks of 8–12 trades are normal. The few big winners pay for them.
- **Judge the bot over months**, never after a single trade.

---

## 5. How the strategy was chosen and proven

Everything was tested on history before the bot was allowed to trade, and a lot of ideas failed.

### Data used
| Data | Period | Coins |
|---|---|---|
| Daily candles | Dec 2019 / 2020 → 13 Sep 2026 (newer coins from their listing: APT Oct 2022, ARB Mar 2023, OP Jun 2022, INJ Aug 2022) | 24 |
| 1h + 4h candles | Sep 2023 → Sep 2026 | BTC, ETH |
| Funding rates | Sep 2023 → Sep 2026 | BTC, ETH |

### What was tested
| Step | Idea | Result |
|---|---|---|
| 1 | **Setup cards**: structure, support/resistance, Fibonacci, candle patterns, divergence, score out of 12 | ❌ **−0.32R per trade.** No better than a coin flip; higher scores did *worse* |
| 2 | Fixing stops/targets on those setups | Losses shrank but stayed negative. A filter that looked profitable on old data lost on new data (overfitting) |
| 3 | **Strategy lab**: liquidity sweeps, EMA pullbacks, breakout + retest, funding extremes, trend following, random entries as a control | Only **daily trend following** passed |
| 4 | **Stress test** on 12 coins, 2020–2026, 300 random-entry runs | Longs beat random entries (p ≈ 0.01); shorts lost → long-only |
| 5 | **7 take-profit styles**, including signal-channel TP1–TP4 levels | Fixed profit levels cut returns by half; letting winners run won |
| 6 | **8 exit methods** on 12 coins, then re-checked on **12 never-seen coins** | "Sell below the 20-day low" won on both sets, better on 9 of 12 new coins |
| 7 | **Walk-forward training**, 24 coins: each year uses only settings that were best on the years before it | Picked **55-day breakout + 20-day low** in every year 2022–2026: **+38%** total vs **+8%** for the old settings |

### Costs included in every test
- 0.05% trading fee on entry and exit
- 0.02% slippage
- 0.01% funding every 8 hours
- stops at least 1.2% away
- entry at the next candle's open (never the signal candle's close)
- if a candle touches both stop and target, the stop is assumed first

### Retraining
Run this every few months:
```powershell
.\.venv\Scripts\python.exe train_trend.py
```
It downloads the newest candles and repeats the walk-forward test. **Only change the settings if the walk-forward keeps choosing something different.** Never change them because of a few losing trades.

---

## 6. The dashboard

Open **http://127.0.0.1:8000** (started by `start.cmd`, or `python dashboard.py`).

### Terminal page (Binance-style)
| Area | What it shows |
|---|---|
| **Ticker strip** (top) | The bot's coins with 24h change. Click one to open its chart |
| **Symbol header** | Price, 24h change, mark price, index price, funding rate + countdown, 24h high/low/volume, open interest |
| **Chart** | Live candles (updates every trade), 15m/1H/4H view, layer toggles |
| **Bot chart / TradingView** | Bot chart shows the bot's drawings and your entry/stop/target lines. TradingView has full drawing tools and indicators |
| **Real market / Demo server** | Where the *chart's* prices come from. **Real market** = real Binance (use this). Demo server = Binance's demo copy (slightly different prices, fake volume). It doesn't change your account or the bot |
| **Layers** | Structure (HH/HL/LH/LL, BOS/CHoCH), S/R zones, Fibonacci, EMA 50/200, candle patterns, RSI divergence. These are for learning; the bot doesn't trade them |
| **Trend bot panel** (right) | This coin's status: breakout level, EMA filter, progress bar, or the open trade's entry and stop |
| **Chart analysis** (right) | Plain-English reading of the chart (learning only) |
| **Positions tab** | Open positions: size, entry, mark, liquidation, margin, PnL (ROI%), stop, stop→target bar, target, **Market close** |
| **Strategy watchlist tab** | All 24 coins sorted by how close they are to a buy signal |
| **Setup cards tab** | The old setup-card analysis. **Learning only: it failed the backtest** |
| **Results tab** | Realized PnL, fees, funding (1D/7D/30D/90D) and each entry |
| **Journal tab** | Every trade opened and closed (from `trades.csv`) |
| **Account panel** | Balance, available margin, unrealized PnL, net PnL, win rate, bot slots used |
| **Status bar** (bottom) | Connection status, mini tickers, last update time |

### The "Market close" button
- **Immediately closes that whole position at the current market price** (a reduce-only market order).
- **Cancels its stop-loss and take-profit orders** on Binance.
- **Writes the close to the journal.**
- **Asks you to confirm first.**
- On a **bot trade**, the bot notices at its next check and stops managing that coin.
- Use it only when you have a reason, like cleaning up a test position. Closing bot trades by hand breaks the strategy's statistics.

### Overview page
- **Market heatmap:** tile size = 24h volume. Colour = 24h change, or switch to *Distance to signal* (brighter = closer to a buy; green = signal; blue = in trade; grey = below EMA 100).
- **What to expect:** the backtest numbers above.
- **Bot status:** running or stopped, countdown to the next daily check, slots used, coins closest to a signal, last log line.

### Account numbers explained
| Number | Meaning |
|---|---|
| Wallet balance | Money in the futures wallet (closed trades only) |
| Available | Balance minus margin locked in open positions |
| Unrealized PnL | Profit/loss of open positions if closed now (paper only) |
| Net PnL | Closed-trade profit/loss after fees and funding |
| Win rate | Share of closing fills that made money (tiny test trades count as losses because of fees) |
| Bot slots | Open positions out of 6. Manual positions count too |

---

## 7. How profit and loss are calculated

```
Long profit = (exit price − entry price) × size − fees − funding
```

- **Leverage** doesn't change the profit for the same size; it only changes how much margin is locked and how close liquidation is.
- **Unrealized** profit becomes **realized** when the position closes, then it's added to the wallet balance.
- **Fees:** ~0.05% of position value on entry and exit.
- **Funding:** paid or received every 8 hours while a position is open, usually ~0.01% of position value.

---

## 8. Safety features

| Feature | What it does |
|---|---|
| Demo by default | `BINANCE_ENV=demo`. Real money needs both `BINANCE_ENV=live` **and** `ALLOW_LIVE_TRADING=yes` |
| Fixed risk | 0.75% of balance per trade, sized from the stop |
| Max 6 positions | Limits total exposure (coins move together) |
| Isolated margin, 3x | A position can't use the rest of your balance |
| Stop always on Binance | Placed right after entry; if it can't be placed, the position is closed immediately |
| Stop repair | Every hour the bot checks each position still has its stop, and re-places it if missing |
| New stop before cancelling old | When the stop moves, the position is never unprotected |
| Only runs when you start it | No scheduled tasks; nothing trades while the window is closed |
| Stops before liquidation | Stop distance is always far inside the liquidation price |
| Keys stay local | API keys live in `.env`; the dashboard only runs on your PC (127.0.0.1) |
| Close button protection | Requires confirmation, and a special header so other websites can't trigger it |

---

## 9. Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `BINANCE_ENV` | `demo` | `demo` = fake money, `live` = real money |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | — | Your API keys (never share this file) |
| `ALLOW_LIVE_TRADING` | empty | Must be `yes` for live trading |
| `LEVERAGE` | `3` | Leverage for new positions (max `MAX_LEVERAGE`) |
| `RISK_PCT`, `REWARD_RISK` | `1`, `2` | Used by the manual `bot.py trade` command only (the trend bot uses 0.75%) |
| `MAX_RISK_PCT`, `MAX_LEVERAGE` | `2`, `5` | Hard limits the bot refuses to exceed |
| `JOURNAL_FILE` | `trades.csv` | Trade journal file |

The trend bot's strategy settings (coins, 55-day breakout, 20-day-low exit, 0.75% risk, 6 positions) are at the top of `trend_bot.py`.

### Before ever using real money
1. At least **3 months / 15+ trades on demo**, with results close to the backtest
2. Create **real API keys** with **withdrawals disabled** and an **IP restriction**
3. Use a **sub-account** with a small amount you can afford to lose
4. Consider lowering risk to **0.5%** for the first months

---

## 10. Files and commands

| File / command | Purpose |
|---|---|
| **`start.cmd`** | Start bot + dashboard (double-click) |
| `trend_bot.py run` | The live strategy (what `start.cmd` runs) |
| `trend_bot.py scan` | Show all 24 coins' signal status (no trading) |
| `trend_bot.py tick` | One check: daily cycle if due + stop check |
| `trend_bot.py selftest [COIN]` | Demo only: opens a small position, moves the stop, deletes and repairs it, closes |
| `dashboard.py` | Web dashboard |
| `bot.py status` / `history --days 7` | Account, positions, realized PnL, fees, funding |
| `bot.py plan / trade / close` | Manual trading tools with the same risk rules |
| `train_trend.py` | Retrain: walk-forward test on 24 coins with the newest data |
| `lab.py`, `validate_trend.py`, `backtest.py` | Research tools used to find and prove the strategy |
| `data.py` | Download historical candles and funding |
| `data/trend_bot.log` | Everything the bot did |
| `data/trend_state.json` | The bot's memory of its open trades (don't edit) |
| `trades.csv` | Trade journal |
| `PLAN.md` | Project history and decisions |

---

## 11. Troubleshooting

| Problem | What to do |
|---|---|
| **No trades for days or weeks** | Normal. The bot waits for a real 55-day breakout. Check the watchlist to see how close coins are |
| **Dashboard says "Bot is stopped"** | Double-click `start.cmd` |
| **Missed days (PC off)** | Fine. Signals up to 3 days old are still taken; stops on Binance protect open trades |
| **"Can't size it" in the log** | Not enough available margin, or the position would be below Binance's minimum. Free margin or accept the skip |
| **"stop order missing! Re-placing"** | The hourly safety check fixed it. If it repeats, check the Binance demo site |
| **Page doesn't load** | The dashboard isn't running: start it with `start.cmd` or `python dashboard.py` |
| **TradingView chart blank** | Needs internet access to tradingview.com; switch back to *Bot chart* |
| **Binance error about keys** | Demo API keys may have expired: create new ones at demo.binance.com → API Management and update `.env` |

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Long** | Buy expecting price to rise |
| **Breakout** | Price closes above a level it hasn't reached for a while (here: 55 days) |
| **EMA 100** | Average price of roughly the last 100 days (weighted to recent days); above it = uptrend |
| **ATR** | Average True Range: a coin's normal daily price movement |
| **Stop / stop-loss** | Order that closes the position when price falls to a level |
| **Trailing stop** | A stop that moves up as the trade goes well (here: follows the 20-day low) |
| **R** | The amount risked on a trade; results are measured in multiples of it |
| **Margin** | Money locked to hold a futures position |
| **Leverage** | Position value ÷ margin |
| **Isolated margin** | Each position uses only its own margin |
| **Liquidation** | Forced close when margin runs out. Our stops are always far before it |
| **Funding** | Small payment between longs and shorts every 8 hours |
| **Mark price** | Fair price Binance uses for stops and liquidation (resists sudden spikes) |
| **Backtest** | Testing rules on past data |
| **Walk-forward** | Choosing settings using only past years, then testing on the next year |
| **Overfitting** | Rules that fit past data perfectly but fail on new data |
| **Drawdown / worst drop** | Largest fall from a previous account high |
