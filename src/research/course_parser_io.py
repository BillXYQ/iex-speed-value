"""Read the course IEX DEEP parser's Strategy Studio tick file and build a `bbo` table.

The course parser (`iexdownloaderparser`, by Prof. Lariviere) writes one tick file
per symbol and day, e.g. `tick_SPY_20220801.txt.gz`, with two row types:

  P (price level update):
    collection_time, source_time, seq, P, IEX, side(1=bid, 2=ask), price, size, , , , is_partial
  T (trade):
    collection_time, source_time, seq, T, IEX, price, size

Timestamps are UTC strings with nanoseconds. Notes from reading the parser:
  * collection_time = pcap capture time  -> our `ts_recv_ns`.
  * source_time     = IEX-TP packet *send time*, not the message's own event
    timestamp (the parser does not write that one to the tick file). We use it as
    `ts_exch_ns` here and flag the difference in docs/data_format.md.
  * is_partial = 1 means more updates for the same IEX event follow; 0 means the
    event is complete. A BBO is only emitted after complete events.
  * size = 0 removes a price level. (The course StockBook inserts a zero-size level
    when a removal arrives for an unknown price; we ignore such removals instead.)

This is an adapter for the DEEP sample we already have; the research code itself
only depends on the `bbo` format, so swapping in Aditi's DEEP+ parser output later
changes nothing downstream.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .schema import BBO_COLUMNS, PRICE_SCALE

TICK_COLUMNS = ["collection_time", "source_time", "seq", "kind", "venue_raw",
                "f5", "f6", "f7", "f8", "f9", "f10", "f11"]


def _to_ns(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).astype("int64").to_numpy()


def read_tick_file(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (levels, trades) from a course tick file.

    levels: ts_exch_ns, ts_recv_ns, seq, side ('B'/'S'), px (int), size, is_partial (bool)
    trades: ts_exch_ns, ts_recv_ns, seq, px (int), size
    """
    raw = pd.read_csv(path, header=None, names=TICK_COLUMNS, dtype=str)

    p = raw[raw["kind"] == "P"]
    levels = pd.DataFrame({
        "ts_exch_ns": _to_ns(p["source_time"]),
        "ts_recv_ns": _to_ns(p["collection_time"]),
        "seq": p["seq"].astype("int64").to_numpy(),
        "side": np.where(p["f5"].to_numpy() == "1", "B", "S"),
        "px": np.rint(p["f6"].astype(float).to_numpy() * PRICE_SCALE).astype("int64"),
        "size": p["f7"].astype("int64").to_numpy(),
        "is_partial": p["f11"].to_numpy() == "1",
    })

    t = raw[raw["kind"] == "T"]
    trades = pd.DataFrame({
        "ts_exch_ns": _to_ns(t["source_time"]),
        "ts_recv_ns": _to_ns(t["collection_time"]),
        "seq": t["seq"].astype("int64").to_numpy(),
        "px": np.rint(t["f5"].astype(float).to_numpy() * PRICE_SCALE).astype("int64"),
        "size": t["f6"].astype("int64").to_numpy(),
    })
    return levels.reset_index(drop=True), trades.reset_index(drop=True)


def build_bbo(levels: pd.DataFrame, venue: str = "iex", symbol: str = "SPY") -> pd.DataFrame:
    """Replay price-level updates and emit one row whenever the BBO changes.

    A row is emitted only after a complete event (is_partial == False) and only
    if best bid/ask price or size differs from the previous emitted row.
    """
    bids: dict[int, int] = {}
    asks: dict[int, int] = {}
    best_bid: int | None = None
    best_ask: int | None = None
    last = (None, None, None, None)
    out = []

    cols = [levels[c].to_numpy() for c in ("ts_exch_ns", "ts_recv_ns", "seq", "side", "px", "size", "is_partial")]
    for ts_e, ts_r, seq, side, px, size, partial in zip(*cols):
        book = bids if side == "B" else asks
        if size == 0:
            if px in book:
                del book[px]
                if side == "B" and px == best_bid:
                    best_bid = max(bids) if bids else None
                elif side == "S" and px == best_ask:
                    best_ask = min(asks) if asks else None
        else:
            book[px] = size
            if side == "B" and (best_bid is None or px > best_bid):
                best_bid = px
            elif side == "S" and (best_ask is None or px < best_ask):
                best_ask = px

        if partial:
            continue
        cur = (best_bid, bids.get(best_bid) if best_bid is not None else None,
               best_ask, asks.get(best_ask) if best_ask is not None else None)
        if cur != last:
            out.append((ts_e, ts_r, seq, *cur))
            last = cur

    df = pd.DataFrame(out, columns=["ts_exch_ns", "ts_recv_ns", "seq", "bid_px", "bid_sz", "ask_px", "ask_sz"])
    df.insert(3, "venue", venue)
    df.insert(4, "symbol", symbol)
    return df.astype({c: t for c, (t, _) in BBO_COLUMNS.items()})[list(BBO_COLUMNS)]
