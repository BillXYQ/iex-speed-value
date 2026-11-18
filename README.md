# What Is Speed Worth on IEX?

**FIN 556 — Algorithmic Market Microstructure (UIUC), group project (3 members).**
Author of this repository setup: Yiqi (Yiqi Xu).

## Overview

IEX delays incoming orders with a 350µs "speed bump", while its own view of other venues' market data is not delayed. This project asks how much speed is still worth on such a venue.

We study **cross-venue quote propagation**: when the NASDAQ best bid or offer changes, how long it takes for the same change to show up on IEX, and whether that change comes from IEX repricing D-Limit orders or from customers cancelling their orders. We then use **SPY as a leading signal** to trade related ETFs against stale IEX quotes, and sweep the simulated latency to find where the strategy stops being profitable.

Research questions (draft):

1. What does IEX's response lag look like after a NASDAQ BBO change?
2. What share of the responses are IEX-initiated repricing vs. customer cancels?
3. How long do stale IEX quotes survive, and how often are they picked off?
4. At what latency does trading on the SPY lead stop paying after fees?
5. (Stretch) Did any of this change when D-Limit launched on 2020-10-01?

## Data

Raw data is **not** stored in this repository.

| Source | Format | Notes |
|---|---|---|
| IEX HIST (DEEP / DEEP+) | `.pcap.gz` | Free download from IEX's HIST page: https://iextrading.com/trading/market-data/#hist-download |
| NASDAQ TotalView-ITCH | vendor format | Source TBD (course-provided / Databento) |

The team keeps the raw files in a shared OneDrive folder. Point the code at your local copy via the config file (see below). `data/sample/` holds only small samples (< 50MB per file) for tests and quick development.

## Setup

```bash
git clone https://github.com/BillXYQ/iex-speed-value.git
cd iex-speed-value
python3 -m venv .venv && source .venv/bin/activate
pip install pyyaml          # requirements.txt to follow

# Machine-specific paths
cp config/config.example.yaml config/config.local.yaml   # then edit raw_data_dir
# or: export IEX_SPEED_RAW_DATA="/path/to/FIN556"

# Block accidental commits of files > 50MB
git config core.hooksPath .githooks
```

All code reads paths through `src/config.py`; do not hard-code data paths elsewhere.

## How to Run

_Placeholder — to be filled in as the pipeline is built._

1. Parse IEX HIST pcap files → `TBD`
2. Parse NASDAQ ITCH → `TBD`
3. Event study (quote propagation lags, order fates) → `notebooks/TBD`
4. Backtest + latency sweep → `TBD`

## Repository Layout

```
src/          parsing and backtesting code
notebooks/    exploratory analysis
data/sample/  small data samples (raw data stays on OneDrive)
results/      figures and tables
docs/         plan, notes, report material
config/       path configuration (config.local.yaml is gitignored)
```

## References

- IEX Speed Bump: https://www.iex.io/technology
- IEX, Updating the IEX Exchange Architecture for 2021: https://iex.io/article/updating-the-iex-exchange-architecture-for-2021
- SEC Release 34-101018 (IEX 2024 data center migration): https://sec.gov/files/rules/sro/iex/2024/34-101018.pdf
- IEX D-Limit / D-Peg: https://www.iex.io/products/equities/order-types/d-peg
