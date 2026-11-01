#!/usr/bin/env python3
"""Replay and bootstrap an NSE intraday plan before risking capital.

The simulation uses the ticker's own 5-minute Yahoo bars (up to 60 days). It
does not forecast returns. It answers a narrower question: under intraday bar
shapes recently observed in this stock, which plan boundary tends to be hit
first? All same-bar stop/target collisions are conservatively counted as stop
first.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys

import nsemkt


def sessions(bars: list[dict]) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for bar in bars:
        t = bar["t"]
        if t.weekday() < 5 and dt.time(9, 15) <= t.time() <= dt.time(15, 15):
            grouped.setdefault(t.date().isoformat(), []).append(bar)
    out = []
    for day in sorted(grouped):
        one = sorted(grouped[day], key=lambda b: b["t"])
        if len(one) >= 20:
            out.append(one)
    return out


def boundary_result(path: list[dict], entry: float, stop: float, target: float,
                    start_index: int = 0) -> tuple[str, float]:
    """Apply absolute boundaries to historical bars; stop wins ambiguity."""
    risk = entry - stop
    if risk <= 0:
        return "invalid", 0.0
    for bar in path[start_index:]:
        hit_stop = bar["l"] <= stop
        hit_target = bar["h"] >= target
        if hit_stop:  # conservative when both fall in the same OHLC bar
            return "stop", -1.0
        if hit_target:
            return "target", (target - entry) / risk
    close = path[-1]["c"]
    return "none", (close - entry) / risk


def historical_replay(all_sessions: list[list[dict]], entry: float, stop: float,
                      target: float) -> dict:
    counts = {"target": 0, "stop": 0, "none": 0}
    r_values: list[float] = []
    fired = 0
    examples: list[dict] = []
    for day in all_sessions:
        eligible = [i for i, b in enumerate(day) if b["t"].time() >= dt.time(9, 30)]
        trigger_i = None
        for i in eligible:
            previous_close = day[i - 1]["c"] if i else day[i]["o"]
            # Entry is triggered by an upward cross through the level.
            if previous_close <= entry <= day[i]["h"]:
                trigger_i = i
                break
        if trigger_i is None:
            continue
        fired += 1
        result, r = boundary_result(day, entry, stop, target, trigger_i)
        counts[result] += 1
        r_values.append(r)
        if len(examples) < 10:
            examples.append({
                "date": day[0]["t"].date().isoformat(),
                "trigger_ist": day[trigger_i]["t"].strftime("%H:%M"),
                "result": result,
                "r": round(r, 3),
            })
    return {
        "sessions_checked": len(all_sessions),
        "setups_fired": fired,
        "target": counts["target"],
        "stop": counts["stop"],
        "none": counts["none"],
        "target_rate": round(counts["target"] / fired, 4) if fired else None,
        "stop_rate": round(counts["stop"] / fired, 4) if fired else None,
        "average_r": round(sum(r_values) / len(r_values), 4) if r_values else None,
        "examples": examples,
    }


def monte_carlo(all_sessions: list[list[dict]], entry: float, stop: float,
                target: float, sims: int, seed: int) -> dict:
    rng = random.Random(seed)
    risk = entry - stop
    reward_r = (target - entry) / risk
    counts = {"target": 0, "stop": 0, "none": 0}
    r_values: list[float] = []

    # Each sampled bar contributes its observed high/low/close move relative to
    # its own open. We bootstrap (shuffle with replacement) within one sampled
    # session, starting every synthetic path at the proposed entry.
    shapes: list[list[tuple[float, float, float]]] = []
    for day in all_sessions:
        afternoon = [b for b in day if b["t"].time() >= dt.time(9, 30) and b["o"] > 0]
        if afternoon:
            shapes.append([(b["h"] / b["o"], b["l"] / b["o"], b["c"] / b["o"])
                           for b in afternoon])
    if not shapes:
        raise ValueError("not enough complete intraday sessions for simulation")

    for _ in range(sims):
        template = rng.choice(shapes)
        current = entry
        outcome = "none"
        for _step in range(len(template)):
            high_ratio, low_ratio, close_ratio = rng.choice(template)
            hi, lo = current * high_ratio, current * low_ratio
            if lo <= stop:  # conservative same-bar ordering
                outcome = "stop"
                current = stop
                break
            if hi >= target:
                outcome = "target"
                current = target
                break
            current *= close_ratio
        counts[outcome] += 1
        if outcome == "stop":
            r_values.append(-1.0)
        elif outcome == "target":
            r_values.append(reward_r)
        else:
            r_values.append((current - entry) / risk)

    return {
        "sims": sims,
        "seed": seed,
        "target": counts["target"],
        "stop": counts["stop"],
        "none": counts["none"],
        "p_target": round(counts["target"] / sims, 4),
        "p_stop": round(counts["stop"] / sims, 4),
        "p_none": round(counts["none"] / sims, 4),
        "avg_r": round(sum(r_values) / len(r_values), 4),
    }


def verdict(mc: dict, hist: dict) -> str:
    pt, ps, ar = mc["p_target"], mc["p_stop"], mc["avg_r"]
    if hist["setups_fired"] < 5:
        return "INSUFFICIENT_HISTORY - fewer than 5 comparable historical triggers"
    if pt >= ps + 0.10 and ar > 0:
        return "FAVOURABLE_IN_SAMPLE - target-first leads, but validate out of sample"
    if ps >= pt + 0.10 or ar < -0.10:
        return "UNFAVOURABLE_IN_SAMPLE - stop-first dominates recent bar shapes"
    return "MIXED - no robust target-first edge in this sample"


def main() -> None:
    p = argparse.ArgumentParser(description="Bootstrap and historically replay an NSE intraday plan.")
    p.add_argument("--plan", default=os.path.join(nsemkt.STATE_DIR, "plan.json"))
    p.add_argument("--sims", type=int, default=10_000)
    p.add_argument("--days", type=int, default=60,
                   help="requested 5-minute history, maximum 60 (default 60)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    plan = nsemkt.load_json(args.plan)
    if not plan:
        print(f"REFUSED: no plan at {args.plan}", file=sys.stderr)
        sys.exit(2)
    try:
        entry, stop, target = (float(plan[k]) for k in ("entry", "stop", "target"))
        ticker = str(plan["ticker"]).upper()
    except (KeyError, TypeError, ValueError):
        print("REFUSED: plan must contain ticker, entry, stop and target", file=sys.stderr)
        sys.exit(2)
    if not (0 < stop < entry < target):
        print("REFUSED: require 0 < stop < entry < target", file=sys.stderr)
        sys.exit(2)
    if not (100 <= args.sims <= 1_000_000):
        print("REFUSED: --sims must be from 100 to 1,000,000", file=sys.stderr)
        sys.exit(2)
    days = max(5, min(60, args.days))

    try:
        bars = nsemkt.yahoo_chart(ticker, "5m", f"{days}d")["bars"]
        all_sessions = sessions(bars)
        if len(all_sessions) < 3:
            raise ValueError("fewer than 3 complete sessions returned")
        hist = historical_replay(all_sessions, entry, stop, target)
        mc = monte_carlo(all_sessions, entry, stop, target, args.sims, args.seed)
    except (RuntimeError, ValueError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)

    result = {
        "generated_ist": nsemkt.now_ist().isoformat(timespec="seconds"),
        "ticket": plan.get("ticket"),
        "ticker": ticker,
        "entry": entry, "stop": stop, "target": target,
        "sims": mc["sims"],
        "p_target": mc["p_target"],
        "p_stop": mc["p_stop"],
        "p_none": mc["p_none"],
        "avg_r": mc["avg_r"],
        "verdict": verdict(mc, hist),
        "historical": hist,
        "monte_carlo": mc,
        "limitations": [
            "Uses delayed Yahoo 5-minute bars and only recent sessions.",
            "Bootstrap resampling does not preserve news, regime or serial dependence.",
            "If stop and target appear inside one 5-minute bar, stop is counted first.",
            "Charges, slippage, gaps, circuit limits and rejected orders are not simulated.",
        ],
    }
    out_dir = args.out or nsemkt.STATE_DIR
    path = nsemkt.save_json(os.path.join(out_dir, "sim.json"), result)
    print(f"TIME MACHINE  {ticker}  {args.sims:,} simulations  {len(all_sessions)} sessions")
    print(f"  target first : {mc['p_target']*100:5.1f}%")
    print(f"  stop first   : {mc['p_stop']*100:5.1f}%")
    print(f"  neither      : {mc['p_none']*100:5.1f}%")
    print(f"  average R    : {mc['avg_r']:+.3f}")
    print(f"  history      : {hist['setups_fired']} comparable triggers")
    print(f"  verdict      : {result['verdict']}")
    print(f"  saved        : {path}")


if __name__ == "__main__":
    main()
