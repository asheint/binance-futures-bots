# Binance Futures Practice Bot

> **Start here: [BOT_GUIDE.md](BOT_GUIDE.md)**, the complete guide to the trend bot: how to run it, the strategy, what to expect, the dashboard, safety and troubleshooting. The sections below are the original setup notes.

A practice bot for Binance USDⓈ-M futures. It uses the **demo account (fake money)** by default.

> **Disclaimer:** this project is for learning and experimenting on Binance's demo account. It is **not financial advice**.
> Trading futures with real money can lose more than you expect, quickly. The strategies here are experiments; several
> lost money in the included backtests (see `LEARNING.md` and `data/*/report.md`). Use it at your own risk: the authors
> accept no responsibility for any losses. Real-money trading is off unless you deliberately enable it in `.env`.

Every trade it opens follows the same rules:
- **isolated margin** and **low leverage** (5x at most)
- a position size worked out so that hitting the stop-loss loses only **1% of your balance**
- a **stop-loss and take-profit** placed on Binance right after the entry. If they can't be placed, the bot closes the position immediately.
- a line in `trades.csv` for your trading journal

## 1. Get demo API keys (you do this part)

1. Log in at https://demo.binance.com. It uses your normal Binance account and its fake USDT balance.
2. Open the profile menu, then **API Management**, then **Create API**.
3. Turn on **Enable Futures**. Leave withdrawals off.
4. Copy the **API Key** and **Secret Key**. The secret is only shown once.

If demo.binance.com doesn't work in your region, try https://testnet.binancefuture.com and set
`BINANCE_BASE_URL=https://testnet.binancefuture.com` in `.env`.

## 2. Setup

```powershell
cd binance-futures-bot                # the folder you cloned
.\.venv\Scripts\Activate.ps1          # if the venv already exists
# otherwise: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
copy .env.example .env                # then paste your keys into .env
```

Never share `.env` or upload it anywhere.

## 3. Commands

| Command | What it does |
|---|---|
| `python bot.py plan BTCUSDT --stop 59400 --balance 1000` | Calculator only. Shows size, margin, max loss and liquidation price. No keys needed. |
| `python bot.py status` | Balance, open positions, stop-loss/take-profit orders |
| `python bot.py trade BTCUSDT --stop 59400` | Opens a sized trade after asking you to confirm. A stop **below** the price opens a long, **above** opens a short. |
| `python bot.py close BTCUSDT` | Closes the position at market and cancels its orders |
| `python bot.py history --days 7` | Realized profit/loss, fees, funding and win rate |
| `python bot.py run BTCUSDT --interval 15m` | Automatic EMA 9/21 crossover strategy with an ATR stop |
| `python dashboard.py` | Web dashboard at http://127.0.0.1:8000: balance, positions with SL/TP, live chart with the bot's analysis drawn on it, results, journal |
| `python analysis.py BTCUSDT 4h` | Prints the bot's chart reading: trend, structure breaks, zones, Fibonacci, candles, RSI, volume |
| `python data.py` | Downloads/updates 3 years of BTC and ETH 1h/4h candles into `data/` |
| **`start.cmd`** (double-click) | **Starts the trend bot and the dashboard.** The bot only trades while this window is open |
| `python trend_bot.py scan` | Shows the trend bot's signals and positions without trading |
| **`crazy.cmd`** (double-click) | Starts the crazy bot (demo only): longs and shorts on every liquid coin, 5+ of 9 confirmations, TP at +2 USDT net. See the top of `crazy_bot.py` |
| **`news.cmd`** (double-click) | Starts the news bot (demo only): shorts a coin right after Binance announces its delisting, 25% stop, closes after 4 h. See `LEARNING.md` section 3 |
| **`sniper.cmd`** (double-click) | Starts the sniper bot (demo only): trades like a discretionary trader — 4h trend + key level + a closed trigger candle at the level, stop beyond the level, target the next level (≥ 2R), half off at +1R. `python sniper_bot.py plan` prints its lines without trading |

Options for plan, trade and run: `--risk 1`, `--rr 2`, `--leverage 3`.

## Suggested practice routine

1. Use `plan` on several ideas to get a feel for position sizing.
2. Place 20–30 **manual** `trade`s. Write down why you took each one in the `note` column of `trades.csv`.
3. Check `history` every week. Look at your win rate and whether each win is bigger than each loss.
4. Try `run` to watch a system trade without emotions. Compare its results with yours.
5. Only think about real money after 1–2 consistent months, and then start with a tiny amount.
   Real money needs `BINANCE_ENV=live` **and** `ALLOW_LIVE_TRADING=yes`.

## Notes

- Binance requires stop-loss and take-profit orders to go through the Algo Order API (`/fapi/v1/algoOrder`) since 2025-12-09. This bot already does that.
- The liquidation price shown is an estimate. The stop-loss is always placed well before it.
- The EMA strategy is for practice. It is not a proven way to make money.
