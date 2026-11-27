"""Descriptive statistics on a single venue's `bbo` table.

Everything here works on the shared bbo format, so the same functions apply to
IEX DEEP (today), IEX DEEP+ and NASDAQ (later).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .schema import PRICE_SCALE

NY = ZoneInfo("America/New_York")
TICK = PRICE_SCALE // 100  # one cent in integer price units


def regular_hours(df: pd.DataFrame, trade_date: dt.date, ts_col: str = "ts_exch_ns") -> pd.DataFrame:
    """Keep rows between 09:30 and 16:00 New York time on trade_date."""
    start = dt.datetime.combine(trade_date, dt.time(9, 30), NY)
    end = dt.datetime.combine(trade_date, dt.time(16, 0), NY)
    lo, hi = int(start.timestamp() * 1e9), int(end.timestamp() * 1e9)
    return df[(df[ts_col] >= lo) & (df[ts_col] < hi)].reset_index(drop=True)


def classify_changes(bbo: pd.DataFrame) -> pd.DataFrame:
    """Label each row by what changed versus the previous row."""
    d = bbo.copy()

    def changed(col: str) -> pd.Series:
        cur = d[col].astype("float64")
        prev = cur.shift(1)
        same = (cur == prev) | (cur.isna() & prev.isna())
        return ~same

    d["bid_px_chg"] = changed("bid_px")
    d["ask_px_chg"] = changed("ask_px")
    d["size_only"] = ~d["bid_px_chg"] & ~d["ask_px_chg"]
    d.loc[d.index[0], ["bid_px_chg", "ask_px_chg", "size_only"]] = [False, False, False]
    return d


def update_intervals_us(bbo: pd.DataFrame) -> np.ndarray:
    """Time between consecutive BBO updates, in microseconds."""
    return np.diff(bbo["ts_exch_ns"].to_numpy()) / 1e3


def price_lifetimes_us(bbo: pd.DataFrame, side: str) -> pd.DataFrame:
    """How long each best price stayed at the top of book on one side.

    side: 'bid' or 'ask'. Returns one row per run of an unchanged best price:
    px, start_ns, end_ns, lifetime_us, and how it ended ('improved'/'worsened'
    relative to the trader on that side, or 'emptied'). The last run (cut off by
    the end of the window) is dropped.
    """
    px = bbo[f"{side}_px"].to_numpy(dtype="float64", na_value=np.nan)
    ts = bbo["ts_exch_ns"].to_numpy()
    change = np.r_[True, ~((px[1:] == px[:-1]) | (np.isnan(px[1:]) & np.isnan(px[:-1])))]
    starts = np.flatnonzero(change)
    rows = []
    for i, j in zip(starts[:-1], starts[1:]):
        if np.isnan(px[i]):
            continue
        nxt = px[j]
        if np.isnan(nxt):
            how = "emptied"
        elif (side == "bid" and nxt > px[i]) or (side == "ask" and nxt < px[i]):
            how = "improved"
        else:
            how = "worsened"
        rows.append((int(px[i]), ts[i], ts[j], (ts[j] - ts[i]) / 1e3, how))
    return pd.DataFrame(rows, columns=["px", "start_ns", "end_ns", "lifetime_us", "ended"])


def spread_ticks(bbo: pd.DataFrame) -> pd.Series:
    both = bbo["bid_px"].notna() & bbo["ask_px"].notna()
    return ((bbo.loc[both, "ask_px"] - bbo.loc[both, "bid_px"]) / TICK).astype("float64")


def time_weighted_share(values: pd.Series, bbo: pd.DataFrame) -> pd.Series:
    """Share of time spent at each value (e.g. spread in ticks) until the next update."""
    ts = bbo.loc[values.index, "ts_exch_ns"].to_numpy()
    dur = np.r_[np.diff(ts), 0]
    w = pd.Series(dur, index=values.index)
    return (w.groupby(values).sum() / w.sum()).sort_index()


def quantiles(x: np.ndarray | pd.Series, qs=(0.1, 0.25, 0.5, 0.75, 0.9, 0.99)) -> dict[str, float]:
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return {}
    return {f"p{int(q * 100)}": float(np.quantile(x, q)) for q in qs} | {"mean": float(x.mean()), "n": int(x.size)}


def summarize(bbo: pd.DataFrame, trades: pd.DataFrame | None = None) -> dict:
    """One dictionary with the headline numbers for a venue-day."""
    c = classify_changes(bbo)
    minutes = (bbo["ts_exch_ns"].iloc[-1] - bbo["ts_exch_ns"].iloc[0]) / 60e9
    out = {
        "bbo_updates": int(len(bbo)),
        "bid_price_changes": int(c["bid_px_chg"].sum()),
        "ask_price_changes": int(c["ask_px_chg"].sum()),
        "size_only_updates": int(c["size_only"].sum()),
        "updates_per_minute": float(len(bbo) / minutes) if minutes > 0 else float("nan"),
        "update_interval_us": quantiles(update_intervals_us(bbo)),
        "bid_price_lifetime_us": quantiles(price_lifetimes_us(bbo, "bid")["lifetime_us"]),
        "ask_price_lifetime_us": quantiles(price_lifetimes_us(bbo, "ask")["lifetime_us"]),
        "spread_ticks_time_share": {str(k): float(v) for k, v in
                                    time_weighted_share(spread_ticks(bbo), bbo).head(5).items()},
    }
    if trades is not None and len(trades):
        out["trades"] = int(len(trades))
        out["traded_shares"] = int(trades["size"].sum())
    return out
