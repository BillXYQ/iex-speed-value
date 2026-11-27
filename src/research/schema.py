"""Column specs and validation for the shared data format (docs/data_format.md)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

PRICE_SCALE = 10_000  # prices are stored as int64 price * 10,000

VENUES = {"iex", "nasdaq"}

# column -> (pandas dtype, nullable)
BBO_COLUMNS: dict[str, tuple[str, bool]] = {
    "ts_exch_ns": ("int64", False),
    "ts_recv_ns": ("Int64", True),
    "seq": ("int64", False),
    "venue": ("object", False),
    "symbol": ("object", False),
    "bid_px": ("Int64", True),
    "bid_sz": ("Int64", True),
    "ask_px": ("Int64", True),
    "ask_sz": ("Int64", True),
}


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


def empty_bbo() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, (t, _) in BBO_COLUMNS.items()})


def validate_bbo(df: pd.DataFrame) -> ValidationReport:
    """Check a bbo table against docs/data_format.md section 4/5."""
    r = ValidationReport()
    missing = [c for c in BBO_COLUMNS if c not in df.columns]
    if missing:
        r.errors.append(f"missing columns: {missing}")
        return r

    for col, (dtype, nullable) in BBO_COLUMNS.items():
        s = df[col]
        if dtype in ("int64", "Int64") and not pd.api.types.is_integer_dtype(s):
            r.errors.append(f"{col}: expected integer dtype, got {s.dtype}")
        if not nullable and s.isna().any():
            r.errors.append(f"{col}: {int(s.isna().sum())} null value(s) in a non-nullable column")

    if len(df) > 1 and not (df["seq"].diff().iloc[1:] > 0).all():
        r.errors.append("seq is not strictly increasing")

    bad_venue = set(df["venue"].dropna().unique()) - VENUES
    if bad_venue:
        r.errors.append(f"unknown venue(s): {sorted(bad_venue)}")

    for col in ("bid_px", "ask_px"):
        if (df[col].dropna() <= 0).any():
            r.errors.append(f"{col}: non-positive price(s)")
    for col in ("bid_sz", "ask_sz"):
        if (df[col].dropna() < 0).any():
            r.errors.append(f"{col}: negative size(s)")

    if len(df) > 1 and (df["ts_exch_ns"].diff().iloc[1:] < 0).any():
        n = int((df["ts_exch_ns"].diff().iloc[1:] < 0).sum())
        r.warnings.append(f"ts_exch_ns decreases {n} time(s)")

    both = df["bid_px"].notna() & df["ask_px"].notna()
    crossed = int((df.loc[both, "bid_px"] > df.loc[both, "ask_px"]).sum())
    if crossed:
        r.warnings.append(f"{crossed} crossed row(s) (bid_px > ask_px)")
    return r
