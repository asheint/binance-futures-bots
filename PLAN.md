# Trading Assistant Plan

**Goal:** a bot that *reads the chart like a trader*: it draws structure, zones and patterns, explains **why** each matters, scores confirmations, shows "if this, then that" scenarios, and trades only when enough proven confirmations line up.

**Fixed decisions**
- Market: Binance USDⓈ-M futures, **BTCUSDT and ETHUSDT** first
- Timeframes: **4h for trend and zones**, **1h for triggers**
- Risk: **1% per trade**, isolated margin, max 5x, stop-loss and take-profit always placed
- The bot gives **scenarios, not predictions**
- Score weights and the trade threshold are **set by the backtest**, not by opinion

---

## Phase 1: Bot mechanics ✅ done 2026-09-13
- [x] Demo trade: position, stop-loss and take-profit appear on Binance
- [x] Close, `status`, `history`, journal verified
- [x] Fixes: exit price read from actual fill; prices rounded to tick size
- [x] Dashboard: account, positions with SL/TP, live chart (WebSocket), TradingView tab, results, journal

## Phase 2: Analysis engine and chart drawings (built 2026-09-13, waiting for your comparison)
- [x] Download 3 years of 1h/4h candles (BTC, ETH) into `data/` (`python data.py`)
- [x] Market structure: swing highs/lows, **HH / HL / LH / LL** labels, trend state, BOS / CHoCH
- [x] Support/resistance **zones** from clustered swing points (touch count = strength)
- [x] Fibonacci levels from the latest meaningful swing (legs under 3× ATR ignored)
- [x] EMA 50/200, RSI, ATR, volume vs average
- [x] Candle patterns: engulfing, hammer / shooting star
- [x] Drawn on the dashboard Bot chart with layer toggles, plus a plain-English analysis panel
- [ ] Your check: compare the bot's labels and zones with your own TradingView drawings

**Checkpoint:** you compare the bot's HH/HL and zones with your own TradingView drawings and they mostly match.

## Phase 3: Confirmations, setup cards, scenarios (Mode 1: Analyst)
- [ ] Confirmation checklist, each item with a plain-English reason and a drawing on the chart

| Confirmation | Starting weight |
|---|---|
| Higher-timeframe trend agrees | required + 2 |
| Price inside a support/resistance zone | 2 |
| Zone overlaps Fibonacci 0.5–0.618 | 1 |
| Trigger candle closed (engulfing / hammer) | 2 |
| Volume above average | 1 |
| RSI not stretched against the trade | 1 |
| Break-and-retest of a level | 1 |

- [x] **RSI divergence** (regular + hidden) added as a confirmation, drawn on the chart (built 2026-09-13)
- [x] **Required gates** (no trade without them): trend agrees, logical stop exists, reward ≥ 2R, no open position
- [x] Setup card: direction, score, ✅/⬜ checklist, entry/stop/target, size and risk
- [x] Scenarios: *"If zone holds → target X"*, *"If 1h closes below Y → invalid, next level Z"*
- [x] Long and short cards on the dashboard, with "Show plan on chart"
- [ ] **Mentor layer:** market briefing per candle close, "what I'm watching and why", explanations for skipped setups, and a post-trade review (what went right/wrong, lesson) for every closed trade
- [ ] **Teach mode:** before revealing its analysis, the bot asks you (trend? zone? would you trade?) and then compares your answer with its own
- [ ] Optional: Claude API writes the mentor explanations and answers your questions, working only from the engine's numbers. The engine decides; the AI explains and never places trades

**Checkpoint:** you read 10 setup cards and agree with the reasoning on most of them.

## Phase 3b: News and events layer
- [ ] **Economic calendar** (CPI, FOMC rate decisions, jobs report): countdown on the dashboard
- [ ] **Event gate:** no new trades from 30 min before to 30 min after a high-impact event; setup cards show the warning
- [ ] **Crypto news feed** (headlines with bullish/bearish tags) and **Binance announcements** (listings, delistings)
- [ ] **Fear & Greed index** as market-mood context
- [ ] Price-spike alert: "BTC moved 2% in 5 minutes, check the news"

## Phase 4: Backtester (proves what the score is worth)
- [x] Replays candles one by one (no future data)
- [x] Same analysis engine as live; fees, slippage and funding included
- [x] Results **grouped by score**: trades, win rate, average R, expectancy, drawdown
- [x] **Confirmation test:** result when each confirmation passed vs failed

