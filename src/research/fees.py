"""Exchange and regulatory fees for evaluating backtests (see config/fees.yaml, docs/fees.md)."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import yaml

FEES_FILE = Path(__file__).resolve().parents[2] / "config" / "fees.yaml"


@lru_cache(maxsize=4)
def load_fees(path: str | Path = FEES_FILE) -> dict:
    return yaml.safe_load(Path(path).read_text())


def take_fee_per_share(venue: str, scenario: str = "base", fees: dict | None = None) -> float:
    """$ per share for removing displayed liquidity on `venue` under a fee scenario."""
    fees = fees or load_fees()
    try:
        return float(fees["scenarios"][scenario][venue.lower()])
    except KeyError as e:
        raise KeyError(f"unknown scenario/venue: {scenario}/{venue}") from e


def sec_fee_rate(trade_date: dt.date, fees: dict | None = None) -> float:
    """Section 31 rate (fraction of notional, sells only) in effect on trade_date."""
    fees = fees or load_fees()
    for row in fees["sec_section31"]:
        start = dt.date.fromisoformat(row["from"])
        end = dt.date.fromisoformat(row["to"]) if row["to"] else dt.date.max
        if start <= trade_date <= end:
            return float(row["rate"])
    raise ValueError(f"no Section 31 rate configured for {trade_date}")


def fill_cost(venue: str, side: str, shares: int, price: float, trade_date: dt.date,
              scenario: str = "base", fees: dict | None = None) -> float:
    """Total $ fees for one taking fill: venue take fee plus Section 31 fee on sells."""
    cost = take_fee_per_share(venue, scenario, fees) * shares
    if side.upper() in ("S", "SELL"):
        cost += sec_fee_rate(trade_date, fees) * shares * price
    return cost
