"""Tests for the Strategy Studio export reader and evaluation (synthetic exports in the real format)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.research.ss_results import entry_to_fill_ms, find_runs, latency_sweep, our_fees, summarize_run

FILL_HDR = "StrategyName,TradeTime,Symbol,Quantity,Price,ExecutionCost,LiquidityAction,LiquidityCode,RawLiquidity,Account,Trader,MarketCenter,OrderID,ExecID,TransactionType"
ORDER_HDR = "StrategyName,EntryTime,LastModTime,State,LastUpdateType,Symbol,Side,Type,TIF,Price,Quantity,DisplayQuantity,FilledQty,Remains,AvgFillPrice,ExecutionCost,Account,Trader,Broker,MarketCenter,OrderId,Tag,Reason,Closure"


def write_run(d: Path, name="Snipe", created="2026-11-27_120000", day="03-03-2025"):
    stem = f"BACK_{name}_{created}_start_{day}_end_{day}"
    (d / f"{stem}_fill.csv").write_text("\n".join([
        FILL_HDR,
        f"{name},2025-Mar-03 14:30:00.000400,SPY,100,580.000000,0.120000,REMOVED,0,,SIM,me,IEX,1,,FILL",
        f"{name},2025-Mar-03 14:30:01.000400,SPY,-100,580.050000,1.419224,REMOVED,0,,SIM,me,NASDAQ,2,,FILL",
    ]) + "\n")
    (d / f"{stem}_order.csv").write_text("\n".join([
        ORDER_HDR,
        f"{name},2025-Mar-03 14:30:00.000000,2025-Mar-03 14:30:00.000400,FILLED,FILL,SPY,BUY,LIMIT,IOC,580.00,100,0,100,0,580.00,0.12,SIM,me,FILL_SIMULATOR,IEX,1,,,",
        f"{name},2025-Mar-03 14:30:01.000000,2025-Mar-03 14:30:01.000400,FILLED,FILL,SPY,SELL,LIMIT,IOC,580.05,-100,0,-100,0,580.05,1.42,SIM,me,FILL_SIMULATOR,NASDAQ,2,,,",
        f"{name},2025-Mar-03 14:30:02.000000,2025-Mar-03 14:30:02.000400,CANCELLED,CANCEL,SPY,BUY,LIMIT,IOC,579.90,100,0,0,0,0,0,SIM,me,FILL_SIMULATOR,IEX,3,,,",
    ]) + "\n")
    (d / f"{stem}_pnl.csv").write_text("Name,Time,Cumulative PnL\n"
                                        f"{name},2025-Mar-03 14:30:00.500000,-1.0\n"
                                        f"{name},2025-Mar-03 14:30:01.500000,3.46\n"
                                        f"{name},2025-Mar-04 04:00:00,3.46\n")   # end-of-day row, no fraction


def test_find_and_summarize(tmp_path):
    write_run(tmp_path)
    (tmp_path / "BACK_orphan_2026-11-27_120000_start_03-03-2025_end_03-03-2025_fill.csv").write_text(FILL_HDR + "\n")
    runs = find_runs(tmp_path)
    assert len(runs) == 1 and runs[0].name == "Snipe"
    s = summarize_run(runs[0])
    assert s["orders"] == 3 and s["orders_filled"] == 2
    assert s["fill_rate"] == pytest.approx(2 / 3)
    assert s["final_position"] == 0
    assert s["gross_pnl"] == pytest.approx(5.0)              # 100 * 0.05
    sec = 100 * 580.05 * 27.80e-6
    assert s["fees_base"] == pytest.approx(0.30 + 0.30 + sec)
    assert s["net_pnl"] == pytest.approx(5.0 - 0.60 - sec)
    assert s["entry_to_fill_ms_median"] == pytest.approx(0.4)
    assert s["ss_max_drawdown"] == pytest.approx(0.0)


def test_fee_scenarios(tmp_path):
    write_run(tmp_path)
    run = find_runs(tmp_path)[0]
    assert our_fees(run.fills, "zero").sum() == pytest.approx(100 * 580.05 * 27.80e-6)
    assert our_fees(run.fills, "iex_tier2").iloc[0] == pytest.approx(0.22)


def test_entry_to_fill_ignores_unfilled(tmp_path):
    write_run(tmp_path)
    assert len(entry_to_fill_ms(find_runs(tmp_path)[0].orders)) == 2


def test_latency_sweep_cliff():
    rows = {0: {"net_pnl": 100.0}, 50: {"net_pnl": 90.0}, 100: {"net_pnl": 70.0},
            200: {"net_pnl": 40.0}, 350: {"net_pnl": -5.0}}
    table, cliff = latency_sweep(rows)
    assert list(table["latency_us"]) == [0, 50, 100, 200, 350]
    assert cliff == 200
    _, none = latency_sweep({0: {"net_pnl": 10.0}, 100: {"net_pnl": 9.0}})
    assert none is None
