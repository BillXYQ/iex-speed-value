"""Loading and validating tables in Aditi's parser output format (synthetic data)."""

import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.research.schema import load_table, validate_bbo, validate_orders

T = 1_659_360_600_000_000_000  # 2022-08-01 13:30 UTC in ns
UNSIGNED = {"order_id", "seq", "size", "new_size", "bid_sz", "ask_sz",
            "executed_size", "channel", "session", "flags"}
TEXT = {"venue", "symbol", "event", "side", "message_type"}


def write_like_aditi(path: Path, rows: dict) -> Path:
    """Write Parquet with the same Arrow types as her scripts/to_parquet.py."""
    def typ(c):
        return pa.string() if c in TEXT else pa.uint64() if c in UNSIGNED else pa.int64()
    table = pa.table({c: pa.array(v, type=typ(c)) for c, v in rows.items()})
    pq.write_table(table, path)
    return path


def orders_rows():
    n = 4
    return {
        "ts_exch_ns": [T, T + 10, T + 20, T + 30],
        "ts_capture_ns": [T + 5, T + 15, T + 25, T + 35],
        "venue": ["IEX"] * n, "symbol": ["SPY"] * n,
        "event": ["add", "modify", "execute", "clear"],
        "order_id": [2**63 + 7, 2**63 + 7, 2**63 + 7, None],  # needs uint64
        "side": ["B", "B", "B", None],
        "price": [4_100_000, 4_100_000, 4_100_100, None],
        "size": [300, 300, 200, None],
        "new_price": [4_100_000, 4_100_100, 4_100_100, None],
        "new_size": [300, 200, 100, 0],
        "flags": [0, 1, 0, 0],
        "seq": [1, 2, 3, 4],
        "message_type": ["a", "M", "L", "C"],
        "executed_size": [0, 0, 100, 0],  # 0, not null, off executions
        "execution_price": [None, None, 4_100_100, None],
        "ts_send_ns": [T + 1, T + 11, T + 21, T + 31],
        "channel": [1] * n, "session": [7] * n,
    }


def test_load_and_validate_orders(tmp_path):
    df = load_table(write_like_aditi(tmp_path / "SPY_orders.parquet", orders_rows()), "orders")
    assert str(df["seq"].dtype) == "int64" and str(df["order_id"].dtype) == "UInt64"
    assert int(df["order_id"].iloc[0]) == 2**63 + 7      # no float round-trip
    assert int(df["ts_capture_ns"].iloc[0]) == T + 5
    rep = validate_orders(df)
    assert rep.ok and not rep.warnings, rep

    early = df.copy()
    early["ts_capture_ns"] = early["ts_exch_ns"] - 100   # as in her synthetic demo
    assert any("ts_capture_ns earlier" in w for w in validate_orders(early).warnings)

    bad = df.copy()
    bad.loc[1, "event"] = "MODIFY"        # events are lowercase
    bad.loc[2, "execution_price"] = None  # execute must carry its trade price
    rep = validate_orders(bad)
    assert any("unknown event" in e for e in rep.errors)
    assert any("execute without" in e for e in rep.errors)


def test_load_and_validate_bbo(tmp_path):
    rows = {
        "ts_exch_ns": [T, T + 10], "ts_capture_ns": [T + 5, T + 15],
        "venue": ["IEX", "IEX"], "symbol": ["SPY", "SPY"],
        "bid_px": [4_100_000, 4_100_000], "bid_sz": [300, 300],
        "ask_px": [None, 4_100_200], "ask_sz": [0, 100],
        "seq": [1, 2],
    }
    df = load_table(write_like_aditi(tmp_path / "SPY_bbo.parquet", rows), "bbo")
    assert validate_bbo(df).ok

    bad = df.copy()
    bad.loc[0, "ask_sz"] = 50   # empty side must have size 0
    bad["venue"] = "iex"        # venue is uppercase
    rep = validate_bbo(bad)
    assert any("empty side" in e for e in rep.errors)
    assert any("unknown venue" in e for e in rep.errors)
