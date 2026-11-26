# What Is Speed Worth on IEX?

**FIN 556 — Algorithmic Market Microstructure (UIUC), group project (3 members).**
Author of this repository setup: Yiqi (Yiqi Xu).

## Overview

IEX delays incoming orders with a 350µs "speed bump", while its own view of other venues' market data is not delayed. This project asks how much speed is still worth on such a venue.

We study **cross-venue quote propagation in SPY**: when the NASDAQ best bid or offer changes, how long it takes for the same change to show up on IEX, and whether that change comes from IEX repricing D-Limit orders or from customers cancelling their orders. We then build **one taking strategy** in Strategy Studio that trades against stale IEX quotes after NASDAQ moves, and **sweep the simulated latency** from zero upward to find where the strategy stops being profitable. That cliff approximates the speed of the fastest trader doing this trade.

Research questions:

1. What does IEX's response lag look like after a NASDAQ BBO change?
2. What share of the responses are IEX-initiated repricing vs. customer cancels?
3. How long do stale IEX quotes survive, and do they end by cancel/reprice or by execution?
4. At what latency does the taking strategy stop paying after fees?
5. (Stretch) Did any of this change when D-Limit launched on 2020-10-01?

**Scope:** SPY only; ~5 trading days (3 in-sample, 2 out-of-sample). Out of scope: FPGA/hardware, market making, other symbols, SPY → leveraged ETF lead-lag.

Full plan, roles and ordered timeline: [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).

## Team

| Member | Role |
|---|---|
| Qunbo Zhou | Lead; Strategy Studio strategy and latency sweep |
| Aditi Bhatt | Data: IEX DEEP+ and NASDAQ ITCH parsers, alignment |
| Yiqi (Yiqi Xu) | Research and evaluation: lag/order-fate analysis, backtest evaluation |

## Data

Raw data is **not** stored in this repository.

| Source | Format | Notes |
|---|---|---|
| IEX HIST DEEP+ (DPLS) | `.pcap.gz` | Order-by-order; main IEX source. Free download from IEX's HIST page: https://iextrading.com/trading/market-data/#hist-download |
| IEX HIST DEEP | `.pcap.gz` | Price-level depth; SPY 2022-08-01 already parsed with the course parser (Strategy Studio warm-up) |
| NASDAQ TotalView-ITCH | vendor format | Source TBD (course-provided / Databento) |

The team keeps the raw files in a shared OneDrive folder. Point the code at your local copy via the config file (see below). `data/sample/` holds only small samples (< 50MB per file) for tests and quick development.

## Setup

```bash
git clone https://github.com/BillXYQ/iex-speed-value.git
cd iex-speed-value
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Machine-specific paths
cp config/config.example.yaml config/config.local.yaml   # then edit raw_data_dir
# or: export IEX_SPEED_RAW_DATA="/path/to/FIN556"

# Block accidental commits of files > 50MB
git config core.hooksPath .githooks
```

All code reads paths through `src/config.py`; do not hard-code data paths elsewhere.

## Getting IEX Data

`scripts/iex_hist.py` lists and downloads IEX HIST files, including DEEP+ (the course downloader only supports TOPS and DEEP). Standard library only; run it on a machine with internet access.

```bash
python3 scripts/iex_hist.py summary                     # feeds, date ranges, file sizes
python3 scripts/iex_hist.py dates --feed DPLS --start 2020-07-01 --end 2021-01-31
python3 scripts/iex_hist.py download --feed DPLS --date 2025-11-03   # -> data/raw/iex/DPLS/
```

Use the feed names printed by `summary`. Downloads go to `data/raw/` (gitignored), never into the raw OneDrive folder.

## How to Run

_Placeholder — to be filled in as the pipeline is built._

1. Parse IEX DEEP+ pcap files → `src/parsers/` (TBD)
2. Parse NASDAQ ITCH and align with IEX → `src/parsers/` (TBD)
3. Event study (quote propagation lags, order fates) → `src/research/` (TBD)
4. Strategy Studio backtest + latency sweep → `strategy/` (TBD)
5. Evaluation (PnL vs. latency, out-of-sample) → `src/research/` (TBD)

## Repository Layout

```
src/config.py   single source of truth for data paths
src/parsers/    IEX DEEP+ and NASDAQ ITCH parsers, alignment, Strategy Studio conversion
src/research/   events, lag, order fates, classification, evaluation
strategy/       Strategy Studio strategy (C++) and latency sweep scripts
scripts/        data acquisition tools (IEX HIST listing/download)
notebooks/      exploratory analysis
data/sample/    small data samples (raw data stays on OneDrive)
results/        figures and tables
docs/           project plan, iteration log
config/         path configuration (config.local.yaml is gitignored)
```

Workflow: one branch per feature, merged through a pull request; never push directly to `main`.

## References

- IEX Speed Bump: https://www.iex.io/technology
- IEX, Updating the IEX Exchange Architecture for 2021: https://iex.io/article/updating-the-iex-exchange-architecture-for-2021
- SEC Release 34-101018 (IEX 2024 data center migration): https://sec.gov/files/rules/sro/iex/2024/34-101018.pdf
- IEX D-Limit / D-Peg: https://www.iex.io/products/equities/order-types/d-peg
- Nasdaq, Tracking All-In Costs to Trade: https://www.nasdaq.com/articles/tracking-all-in-costs-to-trade
- Previous FIN 556 projects (Fall 2025): https://github.com/uiuc-fin556-algo-market-micro-fall-2025
