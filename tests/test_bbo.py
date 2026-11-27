"""Tests for the tick-file adapter, BBO builder, validator and stats (synthetic data)."""

import gzip
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.research.bbo_stats import classify_changes, price_lifetimes_us, spread_ticks, time_weighted_share
from src.research.course_parser_io import build_bbo, read_tick_file
from src.research.schema import validate_bbo

T0 = "2022-08-01 13:30:00."


def ts(us: int) -> str:
    return f"{T0}{us * 1000:09d}"


def write_ticks(path: Path, rows: list[str]) -> Path:
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(rows) + "\n")
    return path


def P(us, seq, side, price, size, partial=0):
    return f"{ts(us + 20)},{ts(us)},{seq},P,IEX,{side},{price:.6f},{size},,,,{partial}"


def T(us, seq, price, size):
    return f"{ts(us + 20)},{ts(us)},{seq},T,IEX,{price:.6f},{size}"


def sample(tmp_path):
    rows = [
        P(0, 1, 1, 100.00, 200),           # bid 100.00x200
        P(10, 2, 2, 100.02, 300),          # ask 100.02x300
        P(20, 3, 1, 100.01, 100, partial=1),  # partial: no row yet
        P(20, 4, 2, 100.03, 50),           # event completes: bid 100.01, ask 100.02
        T(25, 5, 100.02, 100),
        P(30, 6, 2, 100.02, 200),          # ask size only change
        P(40, 7, 2, 100.02, 0),            # ask level removed -> ask 100.03
        P(50, 8, 2, 99.99, 0),             # removal of unknown level: ignored, no change
        P(60, 9, 1, 100.01, 0),            # bid back to 100.00
    ]
    return write_ticks(tmp_path / "tick_SPY_20220801.txt.gz", rows)


def test_read_tick_file(tmp_path):
    levels, trades = read_tick_file(sample(tmp_path))
    assert len(levels) == 8 and len(trades) == 1
    assert levels["px"].iloc[0] == 1_000_000  # 100.00 * 10,000
    assert levels["is_partial"].sum() == 1
    assert (levels["ts_recv_ns"] - levels["ts_exch_ns"] == 20_000).all()
    assert trades["px"].iloc[0] == 1_000_200


def test_build_bbo(tmp_path):
    levels, _ = read_tick_file(sample(tmp_path))
    bbo = build_bbo(levels)
    got = bbo[["seq", "bid_px", "bid_sz", "ask_px", "ask_sz"]].astype("float64").fillna(-1).values.tolist()
    expected = [
        [1, 1_000_000, 200, -1, -1],
        [2, 1_000_000, 200, 1_000_200, 300],
        [4, 1_000_100, 100, 1_000_200, 300],  # partial seq 3 folded into event ending at seq 4
        [6, 1_000_100, 100, 1_000_200, 200],
        [7, 1_000_100, 100, 1_000_300, 50],
        [9, 1_000_000, 200, 1_000_300, 50],   # seq 8 (unknown removal) emitted nothing
    ]
    assert got == expected
    assert validate_bbo(bbo).ok


def test_validator_flags_problems(tmp_path):
    levels, _ = read_tick_file(sample(tmp_path))
    bad = build_bbo(levels)
    bad.loc[2, "seq"] = 1                      # seq not increasing
    bad.loc[3, "bid_px"] = 2_000_000           # crossed
    rep = validate_bbo(bad)
    assert not rep.ok
    assert any("seq" in e for e in rep.errors)
    assert any("crossed" in w for w in rep.warnings)
    assert not validate_bbo(bad.drop(columns=["venue"])).ok


def test_stats(tmp_path):
    levels, _ = read_tick_file(sample(tmp_path))
    bbo = build_bbo(levels)
    c = classify_changes(bbo)
    assert c["size_only"].tolist() == [False, False, False, True, False, False]

    bid_life = price_lifetimes_us(bbo, "bid")
    # bid 100.00 from t=0 to t=20 (improved), bid 100.01 from t=20 to t=60 (worsened)
    assert bid_life[["px", "lifetime_us", "ended"]].values.tolist() == [
        [1_000_000, 20.0, "improved"], [1_000_100, 40.0, "worsened"]]

    sp = spread_ticks(bbo)
    assert sp.tolist() == [2.0, 1.0, 1.0, 2.0, 3.0]
    share = time_weighted_share(sp, bbo)
    assert np.isclose(share.sum(), 1.0)
