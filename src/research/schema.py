"""Column specs, loading and validation for the shared data format.

The format is defined by Aditi's parser repo (`docs/data_format.md` there) and
mirrored in this repo's `docs/data_format.md`. Her Parquet files store sequence
numbers and sizes as uint64; `load_table` casts those to int64 (safe for real
values) so arithmetic and diffs behave. `order_id` stays uint64.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PRICE_SCALE = 10_000  # prices are stored as int64 price * 10,000

VENUES = {"IEX", "NASDAQ"}
SIDES = {"B", "S"}
EVENTS = {"add", "modify", "delete", "execute", "clear"}

# column -> (pandas dtype after load_table, nullable)
BBO_COLUMNS: dict[str, tuple[str, bool]] = {
    "ts_exch_ns": ("int64", False),
    "ts_capture_ns": ("Int64", True),
    "venue": ("object", False),
    "symbol": ("object", False),
    "bid_px": ("Int64", True),   # null when the side is empty
    "bid_sz": ("int64", False),  # 0 when the side is empty
    "ask_px": ("Int64", True),
    "ask_sz": ("int64", False),
    "seq": ("int64", False),
}

ORDER_COLUMNS: dict[str, tuple[str, bool]] = {
    "ts_exch_ns": ("int64", False),
    "ts_capture_ns": ("Int64", True),
    "venue": ("object", False),
    "symbol": ("object", False),
    "event": ("object", False),
    "order_id": ("UInt64", True),        # null on clear
    "side": ("object", True),            # null on clear
    "price": ("Int64", True),            # before the update (new values on add)
    "size": ("Int64", True),
    "new_price": ("Int64", True),        # after the update; null when terminal
    "new_size": ("Int64", True),         # after the update; 0 when terminal
    "flags": ("Int64", True),
    "seq": ("int64", False),
    "message_type": ("object", False),
    "executed_size": ("Int64", True),    # execute only
    "execution_price": ("Int64", True),  # execute only
    "ts_send_ns": ("Int64", True),
    "channel": ("Int64", True),
    "session": ("Int64", True),
}

TABLES = {"bbo": BBO_COLUMNS, "orders": ORDER_COLUMNS}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"errors: {len(self.errors)}, warnings: {len(self.warnings)}"]
        lines += [f"  ERROR   {e}" for e in self.errors]
        lines += [f"  WARNING {w}" for w in self.warnings]
        return "\n".join(lines)


def empty_table(table: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, (t, _) in TABLES[table].items()})


def empty_bbo() -> pd.DataFrame:
    return empty_table("bbo")


def load_table(path: str | Path, table: str) -> pd.DataFrame:
    """Read one of Aditi's Parquet tables and cast columns to the dtypes above."""
    spec = TABLES[table]
    # numpy_nullable keeps integer columns with nulls as Int64/UInt64; the default
    # reader turns them into float64, which corrupts ns timestamps and order IDs.
    df = pd.read_parquet(path, dtype_backend="numpy_nullable")
    missing = [c for c in spec if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    df = df.astype({c: t for c, (t, _) in spec.items()})[list(spec)]
    for c in df.columns[df.dtypes == "string"]:
        df[c] = df[c].astype("object")
    return df


def _check_columns(df: pd.DataFrame, spec: dict, r: ValidationReport) -> bool:
    missing = [c for c in spec if c not in df.columns]
    if missing:
        r.errors.append(f"missing columns: {missing}")
        return False
    for col, (dtype, nullable) in spec.items():
        s = df[col]
        if dtype.lower().startswith(("int", "uint")) and not pd.api.types.is_integer_dtype(s):
            r.errors.append(f"{col}: expected integer dtype, got {s.dtype}")
        if not nullable and s.isna().any():
            r.errors.append(f"{col}: {int(s.isna().sum())} null value(s) in a non-nullable column")
    bad_venue = set(df["venue"].dropna().unique()) - VENUES
    if bad_venue:
        r.errors.append(f"unknown venue(s): {sorted(bad_venue)}")
    return True


def _check_order(df: pd.DataFrame, r: ValidationReport, strict_seq: bool) -> None:
    if len(df) < 2:
        return
    d = df["seq"].astype("float64").diff().iloc[1:]
    if strict_seq and not (d > 0).all():
        r.errors.append("seq is not strictly increasing")
    elif not strict_seq and (d < 0).any():
        r.errors.append("seq decreases")
    n = int((df["ts_exch_ns"].astype("float64").diff().iloc[1:] < 0).sum())
    if n:
        r.warnings.append(f"ts_exch_ns decreases {n} time(s)")
    for col in ("ts_capture_ns", "ts_send_ns"):
        if col in df.columns:
            early = int((df[col].astype("Int64") < df["ts_exch_ns"].astype("Int64")).fillna(False).sum())
            if early:
                r.warnings.append(f"{col} earlier than ts_exch_ns on {early} row(s)")


def validate_bbo(df: pd.DataFrame) -> ValidationReport:
    """Check a bbo table against docs/data_format.md."""
    r = ValidationReport()
    if not _check_columns(df, BBO_COLUMNS, r):
        return r
    _check_order(df, r, strict_seq=True)

    for side in ("bid", "ask"):
        px, sz = df[f"{side}_px"], df[f"{side}_sz"]
        if (px.dropna() <= 0).any():
            r.errors.append(f"{side}_px: non-positive price(s)")
        if (sz.dropna() < 0).any():
            r.errors.append(f"{side}_sz: negative size(s)")
        if (px.isna() & (sz.fillna(0) != 0)).any():
            r.errors.append(f"{side}: empty side (null price) with non-zero size")

    both = df["bid_px"].notna() & df["ask_px"].notna()
    crossed = int((df.loc[both, "bid_px"] > df.loc[both, "ask_px"]).sum())
    if crossed:
        r.warnings.append(f"{crossed} crossed row(s) (bid_px > ask_px)")
    return r


def validate_orders(df: pd.DataFrame) -> ValidationReport:
    """Check an orders table against docs/data_format.md.

    One wire message can produce several rows (e.g. clear), so seq only has to
    be non-decreasing here.
    """
    r = ValidationReport()
    if not _check_columns(df, ORDER_COLUMNS, r):
        return r
    _check_order(df, r, strict_seq=False)

    bad = set(df["event"].dropna().unique()) - EVENTS
    if bad:
        r.errors.append(f"unknown event(s): {sorted(bad)}")
    not_clear = df["event"] != "clear"
    if df.loc[not_clear, "order_id"].isna().any():
        r.errors.append("order_id is null on a non-clear event")
    bad_side = set(df.loc[not_clear, "side"].dropna().unique()) - SIDES
    if bad_side or df.loc[not_clear, "side"].isna().any():
        r.errors.append(f"side must be B/S on non-clear events (found {sorted(bad_side)})")
    for col in ("price", "new_price", "execution_price"):
        if (df[col].dropna() <= 0).any():
            r.errors.append(f"{col}: non-positive price(s)")
    for col in ("size", "new_size", "executed_size"):
        if (df[col].dropna() < 0).any():
            r.errors.append(f"{col}: negative size(s)")
    ex = df["event"] == "execute"
    if df.loc[ex, ["executed_size", "execution_price"]].isna().any().any():
        r.errors.append("execute without executed_size/execution_price")
    return r