### Result v1 (2026-09-13): FAILED, no edge. Do not trade the setup cards.
- 1,247 unique trades, BTC + ETH, Nov 2023 → Sep 2026: **−0.32R per trade after costs**, both in-sample and out-of-sample
- **No directional edge:** with fixed 1R / 1.5R / 2R targets the win rate equals breakeven, and trading the *opposite* direction gives the same result
- **Higher scores did worse**, not better: stacking more of these confirmations doesn't help
- **Costs ate 0.20R per trade** because stops were tight (median 0.58%)
- **Stops under 0.5% lost badly** (normal noise / stop hunts); "at zone" entries with the stop just past the zone lost more than mid-range entries, consistent with liquidity sweeps
- **Far targets (over 3.5R) rarely hit**
- Lessons for v2: minimum stop distance, targets capped near 2R, stops beyond sweeps, and a real source of edge must be proven before anything else

### Fix test (2026-09-13): mechanical fixes reduce losses but can't create an edge
- Best mechanical fix (stop ≥ 1.2% away, 2R target): −0.34R → **−0.09R** per trade on 2025–26, still negative
- Hindsight filter "only ETH longs" looked profitable on 2023–24 (+0.12R) and **lost on 2025–26 (−0.18R)**: overfitting confirmed
- Keep the mechanical fixes as defaults for every future strategy: stops ≥ 1.2% or ≥ 2× ATR, targets 1.5–2R

### Strategy lab (2026-09-13): `python lab.py`, report in `data/lab/report.md`
- [x] Tested 5 ideas × several settings × 1h/4h/1d, plus random-entry control; picked on 2023–24, judged on 2025–26
- ❌ Liquidity sweep, EMA pullback, breakout + retest, funding extremes: fail (most settings lose on 2025–26)
- 🟡 4h trend following: +0.09R, but random 4h entries did better in 2025–26, so not meaningful
- ✅ **Daily trend following** (new 20-day high above EMA 100 / new low below it, 2× ATR stop, trailing stop): **9/9 settings profitable** on 2025–26, picked settings +0.28R per trade, but only 38 trades
- [x] Stress test (`python validate_trend.py`): 12 coins, 2019/2020 → 2026, report in `data/validation/report.md`
  - 9 of 12 coins profitable; beats 300 random-entry runs with the same exits (p = 0.03)
  - **Longs beat random long-only entries in every setting (p ≈ 0.00–0.01)**: a real edge beyond crypto's upward drift
  - **Shorts lose in every setting** → long-only
  - Trail 4× ATR looked best but leaned on the 2020–21 bull run and lost in 2025; trail 3× ATR was most consistent
  - Weak year: 2022 crash (longs −0.60R per trade)

### Live strategy chosen (2026-09-13): `trend_bot.py`
Long-only daily trend following on 12 coins: close above the 20-day high and EMA 100 → buy next open; 2× ATR initial stop (≥1.2%); 3× ATR trailing stop; 120-day time exit; **0.75% risk per trade, max 6 open**.
Backtest 2020–2026 with those caps: ~+23%/year, worst drop ~15%. Expect losing streaks and a bad year in a crash.

- [x] Step 1: live bot (`python trend_bot.py scan` / `run --once` / `run`)
- [x] Self-test on demo passed (entry, stop, trailing move, missing-stop repair, close): `python trend_bot.py selftest`
- [x] Step 2: dashboard "Trend bot" panel (signals, distance to breakout, open trades with stops)
- [x] Step 3: runs only when you start it (2026-09-14, your choice): double-click `start.cmd` for bot + dashboard; scheduled task removed. Signals from up to 3 days back are still taken (backtest: +0.51R when 3 days late vs +0.50R on time)
### Retrained 2026-09-14: `python train_trend.py`
- Exit methods compared on 12 coins, then re-checked on 12 never-seen coins: "sell below the 20-day low" beat the 3× ATR trail on both sets (better on 9/12 new coins)
- Walk-forward on 24 coins (each year uses only settings best on earlier years): picked **55-day breakout + 20-day-low exit** every year 2022–2026 → +37.9% total (worst drop 16%) vs +7.8% for the old 20-day / 3× ATR settings
- **Live rules now:** 24 coins · close above 55-day high and EMA 100 · 2× ATR first stop · stop follows the 20-day low · 0.75% risk · max 6 open
- Last 3 years with these rules: ~+16%/yr, worst drop 16%, win rate ~27%, ~3 trades/month, 2026 so far −12%
- Full documentation: `BOT_GUIDE.md`

