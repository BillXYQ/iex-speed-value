"""Tests for scripts/xnas_day_inventory.py on a fake directory tree (sparse files, no real pcaps)."""

import csv
import datetime as dt
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location("xnas_day_inventory", REPO / "scripts" / "xnas_day_inventory.py")
inv = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = inv
_spec.loader.exec_module(inv)

BIG = 500_000_000  # sparse, so no real disk is used


def make_day(root: Path, folder: str, start_utc: str, end_utc: str, size: int = BIG,
             skip: tuple[str, ...] = (), small: tuple[str, ...] = ()) -> None:
    d = root / folder
    d.mkdir(parents=True)
    t = dt.datetime.strptime(folder + start_utc, "%Y%m%d%H%M")
    end = dt.datetime.strptime(folder + end_utc, "%Y%m%d%H%M")
    while t <= end:
        hm = t.strftime("%H%M")
        if hm not in skip:
            with (d / f"ny4-xnas-tvitch-a-{t:%Y%m%dT%H%M%S}.pcap.zst").open("wb") as f:
                f.truncate(1000 if hm in small else size)
        t += dt.timedelta(minutes=10)


def test_rth_slots_follow_dst():
    before = inv.rth_slots_utc(dt.date(2025, 3, 7))
    after = inv.rth_slots_utc(dt.date(2025, 3, 10))
    assert len(before) == len(after) == 39
    assert (before[0].hour, before[0].minute, before[-1].hour, before[-1].minute) == (14, 30, 20, 50)
    assert (after[0].hour, after[0].minute, after[-1].hour, after[-1].minute) == (13, 30, 19, 50)


def test_inventory_statuses(tmp_path):
    root = tmp_path / "xnas_pcaps"
    make_day(root, "20250307", "0800", "2350")                      # Fri, pre-DST, complete
    make_day(root, "20250310", "0700", "2350")                      # Mon, post-DST, complete
    make_day(root, "20250311", "0700", "2350", skip=("1500", "1950"))  # missing two RTH slots
    make_day(root, "20250312", "0700", "2350", small=("1600",))     # tiny RTH file
    make_day(root, "20250304", "1330", "2350")                      # pre-DST but starts at 13:30 UTC: fine
    make_day(root, "20250305", "0800", "2040")                      # pre-DST, ends 20:40: misses 20:50
    make_day(root, "20250308", "0000", "0100")                      # Saturday
    make_day(root, "20250418", "0000", "0000")                      # Good Friday
    (root / "20250230").mkdir()                                     # impossible date
    (root / "20250313").mkdir()                                     # weekday, empty
    (root / "20250313" / "notes.txt").write_text("x")

    rows = {r.folder: r for r in inv.build_inventory(root)}
    assert rows["20250307"].status == "complete"
    assert rows["20250310"].status == "complete"
    assert rows["20250310"].n_files == 102
    assert rows["20250304"].status == "complete"
    r = rows["20250311"]
    assert r.status == "incomplete" and r.rth_present == 37
    assert [s.strftime("%H:%M") for s in r.missing_slots] == ["15:00", "19:50"]
    assert rows["20250312"].status == "check_small_files"
    assert [s.strftime("%H:%M") for s in rows["20250312"].small_slots] == ["16:00"]
    assert [s.strftime("%H:%M") for s in rows["20250305"].missing_slots] == ["20:50"]
    assert rows["20250308"].status == "weekend"
    assert rows["20250418"].status == "closed (Good Friday)"
    assert rows["20250230"].status == "invalid_date" and rows["20250230"].date is None
    assert rows["20250313"].status == "no_data" and rows["20250313"].other_files == ["notes.txt"]


def test_main_writes_outputs(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "raw"
    make_day(raw / "xnas_pcaps", "20250310", "0700", "2350")
    (raw / "xnas_pcaps" / "pcap_list.txt").write_text("")
    monkeypatch.setattr(inv.config, "raw_data_dir", lambda: raw)
    monkeypatch.setattr(inv.config, "results_dir", lambda: tmp_path / "results")

    assert inv.main([]) == 0
    out = tmp_path / "results" / "xnas_inventory"
    with (out / "inventory.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["date"] == "2025-03-10" and rows[0]["status"] == "complete"
    md = (out / "summary.md").read_text()
    assert "## Complete trading days (1)" in md and "| 2025-03-10 | Mon |" in md
    assert "pcap_list.txt" in md
    assert "complete" in capsys.readouterr().out
