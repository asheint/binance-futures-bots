"""Setup cards: turns the chart reading into required gates, a confirmation checklist, a plan and scenarios.

The higher timeframe (4h) gives the trend; the lower timeframe (1h) gives location and the trigger.
Weights and thresholds here are starting guesses. The Phase 4 backtest decides the real ones.
"""
from __future__ import annotations

from models import price_text

WEIGHTS = {"htf_trend": 2, "ltf_structure": 1, "location": 2, "fib": 1, "trigger": 2, "divergence": 1,
           "volume": 1, "rsi": 1, "ema": 1}
RECENT_DIVERGENCE = 15  # candles
READY_SCORE = 7
FORMING_SCORE = 5
MIN_RR = 2.0
TREND_WORDS = {"up": "up (HH + HL)", "down": "down (LH + LL)", "range": "mixed / ranging", "unclear": "unclear"}


def zone_text(zone: dict) -> str:
    return f"{price_text(zone['low'])}–{price_text(zone['high'])}"


def evaluate(htf: dict, ltf: dict, has_position: bool = False, htf_name: str = "4h", ltf_name: str = "1h") -> list[dict]:
    cards = [build_card(side, htf, ltf, has_position, htf_name, ltf_name) for side in ("long", "short")]
    return sorted(cards, key=lambda c: (c["status_rank"], c["score"]), reverse=True)