### Faster-entry tests (2026-09-14)
- **Intraday cross vs daily close of the 55-day high:** a little more return on some data (+43% vs +39%/yr) but deeper drops (21% vs 16%) and slightly worse on the 12 never-seen coins → keep close-confirmed entry
- **Intraday momentum lab** (`python intraday_lab.py`, report `data/intraday/report.md`): volume-spike breakout, 24 coins, 1h (3y) and 15m (2y), picked on older data, judged on the last 12 months
  - 1h: ❌ picked settings −0.02R per trade, account −19%, worst drop 48%
  - 15m: 🟡 picked settings +0.10R per trade, account +35% but **worst drop 39%**, only 12/24 settings profitable, older data just +0.03R
  - Signals beat random entries (−0.14 to −0.18R), so volume spikes carry some information, but after fees the edge is too thin and too unstable to trade
  - Possible next step: 15m "shadow mode" (log signals, no orders) for 1–2 months before deciding
- **"Check now" button** added: dashboard asks the running bot to run a full cycle within 30 seconds

### Sniper backtest (2026-09-30): `python sniper_backtest.py`, report in `data/sniper_backtest/report.md`
- Real `plan_coin()` replayed on every 15m candle, 24 coins, Sep 2025 → Sep 2026, managed like live (half at +1R, break-even, 48 h exit, altcoin cap 2)
- ❌ 2165 trades, 50% win, **−0.14R per trade, PF 0.74**, account −95% at 1% risk; lost in 12 of 13 months, longs and shorts, bounces and breakouts
- Half the trades hit the full stop: price does not respect these levels more than chance
- Same window, trend bot: 28 trades, −0.42R, −11% at 1% risk (a quiet year for trends, damage contained)

- [ ] Compare live results with the backtest monthly
- [ ] Known weaknesses to verify: candle patterns away from levels, divergence in strong trends, RSI filter in trends, overlapping trend checks
- [ ] Tune weights on **2023–2024**, verify once on **2025–2026** (never seen during tuning)
- [ ] Every trade exported with a chart snapshot so you can inspect it

**Pass criteria at the chosen threshold (out-of-sample, after fees)**
| Metric | Required |
|---|---|
| Trades | ≥ 100 |
| Expectancy | ≥ +0.15R per trade |
| Profit factor | ≥ 1.3 |
| Max drawdown | ≤ 15R |

If nothing passes: adjust the confirmation set (max 4 attempts) or change approach. Failing here costs no money.

## Phase 4b: Professional upgrades (each one backtested before it's kept)
- [ ] **Trade management:** partial take-profit at 1R, stop to breakeven, trailing stop vs fixed 2R, compared in the backtest
- [ ] **Market regime filter:** trending vs ranging (ADX + volatility); trend setups only in trends
- [ ] **Liquidity sweeps:** detect wicks below support / above resistance that reclaim the level; enter after the sweep; place stops beyond the sweep, not at obvious levels
- [ ] **Circuit breakers:** stop for the day after −3% or 3 consecutive losses; max trades per day
- [ ] **Funding rate + open interest:** flag crowded longs/shorts; avoid joining the crowd at extremes
- [ ] **Correlation guard:** BTC and ETH positions in the same direction count as one risk budget
- [ ] **Session filter:** measure results by Asia / London / New York session and weekends; skip the weak ones

## Phase 5: Place-trade button (Mode 2: Co-pilot)
- [ ] "Preview trade" on a setup card shows the exact order, size and risk
- [ ] "Place on demo" places entry + stop-loss + take-profit through the existing bot
- [ ] Journal stores the setup card (score + confirmations) with each trade

**Checkpoint:** 20+ co-pilot trades on demo, reviewed.

## Phase 6: Auto mode on demo (Mode 3)
- [ ] Bot trades automatically when score ≥ the backtest-proven threshold
- [ ] Daily loss limit and max trades per day
- [ ] Weekly review: demo results vs backtest

**Checkpoint:** 6+ weeks, demo expectancy close to backtest.

## Phase 7: Tiny real money (only if everything passed)
- [ ] Separate sub-account, small amount you accept losing, 0.5% risk per trade for the first month

## Later
- Chart patterns: double top/bottom, flags, triangles, head & shoulders
- Trend lines and channels
- Alerts to phone
- ML filter on top of the proven checklist

---

## Your learning track
| When | Study | Practice |
|---|---|---|
| Phase 2 | Market structure (Dow Theory), support/resistance | Mark HH/HL and 3–4 zones on BTC 4h in TradingView; screenshot for review |
| Phase 3 | Fibonacci, candle patterns, confluence | Judge each setup card: agree or disagree, and why |
| Phase 4 | R-multiples, expectancy, drawdown | Explain the backtest table in your own words |
| Phase 5–6 | Discipline, journaling | Weekly review of every trade |
