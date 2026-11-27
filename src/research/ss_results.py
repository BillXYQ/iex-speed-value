"""Read and evaluate Strategy Studio backtest exports.

`StrategyCommandLine cmd export_cra_file <run.cra> <dir>` writes three CSVs per run:

  BACK_<name>_<created>_start_<MM-DD-YYYY>_end_<MM-DD-YYYY>_fill.csv
      StrategyName,TradeTime,Symbol,Quantity,Price,ExecutionCost,LiquidityAction,LiquidityCode,
      RawLiquidity,Account,Trader,MarketCenter,OrderID,ExecID,TransactionType
  ..._order.csv
      StrategyName,EntryTime,LastModTime,State,LastUpdateType,Symbol,Side,Type,TIF,Price,Quantity,
      DisplayQuantity,FilledQty,Remains,AvgFillPrice,ExecutionCost,Account,Trader,Broker,MarketCenter,
      OrderId,Tag,Reason,Closure
  ..._pnl.csv
      Name,Time,Cumulative PnL

Times look like "2019-Sep-13 13:30:02.078649" (UTC). Quantity is signed (+buy, -sell).
ExecutionCost is Strategy Studio's own fee model ($0.0012/share + 2.24e-05 of notional on
sells, venue-independent); `net_pnl` replaces it with our venue fees from config/fees.yaml.

Format taken from last year's FIN 556 exports (group_04, group_06).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .fees import load_fees, sec_fee_rate, take_fee_per_share

TIME_FMT = "%Y-%b-%d %H:%M:%S.%f"
RUN_RE = re.compile(r"BACK_(?P<name>.+?)_(?P<created>\d{4}-\d{2}-\d{2}_\d{6})_start_(?P<start>\d{2}-\d{2}-\d{4})_end_(?P<end>\d{2}-\d{2}-\d{4})_(?P<kind>fill|order|pnl)\.csv$")


def _t(s: pd.Series) -> pd.Series:
    # Most rows have microseconds; the end-of-day PnL row does not ("2019-Sep-14 04:00:00").
    s = s.astype(str).where(s.astype(str).str.contains(r"\."), s.astype(str) + ".000000")
    return pd.to_datetime(s, format=TIME_FMT, utc=True)


def read_fills(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["TradeTime"] = _t(df["TradeTime"])
    return df


def read_orders(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["EntryTime"] = _t(df["EntryTime"])
    df["LastModTime"] = _t(df["LastModTime"])
    return df


def read_pnl(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Time"] = _t(df["Time"])
    return df.rename(columns={"Cumulative PnL": "cum_pnl"})


@dataclass
class Run:
    name: str
    start: dt.date
    end: dt.date
    fills: pd.DataFrame
    orders: pd.DataFrame
    pnl: pd.DataFrame


def find_runs(results_dir: str | Path) -> list[Run]:
    """Group the exported CSVs in a directory into runs."""
    groups: dict[tuple, dict[str, Path]] = {}
    for p in Path(results_dir).glob("BACK_*.csv"):
        m = RUN_RE.search(p.name)
        if m:
            key = (m["name"], m["created"], m["start"], m["end"])
            groups.setdefault(key, {})[m["kind"]] = p
    runs = []
    for (name, _created, start, end), files in sorted(groups.items()):
        if {"fill", "order", "pnl"} - files.keys():
            continue
        runs.append(Run(
            name=name,
            start=dt.datetime.strptime(start, "%m-%d-%Y").date(),
            end=dt.datetime.strptime(end, "%m-%d-%Y").date(),
            fills=read_fills(files["fill"]),
            orders=read_orders(files["order"]),
            pnl=read_pnl(files["pnl"]),
        ))
    return runs


def our_fees(fills: pd.DataFrame, scenario: str = "base", fees: dict | None = None) -> pd.Series:
    """Per-fill fees under our venue fee model (taking fills only; others get 0 + Section 31)."""
    fees = fees or load_fees()
    venue_fee = fills["MarketCenter"].str.lower().map(
        lambda v: take_fee_per_share(v, scenario, fees) if v in ("iex", "nasdaq") else np.nan)
    taking = fills["LiquidityAction"].eq("REMOVED")
    shares = fills["Quantity"].abs()
    exch = np.where(taking, venue_fee * shares, 0.0)
    sec_rate = fills["TradeTime"].dt.date.map(lambda d: sec_fee_rate(d, fees))
    sec = np.where(fills["Quantity"] < 0, sec_rate * shares * fills["Price"], 0.0)
    return pd.Series(exch + sec, index=fills.index)


def entry_to_fill_ms(orders: pd.DataFrame) -> pd.Series:
    """Delay from order entry to its final fill, in ms (filled orders only)."""
    f = orders[orders["State"] == "FILLED"]
    return (f["LastModTime"] - f["EntryTime"]).dt.total_seconds() * 1e3


def max_drawdown(cum: pd.Series) -> float:
    if cum.empty:
        return 0.0
    return float((cum - cum.cummax()).min())


def summarize_run(run: Run, scenario: str = "base", mark_price: float | None = None) -> dict:
    """Headline metrics for one run.

    gross_pnl = -sum(qty * price) + final_position * mark_price. If the strategy ends flat,
    mark_price is irrelevant; otherwise pass the closing price (defaults to the last fill price).
    """
    f, o = run.fills, run.orders
    qty, px = f["Quantity"], f["Price"]
    position = int(qty.sum())
    mark = mark_price if mark_price is not None else (float(px.iloc[-1]) if len(f) else 0.0)
    gross = float(-(qty * px).sum() + position * mark)
    fees_ss = float(f["ExecutionCost"].sum())
    fees_ours = float(our_fees(f, scenario).sum())
    shares = int(qty.abs().sum())
    n_orders = int(len(o))
    n_filled = int((o["FilledQty"].abs() > 0).sum())
    lat = entry_to_fill_ms(o)
    return {
        "run": run.name,
        "start": run.start.isoformat(),
        "end": run.end.isoformat(),
        "orders": n_orders,
        "orders_filled": n_filled,
        "fill_rate": n_filled / n_orders if n_orders else float("nan"),
        "fills": int(len(f)),
        "shares": shares,
        "final_position": position,
        "gross_pnl": gross,
        "fees_strategy_studio": fees_ss,
        f"fees_{scenario}": fees_ours,
        "net_pnl": gross - fees_ours,
        "net_pnl_per_share": (gross - fees_ours) / shares if shares else float("nan"),
        "ss_reported_pnl": float(run.pnl["cum_pnl"].iloc[-1]) if len(run.pnl) else float("nan"),
        "ss_max_drawdown": max_drawdown(run.pnl["cum_pnl"]),
        "entry_to_fill_ms_min": float(lat.min()) if len(lat) else float("nan"),
        "entry_to_fill_ms_median": float(lat.median()) if len(lat) else float("nan"),
    }


def latency_sweep(summaries: dict[float, dict], drop: float = 0.5) -> tuple[pd.DataFrame, float | None]:
    """Combine per-latency summaries into one table and find the cliff.

    summaries: {latency_us: summarize_run(...)}. The cliff is the smallest latency at which
    net PnL falls to `drop` x the zero-latency net PnL or below (or to <= 0 if that baseline
    is not positive).
    """
    df = pd.DataFrame.from_dict(summaries, orient="index").rename_axis("latency_us").sort_index().reset_index()
    if df.empty:
        return df, None
    base = df.loc[df["latency_us"].idxmin(), "net_pnl"]
    threshold = base * drop if base > 0 else 0.0
    hit = df[(df["latency_us"] > df["latency_us"].min()) & (df["net_pnl"] <= threshold)]
    return df, (float(hit["latency_us"].iloc[0]) if len(hit) else None)
