#!/usr/bin/env python3
"""Evaluate Strategy Studio backtest exports, optionally as a latency sweep.

  # one or more runs in a folder of exported CSVs
  python3 scripts/evaluate_backtest.py --results-dir ~/ss/bt/backtesting-results/csv_files

  # latency sweep: a CSV mapping each run name to the latency it was run with
  #   run,latency_us
  #   Snipe_L0,0
  #   Snipe_L350,350
  python3 scripts/evaluate_backtest.py --results-dir <dir> --latency-map sweep.csv --out results/sweep_20250303

Fees come from config/fees.yaml (--scenario base | iex_tier2 | zero). Writes summary.csv and,
with --latency-map, pnl_vs_latency.png plus the detected cliff.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.research.ss_results import find_runs, latency_sweep, summarize_run  # noqa: E402

BLUE, TEXT, TEXT2, GRID = "#257de0", "#191919", "#666666", "#e5e5e5"


def plot_sweep(table: pd.DataFrame, cliff: float | None, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=150)
    ax.plot(table["latency_us"], table["net_pnl"], color=BLUE, linewidth=2, marker="o", markersize=5)
    ax.axhline(0, color=TEXT2, linewidth=1)
    if cliff is not None:
        ax.axvline(cliff, color=TEXT2, linewidth=1, linestyle="--")
        ax.text(cliff, ax.get_ylim()[1], f" cliff ≈ {cliff:g}µs", color=TEXT2, fontsize=9, va="top")
    ax.set_title(title, loc="left", color=TEXT, fontsize=12, pad=10)
    ax.set_xlabel("simulated latency (µs)", color=TEXT2)
    ax.set_ylabel("net PnL after fees ($)", color=TEXT2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--results-dir", type=Path, required=True, help="folder with exported BACK_*_{fill,order,pnl}.csv")
    p.add_argument("--scenario", default="base", help="fee scenario in config/fees.yaml")
    p.add_argument("--latency-map", type=Path, help="CSV with columns run,latency_us")
    p.add_argument("--out", type=Path, help="output folder (default results/backtest_eval)")
    a = p.parse_args(argv)

    runs = find_runs(a.results_dir.expanduser())
    if not runs:
        sys.exit(f"no complete runs (fill + order + pnl) found in {a.results_dir}")
    out = a.out or (config.results_dir() / "backtest_eval")
    out.mkdir(parents=True, exist_ok=True)

    summaries = {r.name: summarize_run(r, a.scenario) for r in runs}
    table = pd.DataFrame(summaries.values())
    table.to_csv(out / "summary.csv", index=False)
    cols = ["run", "start", "orders", "fill_rate", "shares", "gross_pnl", f"fees_{a.scenario}", "net_pnl",
            "net_pnl_per_share", "ss_reported_pnl", "entry_to_fill_ms_median"]
    print(table[cols].to_string(index=False, float_format=lambda x: f"{x:,.4f}"))

    if a.latency_map:
        m = pd.read_csv(a.latency_map)
        missing = set(m["run"]) - summaries.keys()
        if missing:
            sys.exit(f"runs in --latency-map not found in results: {sorted(missing)}")
        sweep, cliff = latency_sweep({float(r.latency_us): summaries[r.run] for r in m.itertuples()})
        sweep.to_csv(out / "latency_sweep.csv", index=False)
        plot_sweep(sweep, cliff, out / "pnl_vs_latency.png", f"Net PnL vs. simulated latency ({a.scenario} fees)")
        print(f"\ncliff: {cliff if cliff is not None else 'not reached'} µs  -> {out / 'pnl_vs_latency.png'}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
