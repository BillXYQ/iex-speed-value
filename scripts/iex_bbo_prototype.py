#!/usr/bin/env python3
"""Stage 1 IEX prototype: build an IEX `bbo` table from the course parser's tick
file and produce descriptive statistics and figures.

  python3 scripts/iex_bbo_prototype.py \
      --tick-file iexdownloaderparser/data/text_tick_data/tick_SPY_20220801.txt.gz \
      --book-file iexdownloaderparser/data/book_snapshots/20220801_book_updates.csv.gz

Paths are relative to raw_data_dir (src/config.py). Outputs:
  {parsed_data_dir}/iex/YYYYMMDD/SPY_bbo.parquet   (gitignored)
  results/iex_bbo_YYYYMMDD/summary.md + figures     (small, committed)

Data caveat: this is DEEP (price levels), not DEEP+, and its timestamps are IEX-TP
packet send times; see src/research/course_parser_io.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.research import bbo_stats as st  # noqa: E402
from src.research.course_parser_io import build_bbo, read_tick_file  # noqa: E402
from src.research.schema import PRICE_SCALE, validate_bbo  # noqa: E402

# Chart styling: light surface, recessive axes, categorical slots 1-2.
BLUE, ORANGE = "#257de0", "#f47230"
TEXT, TEXT2, GRID = "#191919", "#666666", "#e5e5e5"
SPEED_BUMP_US = 350


def style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", color=TEXT, fontsize=12, pad=10)
    ax.set_xlabel(xlabel, color=TEXT2)
    ax.set_ylabel(ylabel, color=TEXT2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT2)


def ecdf(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(x, dtype=float))
    return x, np.arange(1, len(x) + 1) / len(x)


def cross_check(bbo: pd.DataFrame, book_path: Path) -> dict:
    """Compare our BBO with the course parser's level-1 book snapshots at the same seq."""
    book = pd.read_csv(book_path, usecols=["MESSAGE_ID", "BID_PRICE_1", "BID_SIZE_1", "ASK_PRICE_1", "ASK_SIZE_1"])
    book = book.drop_duplicates("MESSAGE_ID", keep="last").sort_values("MESSAGE_ID")
    ours = bbo[["seq", "bid_px", "bid_sz", "ask_px", "ask_sz"]].sort_values("seq")
    m = pd.merge_asof(book, ours, left_on="MESSAGE_ID", right_on="seq", direction="backward")
    eq = (
        (np.rint(m["BID_PRICE_1"] * PRICE_SCALE) == m["bid_px"].astype("float64"))
        & (m["BID_SIZE_1"] == m["bid_sz"].astype("float64"))
        & (np.rint(m["ASK_PRICE_1"] * PRICE_SCALE) == m["ask_px"].astype("float64"))
        & (m["ASK_SIZE_1"] == m["ask_sz"].astype("float64"))
    )
    return {"course_snapshots": int(len(m)), "matching": int(eq.sum()), "match_rate": float(eq.mean())}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tick-file", required=True, help="course tick file, relative to raw_data_dir")
    p.add_argument("--book-file", help="course book_updates CSV for cross-checking (optional)")
    p.add_argument("--symbol", default="SPY")
    a = p.parse_args(argv)

    raw = config.raw_data_dir()
    tick_path = raw / a.tick_file
    date_str = re.search(r"(\d{8})", tick_path.name).group(1)
    trade_date = dt.datetime.strptime(date_str, "%Y%m%d").date()

    print(f"Reading {tick_path}")
    levels, trades = read_tick_file(tick_path)
    bbo = build_bbo(levels, venue="iex", symbol=a.symbol)
    report = validate_bbo(bbo)
    print(f"BBO rows: {len(bbo):,}  validation: {report}")
    if not report.ok:
        sys.exit("bbo failed validation; stopping")

    out_parquet = config.parsed_data_dir() / "iex" / date_str / f"{a.symbol}_bbo.parquet"
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    bbo.to_parquet(out_parquet, index=False)
    print(f"Wrote {out_parquet}")

    check = cross_check(bbo, raw / a.book_file) if a.book_file else None
    if check:
        print(f"Cross-check vs course book snapshots: {check}")

    rh = st.regular_hours(bbo, trade_date)
    rh_trades = st.regular_hours(trades, trade_date)
    summary = st.summarize(rh, rh_trades)

    res = config.results_dir() / f"iex_bbo_{date_str}"
    res.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "figure.dpi": 150})

    # 1. BBO updates per minute
    mins = pd.to_datetime(rh["ts_exch_ns"], utc=True).dt.tz_convert("America/New_York").dt.floor("min")
    per_min = mins.value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(per_min.index, per_min.values, color=BLUE, linewidth=2)
    style(ax, f"IEX {a.symbol} BBO updates per minute, {trade_date}", "New York time", "updates / minute")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M", tz=per_min.index.tz))
    fig.tight_layout(); fig.savefig(res / "updates_per_minute.png"); plt.close(fig)

    # 2. Time between BBO updates
    x, y = ecdf(st.update_intervals_us(rh))
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.plot(x, y, color=BLUE, linewidth=2)
    ax.set_xscale("log")
    ax.axvline(SPEED_BUMP_US, color=TEXT2, linewidth=1, linestyle="--")
    ax.text(SPEED_BUMP_US * 1.1, 0.04, "350µs speed bump", color=TEXT2, fontsize=9)
    style(ax, f"Time between IEX {a.symbol} BBO updates (CDF)", "microseconds (log scale)", "share of intervals")
    fig.tight_layout(); fig.savefig(res / "update_interval_cdf.png"); plt.close(fig)

    # 3. How long a best price stays at the top (bid vs ask)
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for side, color in (("bid", BLUE), ("ask", ORANGE)):
        life = st.price_lifetimes_us(rh, side)["lifetime_us"].to_numpy()
        x, y = ecdf(life)
        ax.plot(x, y, color=color, linewidth=2, label=f"best {side}")
        i = int(len(x) * 0.62)
        ax.text(x[i] * 1.3, y[i] - 0.06 if side == "bid" else y[i] + 0.02, f"best {side}", color=TEXT, fontsize=9)
    ax.set_xscale("log")
    ax.axvline(SPEED_BUMP_US, color=TEXT2, linewidth=1, linestyle="--")
    ax.text(SPEED_BUMP_US * 1.1, 0.04, "350µs speed bump", color=TEXT2, fontsize=9)
    ax.legend(frameon=False, loc="upper left", labelcolor=TEXT)
    style(ax, f"How long a best price lasts on IEX, {a.symbol} (CDF)", "microseconds (log scale)", "share of price runs")
    fig.tight_layout(); fig.savefig(res / "best_price_lifetime_cdf.png"); plt.close(fig)

    # 4. Spread, share of time
    share = st.time_weighted_share(st.spread_ticks(rh), rh)
    cap = 20
    bars = share[share.index <= cap].reindex(range(1, cap + 1), fill_value=0.0)
    labels = [str(k) for k in bars.index] + [f"{cap + 1}+"]
    vals = list(bars.values * 100) + [share[share.index > cap].sum() * 100]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.bar(labels, vals, color=BLUE, width=0.7)
    style(ax, f"IEX {a.symbol} own spread, share of trading time", "IEX best ask - best bid (cents)", "% of time")
    ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout(); fig.savefig(res / "spread_time_share.png"); plt.close(fig)

    # Summary
    def fmt(d: dict) -> str:
        return ", ".join(f"{k}={v:,.1f}" if isinstance(v, float) else f"{k}={v:,}" for k, v in d.items())

    bid_life = st.price_lifetimes_us(rh, "bid")
    ask_life = st.price_lifetimes_us(rh, "ask")
    under_bump = {s: float((d["lifetime_us"] < SPEED_BUMP_US).mean()) for s, d in (("bid", bid_life), ("ask", ask_life))}
    md = [
        f"# IEX {a.symbol} BBO prototype, {trade_date}",
        "",
        "Source: course IEX DEEP parser tick file (price levels, not DEEP+). Regular hours 09:30-16:00 New York.",
        "Timestamps: IEX-TP packet send time (not the message event time). Generated by `scripts/iex_bbo_prototype.py`.",
        "",
        "## Headline numbers",
        f"- BBO updates: {summary['bbo_updates']:,} ({summary['updates_per_minute']:,.0f} per minute)",
        f"- Best bid price changes: {summary['bid_price_changes']:,}; best ask price changes: {summary['ask_price_changes']:,}; size-only updates: {summary['size_only_updates']:,}",
        f"- Trades: {summary.get('trades', 0):,} ({summary.get('traded_shares', 0):,} shares)",
        f"- Time between BBO updates (µs): {fmt(summary['update_interval_us'])}",
        f"- Best bid price lifetime (µs): {fmt(summary['bid_price_lifetime_us'])}",
        f"- Best ask price lifetime (µs): {fmt(summary['ask_price_lifetime_us'])}",
        f"- Best prices that lasted < 350µs: bid {under_bump['bid']:.1%}, ask {under_bump['ask']:.1%}",
        f"- Spread, share of time by cents: {json.dumps({k: round(v, 4) for k, v in summary['spread_ticks_time_share'].items()})}",
        "",
        "## Data checks",
        f"- Validation (full day): {report}",
    ]
    if check:
        md.append(f"- Our BBO vs. the course parser's level-1 snapshots: {check['matching']:,} of {check['course_snapshots']:,} match ({check['match_rate']:.2%})")
    md += ["", "## Figures", "", "![](updates_per_minute.png)", "![](update_interval_cdf.png)",
           "![](best_price_lifetime_cdf.png)", "![](spread_time_share.png)", ""]
    (res / "summary.md").write_text("\n".join(md))
    (res / "summary.json").write_text(json.dumps({"summary": summary, "under_350us": under_bump, "cross_check": check}, indent=2))
    print(f"Wrote {res}")
    print("\n".join(md[5:15]))


if __name__ == "__main__":
    main()