def build_card(side: str, htf: dict, ltf: dict, has_position: bool, htf_name: str, ltf_name: str) -> dict:
    long = side == "long"
    want = "up" if long else "down"
    zone_side, opposite_side = ("support", "resistance") if long else ("resistance", "support")
    crowd = "buyers" if long else "sellers"
    price = ltf["price"]
    atr = ltf["indicators"]["atr"]
    checks: list[dict] = []

    def check(key: str, label: str, passed: bool, text: str) -> None:
        checks.append({"key": key, "label": label, "status": "pass" if passed else "fail",
                       "points": WEIGHTS[key] if passed else 0, "max": WEIGHTS[key], "text": text})

    # 1. Bigger trend
    htf_ok = htf["trend"] == want
    check("htf_trend", f"{htf_name} trend", htf_ok,
          f"{htf_name} structure is {TREND_WORDS[htf['trend']]}."
          + ("" if htf_ok else f" {'Longs' if long else 'Shorts'} would fight the bigger trend."))

    # 2. Entry timeframe structure
    recent_break = next((b for b in reversed(ltf["breaks"]) if b["ago"] <= 12), None)
    if ltf["trend"] == want:
        ltf_ok, text = True, f"{ltf_name} structure is also {TREND_WORDS[want]}."
    elif recent_break and recent_break["direction"] == want:
        ltf_ok, text = True, f"{ltf_name} just broke structure {want} ({recent_break['kind']}, {recent_break['ago']} candles ago)."
    else:
        ltf_ok, text = False, f"{ltf_name} structure is {TREND_WORDS[ltf['trend']]}, with no recent break {want}."
    check("ltf_structure", f"{ltf_name} structure", ltf_ok, text)

    # 3. Location: at a zone where the crowd stepped in before
    zones = [(ltf_name, z) for z in ltf["zones"][zone_side]] + [(htf_name, z) for z in htf["zones"][zone_side]]
    near = [(tf, z) for tf, z in zones if z["low"] - 0.5 * atr <= price <= z["high"] + 0.5 * atr]
    zone_tf, zone = max(near, key=lambda item: item[1]["touches"]) if near else (None, None)
    if zone:
        text = f"Price is at {zone_side} {zone_text(zone)} ({zone_tf}, {zone['touches']} touches), where {crowd} stepped in before."
    elif zones:
        tf, nearest = min(zones, key=lambda item: abs(price - (item[1]["high"] if long else item[1]["low"])))
        distance = abs(price - (nearest["high"] if long else nearest["low"])) / price * 100
        text = f"Not at a {zone_side} zone. Nearest is {zone_text(nearest)} ({tf}), {distance:.2f}% away. Mid-range entries have poor stops."
    else:
        text = f"No {zone_side} zone in view."
    check("location", f"At {zone_side}", zone is not None, text)

    # 4. Fibonacci pullback
    fibs = [(tf, a["fib"]) for tf, a in ((htf_name, htf), (ltf_name, ltf)) if a["fib"] and a["fib"]["direction"] == want]
    golden = next(((tf, f) for tf, f in fibs if f["golden"][0] - 0.25 * atr <= price <= f["golden"][1] + 0.25 * atr), None)
    if golden:
        text = f"Price is in the {golden[0]} Fibonacci golden zone {price_text(golden[1]['golden'][0])}–{price_text(golden[1]['golden'][1])}, a common {'pullback' if long else 'bounce'} area."
    elif fibs:
        tf, f = fibs[0]
        text = f"Outside the {tf} golden zone {price_text(f['golden'][0])}–{price_text(f['golden'][1])}."
    else:
        text = f"No {want}-leg to measure a Fibonacci {'pullback' if long else 'bounce'} from."
    check("fib", "Fibonacci zone", golden is not None, text)

    # 5. Trigger candle
    trigger = next((p for p in reversed(ltf["patterns"]) if p["ago"] <= 1 and p["direction"] == ("bull" if long else "bear")), None)
    if trigger:
        when = "on the last closed" if trigger["ago"] == 0 else "on the previous"
        text = f"{trigger['name']} {when} {ltf_name} candle: {crowd} are reacting now."
    else:
        text = f"No {'bullish engulfing or hammer' if long else 'bearish engulfing or shooting star'} on the last 2 {ltf_name} candles yet."
    check("trigger", "Trigger candle", trigger is not None, text)

    # 6. RSI divergence in the trade direction (either timeframe)
    divergences = [(tf, d) for tf, a in ((ltf_name, ltf), (htf_name, htf))
                   for d in a["divergences"] if d["ago"] <= RECENT_DIVERGENCE]
    with_trade = next(((tf, d) for tf, d in divergences if d["kind"] == ("bullish" if long else "bearish")), None)
    against = next(((tf, d) for tf, d in divergences if d["kind"] == ("bearish" if long else "bullish")), None)
    if with_trade:
        tf, d = with_trade
        text = f"{'Hidden ' if d['variant'] == 'hidden' else ''}{d['kind']} divergence on {tf}: " + (
            "momentum is turning in favour of the trade." if d["variant"] == "regular" else "momentum says the trend should continue.")
    elif against:
        tf, d = against
        text = f"Warning: {d['kind']} divergence on {tf}; momentum is against {'longs' if long else 'shorts'}."
    else:
        text = "No RSI divergence either way."
    check("divergence", "RSI divergence", with_trade is not None, text)

    # 7. Volume
    ratio = ltf["indicators"]["volume_ratio"]
    volume_ok = ratio is not None and ratio >= 1.3
    check("volume", "Volume", volume_ok,
          f"Volume {ratio:.1f}× average: " + ("real participation." if volume_ok else "no extra participation yet.")
          if ratio is not None else "Volume data unavailable.")

    # 7. RSI not stretched against the trade
    rsi = ltf["indicators"]["rsi"]
    rsi_ok = rsi is not None and (rsi < 70 if long else rsi > 30)
    if rsi is None:
        text = "RSI unavailable."
    elif rsi_ok:
        text = f"RSI {rsi:.0f}: not {'overbought' if long else 'oversold'}, room to move."
    else:
        text = f"RSI {rsi:.0f}: {'overbought' if long else 'oversold'}; entering now is chasing."
    check("rsi", "RSI", rsi_ok, text)

    # 8. EMA filter on the bigger timeframe
    ema50, ema200 = htf["indicators"]["ema50"], htf["indicators"]["ema200"]
    if ema50 is None or ema200 is None:
        ema_ok, text = False, "Not enough data for EMA 200."
    else:
        ema_ok = (price > ema200 and ema50 > ema200) if long else (price < ema200 and ema50 < ema200)
        text = (f"{htf_name}: price {'above' if price > ema200 else 'below'} EMA 200, EMA 50 {'above' if ema50 > ema200 else 'below'} EMA 200"
                + (" (agrees)." if ema_ok else " (disagrees)."))
    check("ema", f"{htf_name} EMA filter", ema_ok, text)

    score = sum(c["points"] for c in checks)
    max_score = sum(WEIGHTS.values())

    # ---- plan: stop beyond the zone (or last swing), target at the next opposing zone ----
    entry = price
    stop_note = ""
    if zone:
        stop = zone["low"] - 0.25 * atr if long else zone["high"] + 0.25 * atr
        stop_reason = f"beyond the {zone_side} zone"
    else:
        swing = next((s for s in reversed(ltf["swings"])
                      if s["kind"] == ("low" if long else "high") and (s["price"] < entry if long else s["price"] > entry)), None)
        if swing:
            stop = swing["price"] - 0.25 * atr if long else swing["price"] + 0.25 * atr
            stop_reason = f"beyond the last {ltf_name} swing {'low' if long else 'high'}"
        else:
            stop = entry - 1.5 * atr if long else entry + 1.5 * atr
            stop_reason = "1.5× ATR (no swing to hide behind)"
    if abs(entry - stop) < 0.5 * atr:
        stop = entry - 0.5 * atr if long else entry + 0.5 * atr
        stop_note = "Stop widened to 0.5× ATR so normal wiggles don't hit it."
    risk = abs(entry - stop)
    stop_ok = risk <= 4 * atr

    opposing = [z for z in ltf["zones"][opposite_side] + htf["zones"][opposite_side]
                if (z["low"] > entry + 0.1 * atr if long else z["high"] < entry - 0.1 * atr)]
    if opposing:
        target_zone = min(opposing, key=lambda z: abs(z["low" if long else "high"] - entry))
        target = target_zone["low"] if long else target_zone["high"]
        target_reason = f"front of {opposite_side} {zone_text(target_zone)}"
    else:
        target = entry + 2 * risk if long else entry - 2 * risk
        target_reason = f"no {opposite_side} in view, default 2R"
    rr = abs(target - entry) / risk

    gates = [
        {"label": f"{htf_name} trend agrees", "pass": htf_ok,
         "text": "Trading with the bigger trend." if htf_ok else f"{htf_name} trend is {TREND_WORDS[htf['trend']]}."},
        {"label": "Logical stop", "pass": stop_ok,
         "text": f"Stop {price_text(stop)} {stop_reason} ({risk / entry * 100:.2f}% away)."
                 + ("" if stop_ok else " Too far: more than 4× ATR.")},
        {"label": f"Reward ≥ {MIN_RR:g}R", "pass": rr >= MIN_RR,
         "text": f"Target {price_text(target)} ({target_reason}) = {rr:.1f}R."
                 + ("" if rr >= MIN_RR else f" The {opposite_side} is too close; not worth the risk.")},
        {"label": "No open position", "pass": not has_position,
         "text": "Account is free for a new trade." if not has_position else "Already in a trade on this symbol."},
    ]
    gates_ok = all(g["pass"] for g in gates)

    if gates_ok and score >= READY_SCORE:
        status, rank = "ready", 2
        summary = (f"All required checks pass with {score}/{max_score}. This is the kind of setup the plan is built for. "
                   "Risk 1%, place the stop, and let the trade play out.")
    elif htf_ok and score >= FORMING_SCORE:
        status, rank = "forming", 1
        missing = [c["label"] for c in checks if c["status"] == "fail"]
        blocked = [g["label"] for g in gates if not g["pass"]]
        summary = f"Setup forming ({score}/{max_score}). Still missing: {', '.join(missing)}."
        if blocked:
            summary += f" Blocked by: {', '.join(blocked)}."
        if not trigger:
            where = zone_text(zone) if zone else f"a {zone_side} zone"
            summary += (f" What would complete it: a {'bullish engulfing or hammer' if long else 'bearish engulfing or shooting star'} "
                        f"closing at {where}.")
    else:
        status, rank = "no-trade", 0
        if not htf_ok:
            summary = (f"No {side}: the {htf_name} trend is {TREND_WORDS[htf['trend']]}. "
                       "Professionals don't fight the bigger trend; this side is off until the structure changes.")
        else:
            summary = f"No {side} yet: only {score}/{max_score} confirmations. Wait for price to reach a zone and show a trigger."

    below_stop = [z for z in ltf["zones"][zone_side] + htf["zones"][zone_side]
                  if (z["high"] < stop if long else z["low"] > stop)]
    next_zone = min(below_stop, key=lambda z: abs(stop - (z["high"] if long else z["low"])), default=None)
    hold = (f"{zone_side} {zone_text(zone)} holds" if zone
            else f"price stays {'above' if long else 'below'} {price_text(stop)}")
    scenarios = [
        {"tone": "bull" if long else "bear",
         "text": f"If {hold} and a {ltf_name} candle closes {'bullish' if long else 'bearish'} → move toward "
                 f"{price_text(target)} ({target_reason}), {rr:.1f}R."},
        {"tone": "bear" if long else "bull",
         "text": f"If a {ltf_name} candle closes {'below' if long else 'above'} {price_text(stop)} → the idea is wrong. "
                 + (f"Next {zone_side}: {zone_text(next_zone)}." if next_zone
                    else f"No {zone_side} {'below' if long else 'above'} that in view.")},
    ]

    return {
        "side": side, "status": status, "status_rank": rank, "score": score, "max_score": max_score,
        "summary": summary, "gates": gates, "checks": checks, "scenarios": scenarios,
        "plan": {"entry": entry, "stop": stop, "target": target, "rr": rr, "stop_note": stop_note},
    }
