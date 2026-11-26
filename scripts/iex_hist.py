#!/usr/bin/env python3
"""List and download IEX HIST market data files (TOPS, DEEP, DEEP+ / DPLS).

IEX publishes an index of all downloadable historical files at
https://iextrading.com/api/1.0/hist (a JSON map: date -> list of files).
The course downloader only accepts TOPS and DEEP; this tool accepts any feed
name in the index, including DEEP+.

Usage (run on a machine with internet access):

  # 1. Which feeds exist, and from/to which dates?
  python scripts/iex_hist.py summary

  # 2. Available dates for one feed, optionally within a window
  python scripts/iex_hist.py dates --feed DPLS --start 2020-07-01 --end 2021-01-31

  # 3. Download one day of one feed
  python scripts/iex_hist.py download --feed DPLS --date 2025-11-03

Downloads go to data/raw/iex/<FEED>/ inside the repo (gitignored) unless --out
is given. This tool never writes into the read-only raw OneDrive folder; move
files there yourself if the team keeps them on OneDrive.

The index is cached at data/raw/iex_hist_index.json; pass --refresh to re-fetch.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_URL = "https://iextrading.com/api/1.0/hist"
DEFAULT_CACHE = REPO_ROOT / "data" / "raw" / "iex_hist_index.json"
DEFAULT_OUT = REPO_ROOT / "data" / "raw" / "iex"
USER_AGENT = "iex-speed-value/0.1 (FIN 556 course project)"


# ---------------------------------------------------------------- index

def fetch_index(cache: Path, refresh: bool) -> dict:
    """Return the HIST index as {YYYYMMDD: [file, ...]}, cached on disk."""
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return data


def flatten(index: dict) -> list[dict]:
    """One dict per file: date, feed, version, protocol, size, link."""
    files = []
    for date_key, entries in index.items():
        if isinstance(entries, dict):  # tolerate a single object instead of a list
            entries = [entries]
        for e in entries or []:
            files.append({
                "date": str(e.get("date", date_key)),
                "feed": str(e.get("feed", "?")),
                "version": str(e.get("version", "?")),
                "protocol": str(e.get("protocol", "?")),
                "size": int(e.get("size") or 0),
                "link": e.get("link", ""),
            })
    return files


def parse_day(s: str | None) -> str | None:
    """Accept YYYY-MM-DD or YYYYMMDD; return YYYYMMDD."""
    if s is None:
        return None
    s = s.replace("-", "")
    dt.datetime.strptime(s, "%Y%m%d")  # validate
    return s


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


# ---------------------------------------------------------------- commands

def cmd_summary(files: list[dict]) -> None:
    by_feed: dict[tuple, list[dict]] = defaultdict(list)
    for f in files:
        by_feed[(f["feed"], f["version"], f["protocol"])].append(f)
    print(f"{'feed':<8}{'version':<9}{'protocol':<10}{'days':>6}  {'first':<10}  {'last':<10}  {'median size':>11}")
    for (feed, ver, proto), fs in sorted(by_feed.items()):
        dates = sorted({f["date"] for f in fs})
        sizes = sorted(f["size"] for f in fs)
        print(f"{feed:<8}{ver:<9}{proto:<10}{len(dates):>6}  {dates[0]:<10}  {dates[-1]:<10}  {human(sizes[len(sizes)//2]):>11}")


def select(files: list[dict], feed: str, start: str | None, end: str | None) -> list[dict]:
    out = [f for f in files if f["feed"].upper() == feed.upper()]
    if start:
        out = [f for f in out if f["date"] >= start]
    if end:
        out = [f for f in out if f["date"] <= end]
    return sorted(out, key=lambda f: (f["date"], f["version"]))


def cmd_dates(files: list[dict], feed: str, start: str | None, end: str | None) -> None:
    sel = select(files, feed, start, end)
    if not sel:
        feeds = sorted({f["feed"] for f in files})
        print(f"No {feed} files in that range. Feeds in the index: {', '.join(feeds)}")
        return
    for f in sel:
        print(f"{f['date']}  {f['feed']} v{f['version']} {f['protocol']:<8} {human(f['size']):>9}")
    print(f"{len(sel)} file(s), {human(sum(f['size'] for f in sel))} total")


def download(f: dict, out_dir: Path) -> Path:
    name = f"{f['date']}_{f['feed']}{f['version']}_{f['protocol']}.pcap.gz"
    dest = out_dir / f["feed"] / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and f["size"] and dest.stat().st_size == f["size"]:
        print(f"Already downloaded: {dest}")
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(f["link"], headers={"User-Agent": USER_AGENT})
    print(f"Downloading {f['date']} {f['feed']} ({human(f['size'])}) -> {dest}")
    done, next_report = 0, 0.0
    with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as fh:
        while chunk := resp.read(8 * 1024 * 1024):
            fh.write(chunk)
            done += len(chunk)
            if f["size"] and done / f["size"] >= next_report:
                print(f"  {done / f['size']:5.0%}  {human(done)}", flush=True)
                next_report += 0.1
    if f["size"] and part.stat().st_size != f["size"]:
        raise RuntimeError(f"Size mismatch: got {part.stat().st_size}, expected {f['size']}. Partial file kept at {part}")
    part.rename(dest)
    print(f"Done: {dest}")
    return dest


def cmd_download(files: list[dict], feed: str, date: str, out_dir: Path) -> None:
    sel = select(files, feed, date, date)
    if not sel:
        print(f"No {feed} file for {date}. Try: python scripts/iex_hist.py dates --feed {feed}")
        sys.exit(1)
    for f in sel:
        download(f, out_dir)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="List and download IEX HIST files.")
    p.add_argument("--refresh", action="store_true", help="re-fetch the index instead of using the cache")
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="index cache path")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("summary", help="feeds, versions, date ranges and sizes")

    d = sub.add_parser("dates", help="available dates for one feed")
    d.add_argument("--feed", required=True, help="e.g. DPLS, DEEP, TOPS")
    d.add_argument("--start", help="YYYY-MM-DD")
    d.add_argument("--end", help="YYYY-MM-DD")

    g = sub.add_parser("download", help="download one day of one feed")
    g.add_argument("--feed", required=True)
    g.add_argument("--date", required=True, help="YYYY-MM-DD")
    g.add_argument("--out", type=Path, default=DEFAULT_OUT, help="download directory (default data/raw/iex)")

    a = p.parse_args(argv)
    files = flatten(fetch_index(a.cache, a.refresh))

    if a.cmd == "summary":
        cmd_summary(files)
    elif a.cmd == "dates":
        cmd_dates(files, a.feed, parse_day(a.start), parse_day(a.end))
    elif a.cmd == "download":
        cmd_download(files, a.feed, parse_day(a.date), a.out)


if __name__ == "__main__":
    main()
