# Learning notes

Notes from our learning sessions. Nothing here is built into the bots yet.

## 1. Confirmations: how many do we need? (2026-09-29)

**Short answer: with the crazy bot's 9 confirmations, no number of them makes 1h trades profitable.** They pick the direction about as well as a coin flip.

### What tutorials teach
- Most traders want **2–3 strong confirmations**. Some use a 5-step checklist: 5 pass = full size, 4 = smaller size, 3 or fewer = skip.
- **"Stack witnesses, not echoes":** confirmations only count if they come from different kinds of evidence. RSI + stochastic + MACD agreeing is one momentum reading, not three.
- The independent kinds: **trend/structure**, **location** (a key level marked beforehand), **behaviour** (rejection candle on volume), **timing** (trigger candle).
- Even fully-aligned setups lose often, and a target of at least 2× the stop is recommended.

### What outside evidence says
- 8 coins, 9 years of daily data: the MACD bullish cross was right 49.1% of the time, below the 49.9% chance level; the golden cross was also below chance. RSI < 30 had a small edge (about 54% once repeated signals are grouped).
- Hudson & Urquhart tested ~15,000 rules: they worked on older data, but for Bitcoin the predictive power disappeared on newer data.
- Crypto's hour-to-hour moves switch between continuing and reversing.

### Our own test
The bot's exact 9 confirmations on 3 years of 1h candles for 24 coins (Sep 2023 → Sep 2026), one trade per coin, TP = SL distance, fees 0.05%/side + 0.02% slippage.

TP = SL = 3.2% → break-even needs **52.2%** wins:

| Confirmations needed | Trades | Win rate |
|---|---|---|
| 3+ | 37,770 | 49.8% |
| 5+ (current) | 36,343 | 50.0% |
| 7+ | 23,059 | 49.8% |
| 9 of 9 | 4,181 | 48.7% |
| Random direction | 36,343 | 49.5% |

- Only +0.5% better than a coin flip. Every threshold loses after fees, in older data and in the last 12 months.
- Exactly 9/9 was the worst (44% wins): when everything agrees, the move has already happened.
- The 9 are really about 4 independent readings. EMA trend, EMA 9/21, Supertrend, 4h trend and structure all measure the trend.
- On their own: MACD +1.5%, volume +1.0% (tiny help); **RSI −2.7% and candle patterns −2.3% hurt**.
- Shorts beat longs over the last year (52% vs 45%): the market fell, it's not skill.
- Bigger targets (2× and 3× the stop) and 4h candles also stayed at random level.
- Earlier project research agrees (data/backtest, data/lab): more confirmations meant worse results, and every short-term YouTube-style setup failed. Only daily trend-following with a trailing stop passed (37–45% wins, winners run).

### Lessons
- The number of confirmations doesn't create an edge. What they measure, and whether they're independent, is what matters.
- Where profit came from in tests here: slower timeframes, exits that let winners run, maybe **location** (the bot uses none).
- A handful of live trades says nothing; win rates need hundreds of trades.

### Parked ideas (not built)
1. Test the exact rules from the YouTube videos (links still needed).
2. Test location: entries only at key support/resistance or the previous day's high/low.
3. Test an ADX trend-strength filter that skips choppy markets.
4. Test the bot's entries with a trailing stop instead of a fixed $2 target.

