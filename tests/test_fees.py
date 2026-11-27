import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.research.fees import fill_cost, sec_fee_rate, take_fee_per_share


def test_take_fees():
    assert take_fee_per_share("iex") == 0.0030
    assert take_fee_per_share("NASDAQ") == 0.0030
    assert take_fee_per_share("iex", "iex_tier2") == 0.0022
    assert take_fee_per_share("nasdaq", "zero") == 0.0
    with pytest.raises(KeyError):
        take_fee_per_share("nyse")


def test_sec_fee_by_date():
    assert sec_fee_rate(dt.date(2025, 3, 3)) == pytest.approx(27.80e-6)
    assert sec_fee_rate(dt.date(2025, 5, 14)) == 0.0


def test_fill_cost():
    d = dt.date(2025, 3, 3)
    buy = fill_cost("iex", "B", 100, 580.0, d)
    sell = fill_cost("iex", "S", 100, 580.0, d)
    assert buy == pytest.approx(0.30)
    assert sell == pytest.approx(0.30 + 100 * 580.0 * 27.80e-6)
