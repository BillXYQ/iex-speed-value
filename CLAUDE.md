# CLAUDE.md

FIN 556 (UIUC Algorithmic Market Microstructure) group project: the value of speed on IEX, via NASDAQ → IEX cross-venue quote propagation and an SPY-led ETF trading strategy.

## Authorship
- In docs and attributions, write my name as **Yiqi (Yiqi Xu)**.

## Git workflow
- Never push directly to `main` (the initial commit was the only exception).
- Every feature gets its own branch and goes through a pull request.
- Commit messages are in English.

## Data and paths
- Raw data lives on OneDrive, outside the repo:
  `/Users/bill/Library/CloudStorage/OneDrive-UniversityofIllinois-Urbana/Course Files/FIN556`
- That folder is **read-only**: never modify, move, or delete anything in it.
- Code gets paths only from `src/config.py` (backed by `config/config.example.yaml`, the gitignored `config/config.local.yaml`, or the `IEX_SPEED_RAW_DATA` env var). Don't hard-code the path anywhere else.
- Never commit `*.pcap`, `*.pcap.gz`, `data/raw/`, or any file > 50MB. Only small samples go in `data/sample/`.

## IEX latency: set it by the data date
| Period | Inbound (orders) | Outbound (incl. market data) |
|---|---|---|
| Before Feb 2021 | 350µs | 350µs |
| Feb 2021 – 2024 data center migration | 350µs | 37µs |
| During 2024 migration (a few weeks) | ~387µs; routable orders get an extra 350µs | 37µs |
| After 2024 migration | 350µs | negligible (ignore) |

- Inbound delay is always 350µs, apart from the 2024 migration weeks noted above.
- IEX's own inbound market data from other venues is not delayed.
- **D-Limit** launched **2020-10-01**. The clean before/after comparison is **2020 Q3 (Jul–Sep)** vs. **Oct 2020 – Jan 2021** (ends before the Feb 2021 outbound change).