Sources (section 1): [MetaTrading Club](https://www.metatradingclub.com/confluence-in-trading/) · [FXOpen](https://fxopen.com/blog/en/what-is-confluence-in-trading-and-how-can-you-use-it/) · [Colibri Trader](https://www.colibritrader.com/confluence-in-trading/) · [Coinpaprika indicator test](https://coinpaprika.com/education/crypto-indicators-actually-work/) · [Hudson & Urquhart](https://link.springer.com/content/pdf/10.1007/s10479-019-03357-1.pdf) · [Intraday momentum/reversal study](https://www.sciencedirect.com/science/article/abs/pii/S1062940822000833) · [ADX filter backtests](https://optionsamurai.com/blog/backtesting-adx-filter/)

## 2. News trading: how it works (2026-09-29)

### Two kinds of news
- **Scheduled** (known time): US CPI, Fed/FOMC decisions, jobs reports, token unlocks, listings with a set start time. Everyone prepares in advance.
- **Unscheduled** (surprise): exchange hacks, Binance "will list" / "will delist" announcements, ETF approvals, regulators, big posts on X. Speed decides everything.

### How the fast players do it
1. The event happens (Binance announcement page updates, CPI published, a post on X).
2. Fast feeds (e.g. **Tree News**) watch the sources directly and push headlines over a websocket from Japan, near the exchanges' servers.
3. Bots act on keywords with pre-written rules ("Binance will list XYZ" → buy XYZ everywhere it already trades). Big firms (Jump, Wintermute) sit inside exchange data centres: orders in single-digit milliseconds.
4. Humans see it last, on X/Telegram, seconds to minutes later; just noticing a headline takes ~0.25 s.

### What the price usually does
- **Binance listings** (470 listings, 2021–2026): +24% on other exchanges in the 3 days *before* the announcement, +9.4% in the last 3 hours (information leaks). After listing it fades: buying at the listing-day close lost a median −4% after 1 day and −21% after 30 days; more hype = deeper fall. Delistings: −28.5% on the announcement day.
- **CPI** moves Bitcoin about 1.8× a normal hour, and the effect lasts. **FOMC** moves it less (positioned in advance). Volatility often rises before the release.
- **First seconds after news:** spreads widen 5–20×, the order book thins, stop clusters get swept, the move is exaggerated and often partly reverses.

### Styles
| Style | How | Reality for us |
|---|---|---|
| Race the headline | Fastest feed + bot in milliseconds | Needs paid feeds and exchange-side servers |
| Straddle | Orders above and below before the release | Slippage and spreads usually eat it |
| Fade the spike | Wait for the spike to run out, trade the pull-back | Most realistic for slower traders; risky if the trend truly changes |
| Buy the rumour, sell the news | Hold the run-up, exit at the news | Fits listing data, needs early information |
| News as a filter | Pause / smaller size around CPI and FOMC | Simplest and safest |

### Our speed (measured 2026-09-29, this PC)
- One request to Binance futures (fapi): **0.36–0.69 s**; to the demo servers: **0.48–1.2 s**; to Binance's announcement list: 0.45 s.
- Big firms: ~0.005 s. We are roughly **100× slower**, so racing the most-watched headlines isn't realistic from here.

### Ideas to test (not built)
1. Event study on our 3 years of candles: how BTC and altcoins moved around every CPI and FOMC release.
2. Whether pausing the crazy bot around those releases would have saved trades.
3. Whether fading the first spike after CPI worked.

Sources (section 2): [Binance listing study](https://github.com/Asalio123/binance-listing-study) · [Empirica: the Binance effect](https://empirica.io/blog/the-binance-effect-a-7-year-analysis-for-token-founders/) · [The Tie: listings in 2026](https://www.thetie.io/insights/what-does-an-exchange-listing-actually-deliver-in-2026) · [KSE thesis: Bitcoin vs FOMC and CPI](https://kse.ua/wp-content/uploads/2026/05/illia-nazaruk_268722_assignsubmission_file_nazaruk_final_thesis.pdf) · [Volatility reactions to macro news](https://www.sciencedirect.com/science/article/pii/S1059056025006720) · [NY Fed: Bitcoin–macro disconnect](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1052.pdf?sc_lang=en) · [Latency (Coinmonks)](https://medium.com/coinmonks/what-does-millisecond-execution-mean-and-why-does-latency-matter-eaa85c6ed3df) · [Tree of Alpha](https://www.treeofalpha.com/) · [CryptoPanic API](https://cryptopanic.com/developers/api/about) · [The news fade (Tradoki)](https://blog.tradoki.com/posts/the-news-fade-when-economic-prints-trap-retail) · [Why straddles fail](https://financialsource.co/why-straddle-news-trading-doesnt-work)

## 3. News event study: which Binance news still pays when we're late? (2026-09-29)

Every Binance listing/delisting announcement since 2023 (2,709 downloaded, exact timestamps from Binance's announcement API), kept when the coin already had a USDT perpetual at announcement time: **177 coin-events**. 1-minute futures candles from 3 h before to 3 days after. Costs: 0.3% round trip (fees + extra news slippage).

| Event (trade) | Coin trades | Best tested rule | Result |
|---|---|---|---|
| **Spot delisting (short)** + **futures delisting (short)** | 133 (56 announcements) | enter +1 min, hold 4 h, 25% stop | **+5.6% avg, 70% wins, worst −27%** |
| same | 133 | enter +1 min, hold 4 h, 15% stop | +4.8% avg, 65% wins, worst −17% |
| same | 133 | enter **+15 min**, hold 24 h, 15% stop | +5.8% avg, 59% wins |
| Spot listing (long) | 34 | — | too noisy: first-hour spikes, then fades |
| Margin delisting (short) | 10 | — | loses money |

- **Speed isn't the bottleneck:** entering 15 minutes late still worked; the drop plays out over hours.
- **Stops are essential:** with no stop the worst trade was −407% (ALPACA squeezed 3× after its delisting news).
- No run-up before delisting news (unlike listings, where leaks give +24% before the announcement).
- Funding cost for the short: about −0.07% over 4 h (included).
- By year (futures delistings, +1 min entry): 2024 −1.3% per day held (17 trades), 2025 +12.5%, 2026 +11.1%.

**Built:** `news_bot.py` / `news.cmd` (demo only). Watches the Delisting announcements every 2 s, shorts each coin with a futures contract, $50 loss at the 25% stop, 2× isolated, closes after 4 h. Shown on the robot page's News desk. Tested on demo 2026-09-29: STORJ short opened, stop placed at +25%, closed by the time exit, nothing left behind.

Study scripts: scratchpad `news/collect_events.py`, `news/analyze_events.py`, `news/risk_check.py`.

## 4. How traders use confirmations (the proper way) (2026-09-29)

Traders don't count indicators. They answer **a few different questions, in a fixed order**, and each question needs its own kind of evidence.

### The 5 questions (top-down)
| # | Question | What they look at | Timeframe |
|---|---|---|---|
| 1 | **Which way is the market going?** (context) | Structure: higher highs/lows = up, lower highs/lows = down. Price vs the 200 EMA. For altcoins, also what **BTC** is doing. | Daily / 4h |
| 2 | **Is price at a good place?** (location) | A **key level**: support/resistance zone, previous day's high/low, range edges, an old breakout level, the 0.5–0.618 Fibonacci pullback zone, VWAP, round numbers. **No level, no trade.** | 4h / 1h |
| 3 | **What is price doing at that level?** (setup) | Pullback into support in an uptrend, breakout and retest, **liquidity sweep** (a wick pokes through the level, the candle closes back inside), bounce off a range edge. | 1h |
| 4 | **Is it time to enter?** (trigger) | A confirmation candle **at the level**: engulfing, pin bar, a close back above/below the level, or a small break of structure on the lower timeframe. | 15m / 5m |
| 5 | **Does anything else agree?** (booster, optional) | Volume rising as price leaves the level, or **RSI divergence** at the level. At most one or two. | same |

**Rule:** 1, 2 and 4 are must-haves; 3 and 5 are bonuses.
- All 5 = A+ trade at full size.
- Trend + location + trigger = normal trade.
- Location or trigger missing = **skip**, however many indicators agree.

### Risk plan, decided before entering
- **Stop where the idea is proven wrong:** just beyond the level or the sweep wick, never a fixed amount.
- **Target the next level:** previous high/low or the other side of the range.
- **Skip if reward ÷ risk is under ~1.5–2.**
- Size the position from the stop distance.
- Manage the exit: many take half off at 1R and move the stop to break-even.

### "Not now" filters
- CPI, FOMC or other big news within about an hour.
- Choppy, trendless market (ADX below ~20, price whipping around a flat EMA).
- Extreme funding rates, or BTC dumping hard while wanting to long an altcoin.

### Worked example (long; a short is the mirror)
1. **Context:** SOL's 4h chart makes higher highs and lows, above the 200 EMA; BTC steady.
2. **Location:** pullback to an old breakout level that lines up with the 0.618 Fibonacci level.
3. **Setup:** on 1h a candle wicks just below the zone (sweep) and closes back inside.
4. **Trigger:** on 15m a bullish engulfing candle closes above the zone on rising volume.
5. **Plan:** enter on that close, stop just below the sweep wick, target the previous high at 2.5R.

### Compared with the crazy bot
| | Bot now | Proper traders |
|---|---|---|
| Trend | 5 of its 9 checks (the same idea five times) | 1 check, on a higher timeframe |
| **Location (key levels)** | **none** | **the most important one** |
| Trigger at the level | none (its candle check isn't tied to a level) | required |
| Stop / target | fixed $2 / $2 | structural: beyond the level, target the next level |

Note: the earlier backtests here (break and retest, sweeps, EMA pullbacks on BTC/ETH; `data/lab/report.md`) still lost money. This is a framework, not a guarantee: how precisely levels and exits are defined decides the result.

Side note, reverse experiment: flipping the bot's signals scored 49.8% wins over 3 years (50.8% in the last 12 months), still below the 52.2% needed after fees. Live it also lost, though most of its closed trades were closed by hand after minutes, not by TP/SL.

## 5. Waiting for price to cross a line: "if it goes here, long; if it goes there, short" (2026-09-29)

Traders mark their levels in advance and **let the market pick the direction**: above this price they're buyers, below that price sellers, in between they do nothing.

### Why they wait for a line
- **Price proves it first:** breaking a level shows real buying/selling pressure, which is stronger evidence than any indicator.
- **The middle is chop:** between levels price wanders; moves start at levels, where big buyers and sellers act.
- **No need to predict:** with a plan for both sides, they're ready whichever way it breaks.
- **The stop is obvious:** if price crosses back over the line, the idea was wrong.
- **No emotion, no chasing:** decisions are made calmly before the move.

### Two ways to use a line
| Idea | "If price…" | Order used |
|---|---|---|
| **Breakout**: follow the break | …goes above resistance → long; …goes below support → short | **Stop order** (buy-stop above price, sell-stop below), fires when price reaches it |
| **Bounce**: the level holds | …comes down to support → long; …comes up to resistance → short | **Limit order** waiting at the level |
| **Break and retest** | …breaks the line, then comes back to test it → enter on the retest | wait for the break, then a limit order at the old line |

**Touch or close?** Many wait for a 15m/1h candle to **close** beyond the line, because price often pokes through and snaps back (a "fakeout"). Fewer fake signals, slightly worse entry price.

### Example: BTC stuck between 60,000 and 62,000
| Plan | Trigger | Stop | Target |
|---|---|---|---|
| Long | 1h candle closes above 62,000 | 61,400 (back inside the range) | 63,800 |
| Short | 1h candle closes below 60,000 | 60,600 | 58,200 |
| In between | do nothing | | |

- When one side triggers, cancel the other.
- If neither triggers within a set time, or big news is coming, cancel both and re-plan.

### On Binance futures
- **Conditional orders** (Stop Market / Stop Limit) sit on Binance and fire when price reaches the trigger; a buy-stop above and a sell-stop below can wait at the same time.
- **Limit orders** wait at a level for bounces.
- No built-in "one cancels the other" for entries: you or a bot cancel the other side once one fills.
- Risks: in fast moves a stop-market entry can fill worse than the trigger (slippage); a fakeout can trigger and reverse, which is why many wait for a close or a retest.

### Compared with our bots
The crazy bot enters at market the moment it scans, wherever price is (often the middle). A line-based version would find each coin's key levels during the scan, place conditional orders on both sides, trade only when price breaks or reaches a level, and cancel the unused side and anything stale. (Idea only, not built.)
