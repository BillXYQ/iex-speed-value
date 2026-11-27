#!/usr/bin/env python3
"""Inventory of NASDAQ TotalView-ITCH days on the course VM.

  python3 scripts/xnas_day_inventory.py

Reads {raw_data_dir}/xnas_pcaps/YYYYMMDD/ny4-xnas-tvitch-a-YYYYMMDDTHHMMSS.pcap.zst
using directory listings and file sizes only: pcaps are never opened or decompressed.
File times in the names are UTC.

For every folder it reports date validity, weekday, file count, total size, first and
last file time, and (for open weekdays) which 10-minute slots of US regular hours
(09:30-16:00 America/New_York, converted to UTC per day so the 2025-03-09 DST switch
is handled) have no file. Outputs (small, committed):
  {results_dir}/xnas_inventory/inventory.csv
  {results_dir}/xnas_inventory/summary.md
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
SLOT = dt.timedelta(minutes=10)
RTH_OPEN, RTH_CLOSE = dt.time(9, 30), dt.time(16, 0)
FILE_RE = re.compile(r"^ny4-xnas-tvitch-a-(\d{8}T\d{6})\.pcap\.zst$")

# US equity market full-day closures inside the data window (Feb-Apr 2025).
HOLIDAYS = {
    dt.date(2025, 2, 17): "Presidents' Day",
    dt.date(2025, 4, 18): "Good Friday",
}

# An RTH file this small is flagged: a full 10-minute RTH file is hundreds of MB.
DEFAULT_SMALL_RTH_BYTES = 10_000_000

CSV_FIELDS = [
    "folder", "date", "weekday", "valid_date", "status", "n_files", "total_gb",
    "first_file_utc", "last_file_utc", "rth_slots_expected", "rth_slots_present",
    "missing_rth_slots_utc", "small_rth_files_utc", "other_files",
]


@dataclass
class DayRow:
    folder: str
    date: dt.date | None
    status: str = ""
    n_files: int = 0
    total_bytes: int = 0
    first_file: dt.datetime | None = None
    last_file: dt.datetime | None = None
    rth_expected: int = 0
    rth_present: int = 0
    missing_slots: list[dt.datetime] = field(default_factory=list)
    small_slots: list[dt.datetime] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)

    def as_csv(self) -> dict:
        hm = lambda ts: ts.strftime("%H:%M")  # noqa: E731
        return {
            "folder": self.folder,
            "date": self.date.isoformat() if self.date else "",
            "weekday": self.date.strftime("%a") if self.date else "",
            "valid_date": self.date is not None,
            "status": self.status,
            "n_files": self.n_files,
            "total_gb": f"{self.total_bytes / 1e9:.2f}",
            "first_file_utc": self.first_file.strftime("%H:%M:%S") if self.first_file else "",
            "last_file_utc": self.last_file.strftime("%H:%M:%S") if self.last_file else "",
            "rth_slots_expected": self.rth_expected or "",
            "rth_slots_present": self.rth_present if self.rth_expected else "",
            "missing_rth_slots_utc": " ".join(hm(s) for s in self.missing_slots),
            "small_rth_files_utc": " ".join(hm(s) for s in self.small_slots),
            "other_files": " ".join(self.other_files),
        }


def parse_folder_date(name: str) -> dt.date | None:
    if not re.fullmatch(r"\d{8}", name):
        return None
    try:
        return dt.datetime.strptime(name, "%Y%m%d").date()
    except ValueError:
        return None


def rth_slots_utc(day: dt.date) -> list[dt.datetime]:
    """UTC start times of the 10-minute files covering 09:30-16:00 New York time."""
    start = dt.datetime.combine(day, RTH_OPEN, NY).astimezone(UTC)
    end = dt.datetime.combine(day, RTH_CLOSE, NY).astimezone(UTC)
    slots, t = [], start
    while t < end:
        slots.append(t)
        t += SLOT
    return slots


def inventory_folder(path: Path, small_rth_bytes: int = DEFAULT_SMALL_RTH_BYTES) -> DayRow:
    row = DayRow(folder=path.name, date=parse_folder_date(path.name))
    files: dict[dt.datetime, int] = {}
    for entry in path.iterdir():  # listing + stat only, never opened
        m = FILE_RE.match(entry.name)
        if not (m and entry.is_file()):
            row.other_files.append(entry.name)
            continue
        ts = dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        files[ts] = entry.stat().st_size
    row.other_files.sort()
    row.n_files = len(files)
    row.total_bytes = sum(files.values())
    if files:
        row.first_file, row.last_file = min(files), max(files)

    d = row.date
    if d is None:
        row.status = "invalid_date"
    elif d.weekday() >= 5:
        row.status = "weekend"
    elif d in HOLIDAYS:
        row.status = f"closed ({HOLIDAYS[d]})"
    else:
        slots = rth_slots_utc(d)
        row.rth_expected = len(slots)
        row.missing_slots = [s for s in slots if s not in files]
        row.small_slots = [s for s in slots if s in files and files[s] < small_rth_bytes]
        row.rth_present = len(slots) - len(row.missing_slots)
        if not files:
            row.status = "no_data"
        elif row.missing_slots:
            row.status = "incomplete"
        elif row.small_slots:
            row.status = "check_small_files"
        else:
            row.status = "complete"
    return row


def build_inventory(root: Path, small_rth_bytes: int = DEFAULT_SMALL_RTH_BYTES) -> list[DayRow]:
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    return [inventory_folder(p, small_rth_bytes) for p in folders]


def write_csv(rows: list[DayRow], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(r.as_csv() for r in rows)


def summary_md(rows: list[DayRow], root: Path, top_level_files: list[str]) -> str:
    def count(pred) -> int:
        return sum(1 for r in rows if pred(r))

    complete = [r for r in rows if r.status == "complete"]
    problem = [r for r in rows if r.status in ("incomplete", "no_data", "check_small_files")]
    lines = [
        "# NASDAQ TotalView-ITCH day inventory",
        "",
        f"Source: `{root}` (directory listings and file sizes only; no pcap was opened).",
        f"Generated by `scripts/xnas_day_inventory.py` on {dt.date.today().isoformat()}.",
        "RTH = 09:30-16:00 America/New_York = 39 ten-minute files "
        "(14:30-20:50 UTC starts before 2025-03-09, 13:30-19:50 UTC after).",
        "",
        "| Folders | Invalid dates | Weekend | Holiday | Open weekdays | Complete | Not complete |",
        "|---|---|---|---|---|---|---|",
        f"| {len(rows)} | {count(lambda r: r.status == 'invalid_date')} "
        f"| {count(lambda r: r.status == 'weekend')} "
        f"| {count(lambda r: r.status.startswith('closed'))} "
        f"| {count(lambda r: r.rth_expected > 0)} | {len(complete)} | {len(problem)} |",
        "",
        f"## Complete trading days ({len(complete)})",
        "",
        "| Date | Weekday | Files | Size (GB) |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r.date} | {r.date:%a} | {r.n_files} | {r.total_bytes / 1e9:.1f} |" for r in complete
    ]
    lines += ["", "## Trading days that are not complete", ""]
    if problem:
        lines += ["| Date | Status | Missing RTH slots (UTC) | Small RTH files (UTC) |", "|---|---|---|---|"]
        for r in problem:
            c = r.as_csv()
            lines.append(
                f"| {r.date} | {r.status} | {c['missing_rth_slots_utc'] or '-'} "
                f"| {c['small_rth_files_utc'] or '-'} |"
            )
    else:
        lines.append("None.")
    closed = [r for r in rows if r.status.startswith("closed")]
    lines += ["", "## Notes", ""]
    for r in closed:
        lines.append(f"- {r.date} {r.status}: {r.n_files} file(s) in folder.")
    weekend_with_files = [r for r in rows if r.status == "weekend" and r.n_files]
    if weekend_with_files:
        lines.append(
            "- Weekend folders with files (not trading days): "
            + ", ".join(f"{r.date} ({r.n_files})" for r in weekend_with_files)
            + "."
        )
    invalid = [r for r in rows if r.status == "invalid_date"]
    if invalid:
        nonempty = [r.folder for r in invalid if r.n_files or r.other_files]
        lines.append(
            f"- {len(invalid)} folders with impossible dates ({invalid[0].folder} ... {invalid[-1].folder}); "
            + (f"non-empty: {', '.join(nonempty)}." if nonempty else "all empty.")
        )
    odd = [r for r in rows if r.other_files]
    if odd:
        lines.append("- Non-pcap entries inside folders: " + ", ".join(f"{r.folder}: {r.other_files}" for r in odd))
    if top_level_files:
        lines.append(f"- Files at the top level of the source directory (not inspected): {', '.join(top_level_files)}.")
    return "\n".join(lines) + "\n"


def print_table(rows: list[DayRow]) -> None:
    cols = ["date", "weekday", "status", "n_files", "total_gb", "first_file_utc", "last_file_utc",
            "rth_slots_present", "missing_rth_slots_utc", "small_rth_files_utc"]
    data = []
    for r in rows:
        c = r.as_csv()
        c["date"] = c["date"] or r.folder
        data.append([str(c[k]) for k in cols])
    widths = [max(len(k), *(len(d[i]) for d in data)) if data else len(k) for i, k in enumerate(cols)]
    print("  ".join(k.ljust(w) for k, w in zip(cols, widths)))
    for d in data:
        print("  ".join(v.ljust(w) for v, w in zip(d, widths)).rstrip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subdir", default="xnas_pcaps", help="folder under raw_data_dir (default: xnas_pcaps)")
    ap.add_argument("--small-rth-mb", type=float, default=DEFAULT_SMALL_RTH_BYTES / 1e6,
                    help="flag RTH files smaller than this many MB (default: 10)")
    ap.add_argument("--hide-invalid", action="store_true", help="omit impossible-date folders from the printed table")
    args = ap.parse_args(argv)

    root = config.raw_data_dir() / args.subdir
    out_dir = config.results_dir() / "xnas_inventory"
    rows = build_inventory(root, int(args.small_rth_mb * 1e6))
    top_level_files = sorted(p.name for p in root.iterdir() if not p.is_dir())

    print_table([r for r in rows if not (args.hide_invalid and r.status == "invalid_date")])
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / "inventory.csv")
    md = summary_md(rows, root, top_level_files)
    (out_dir / "summary.md").write_text(md)
    print(f"\nWrote {out_dir / 'inventory.csv'} and {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
