# FIN 556 Group Project Plan
## Cross-Venue Quote Propagation and the Value of Speed on IEX

Team (3): Qunbo Zhou (lead), Aditi Bhatt, Yiqi Xu
Status: draft v2 (slimmed). No dates; the timeline is an ordered sequence of stages.

---

## 0. Summary

When a quote changes on NASDAQ, how long until the same change shows up on IEX? How much of that response comes from **IEX repricing its customers' D-Limit orders** (IEX's inbound market data is not delayed) versus **customers canceling their own orders** (their messages must pass IEX's 350µs inbound speed bump)? And at what latency does trading against stale IEX quotes stop paying?

Core work:
1. **Measurement study** on IEX DEEP+ (order-by-order) and NASDAQ ITCH data, SPY only.
2. **One taking strategy** in Strategy Studio that trades against stale IEX quotes after NASDAQ moves.
3. **Latency sweep**: start at zero latency, increase until PnL falls off a cliff. The cliff approximates the speed of the fastest trader doing this trade.

Stretch goal (only if data comes easily): D-Limit before/after comparison (launch: Oct 1, 2020).

Out of scope: FPGA/hardware, market making, other symbols, SPY → leveraged ETF lead-lag.

---

## 1. Research Questions

**Main question**
After a NASDAQ quote change, how quickly does IEX's quote follow, how much of that is D-Limit repricing vs. customer cancels, and what latency threshold does that imply for stale-quote sniping?

- Q1. Distribution of IEX's response lag after NASDAQ best bid/offer changes.
- Q2. Share of responses that are IEX-initiated repricing vs. customer cancels.
- Q3. How long stale IEX quotes survive, and whether they end by cancel/reprice or by execution (sniped).
- Q4. The latency at which the taking strategy stops being profitable after fees.
- Q5 (stretch). Whether Q1–Q4 changed after D-Limit launched.

**Hypothesis to test**
The lag distribution is bimodal: a fast mode well under 350µs (IEX repricing) and a slower mode at or above ~350µs (customer cancels through the speed bump).

---

## 2. Background Facts

**IEX speed bump by period** (sources in References)

| Period | Inbound delay | Outbound delay (incl. market data) |
|---|---|---|
| Before Feb 2021 | 350µs | 350µs |
| Feb 2021 – 2024 data center move | 350µs | 37µs |
| During 2024 move (a few weeks) | 387µs | 37µs |
| After 2024 move | 350µs | negligible |

- IEX's inbound market data from other venues is not delayed.
- Simulated latency must match the data date. For recent data: 350µs inbound only.

**D-Limit** (not D-Peg): a displayed order that IEX reprices when its Signal predicts a price change. D-Peg is dark and does not appear in displayed market data. SEC approved Aug 2020; launched Oct 1, 2020; still active. Clean before/after window: Jul–Sep 2020 vs. Oct 2020–Jan 2021 (before the Feb 2021 outbound change).

**Fees**: include each venue's take fee in PnL (look up current IEX and NASDAQ fee schedules).

---

## 3. Data

| Data | Use | Status |
|---|---|---|
| IEX HIST DEEP+ (DPLS), order-by-order | Research (order fates) + Strategy Studio ticks | C++ parser to build from the course DEEP parser |
| NASDAQ TotalView-ITCH | Trigger events + Strategy Studio ticks | Source to confirm; build on last year's group_01 pipeline |
| IEX DEEP (already parsed: SPY, 2022-08-01) | Strategy Studio warm-up, early prototyping | Done |

**Scope**
- Symbol: SPY only.
- Dates: 1 dev day, then ~5 days total (3 in-sample, 2 out-of-sample). Days must exist for both venues.

**Timestamps**
- Use exchange timestamps for cross-venue comparisons; keep capture timestamps too.
- Document clock assumptions (different data centers).

**Shared format** (Parquet, prices as integers ×10,000)
`data/parsed/{venue}/{date}/SPY_{table}.parquet`

- **orders**: `ts_exch_ns, ts_capture_ns, venue, event (add/modify/delete/execute), order_id, side, price, size, new_price, new_size, flags, seq`
- **bbo**: `ts_exch_ns, ts_capture_ns, venue, bid_px, bid_sz, ask_px, ask_sz`
- **Strategy Studio tick files**: exact `TextTickReader` / `DepthUpdateByPrice` format, IEX + NASDAQ merged and sorted by source time.

---

## 4. Methodology

### 4.1 Events
- Event = a change in NASDAQ's best bid or best offer.
- Keep only events where IEX had a displayed quote at the now-stale price on the affected side.
- Two thresholds: any price change; ≥2 ticks.

### 4.2 IEX response lag and order fates
- For each event, every IEX order resting at the stale price: record what happens within 5ms (deleted, repriced/modified, executed, unchanged) and the lag.
- Output: lag histogram/CDF; share of each fate.

### 4.3 Repricing vs. customer cancel
1. DEEP+ flags/event types, if they mark exchange-initiated repricing.
2. Order ID kept with a new price (repricing) vs. delete (cancel).
3. Timing: responses much faster than 350µs cannot be a customer reacting to the NASDAQ change.
Validate on a handful of examples before applying at scale.

### 4.4 Strategy (taking)
- Signal: NASDAQ BBO moves so an IEX quote becomes stale by at least N ticks after fees.
- Action: IOC order on IEX to take the stale quote; exit on IEX after a fixed short holding time.
- Fair value: NASDAQ mid.
- Limits: max position, max holding time.

### 4.5 Latency in Strategy Studio
- Find the default simulated latency (professor: 0 or 100µs, in a SQLite settings DB) and how to change it (group_06 used `set_simulator_params -latency_to_exchange`; confirm units).
- Reaction delay in strategy code: template from group_01 `VenueArbPlusLatencyStrategy` (`latency_ns`).
- Add IEX's 350µs inbound speed bump to orders sent to IEX.

### 4.6 Latency sweep (main result)
- Grid (µs): 0, 50, 100, 200, 350, 500, 1000; refine around the cliff.
- Per point: PnL after fees, fills, fill rate, PnL per share.
- Output: PnL-vs-latency curve and the cliff location.

### 4.7 Evaluation
- Parameters chosen on in-sample days, results reported on out-of-sample days.
- Iteration log: what changed, why, result (needed for the report's "evolution of research").

### 4.8 Stretch: D-Limit before/after
Only if both venues' data for Jul 2020 – Jan 2021 is easily available: repeat 4.2–4.3 on both periods and compare.

---

## 5. Repositories (GitHub)

Each teammate keeps their own repo; the interface between them is the shared data format.

| Repo | Owner | Contents |
|---|---|---|
| `BillXYQ/iex-speed-value` (public) | Yiqi | Research and evaluation, plan, shared docs |
| [`AditiB12/Cross-Venue-Quote-Propagation-and-the-Value-of-Speed-on-IEX`](https://github.com/AditiB12/Cross-Venue-Quote-Propagation-and-the-Value-of-Speed-on-IEX) | Aditi | IEX DEEP+ and NASDAQ ITCH parsers, Parquet conversion, data format (source of truth) |
| Qunbo's repo (link TBD) | Qunbo | Strategy Studio strategy (C++) and latency sweep scripts |

This repo:

```
iex-speed-value/
├── README.md        # overview, setup, final report
├── CLAUDE.md        # project rules (git workflow, data paths, IEX latency table)
├── config/          # path config (config.local.yaml is gitignored), fees
├── src/
│   ├── config.py    # single source of truth for data paths
│   └── research/    # loading/validation, events, lag, order fates, classification, evaluation
├── scripts/         # prototypes, inventories, evaluation CLI
├── data/sample/     # small samples only (< 50MB); raw data stays on OneDrive / the VM
├── results/         # figures and tables
└── docs/            # this plan, data format (mirror), iteration log
```

- Parsed data moves between repos as Parquet files (OneDrive), never as raw pcaps in git.
- Every feature on its own branch, merged through a pull request; never push directly to `main`.
- Credit reused code (course parser, group_01, group_06) in commits and the README.

---

## 6. Roles

**Qunbo — Lead / Strategy**
- Professor communication; GitHub repo and issues.
- Strategy Studio setup: data paths, IEX + NASDAQ feeds, latency and fee settings.
- Taking strategy (C++) and latency sweep.
- Report: strategy and latency sweep sections.

**Aditi — Data**
- IEX DEEP+ parser (C++) and NASDAQ ITCH parser.
- Shared-format outputs + merged Strategy Studio tick files.
- Timestamp alignment and basic data checks.
- Report: data and parsing section.

**Yiqi — Research & Evaluation**
- Shared data format (with Aditi); research code built on sample data first.
- Events, lag, order fates, repricing vs. cancel classification.
- Strategy parameter spec; evaluation of backtests; PnL-vs-latency curve; out-of-sample.
- Iteration log; final report integration.

---

## 7. Ordered Timeline

### Stage 0 — Setup
- **Qunbo**: ask the professor the open questions (§9); create GitHub repo and issues; get Strategy Studio running; locate latency and fee settings.
- **Aditi**: get the DEEP+ spec; review the DEEP parser and group_01's NASDAQ pipeline; download one DEEP+ day.
- **Yiqi**: write the shared data format with Aditi; build a small synthetic sample to develop research code.

### Stage 1 — IEX prototype (1 day)
- **Aditi**: DEEP+ parser → orders + bbo for SPY; check the BBO against the DEEP output.
- **Qunbo**: warm-up backtest on the existing IEX SPY tick file (2022-08-01); learn the CRA export and latency setting.
- **Yiqi**: research code on synthetic data, then on real IEX data; evaluation script that reads Qunbo's CRA export.

### Stage 2 — Add NASDAQ (same day)
- **Aditi**: NASDAQ ITCH parser; timestamp alignment; merged Strategy Studio tick file.
- **Qunbo**: strategy skeleton subscribing to both venues; fee settings.
- **Yiqi**: cross-venue lag and order-fate analysis on the one day (Q1–Q3).

### Check-in — Feasibility (team meeting)
- Yiqi presents event counts, lag distribution, stale-quote survival.
- Decide thresholds and the final set of days. If events are too few, add days or lower thresholds.

### Stage 3 — Strategy v1 on all days
- **Aditi**: run the pipeline on all ~5 days.
- **Yiqi**: parameter spec; full lag/fate analysis; validated classification.
- **Qunbo**: implement strategy v1 from the spec; first backtests with fees.

### Stage 4 — Latency sweep and iterations
- **Qunbo**: automate and run the sweep; iterate the strategy (v2, v3).
- **Yiqi**: cliff curve, out-of-sample results, iteration log.
- **Aditi**: support date-specific latency settings; help debug data issues found in backtests; (stretch) parse 2020 data if available.

### Stage 5 — Write-up
- **Everyone**: own report section; all code pushed.
- **Yiqi**: integrate the README report.
- **Qunbo**: presentation.
- **Aditi**: "how to reproduce" instructions.

**Critical path**: Aditi's parsers (Stage 1–2) → feasibility check → strategy v1 → latency sweep.
While parsers are in progress, Yiqi works on synthetic/existing data and Qunbo learns Strategy Studio on the existing SPY tick file.

---

## 8. Handoffs

| From | To | What | Stage |
|---|---|---|---|
| Yiqi + Aditi | All | Shared data format | 0 |
| Aditi | Yiqi | orders / bbo Parquet | 1–3 |
| Aditi | Qunbo | Strategy Studio tick files | 1–3 |
| Qunbo | Yiqi | CRA exports from each backtest | 1 onward |
| Yiqi | Qunbo | Parameter spec; sweep evaluation | 3–4 |

---

## 9. Open Questions for the Professor

1. Does the course provide NASDAQ ITCH data (e.g. via Databento)? Which dates?
2. Is there a known way in DEEP+ to identify IEX-initiated repricing vs. customer cancels?
3. Strategy Studio latency setting: location (SQLite), units, per-venue?
4. (Stretch) Is DEEP+ / NASDAQ data available for Jul 2020 – Jan 2021?

---

## 10. Main Risks

| Risk | Fallback |
|---|---|
| No NASDAQ data | IEX-only study: stale-quote survival after IEX's own BBO moves, plus the latency sweep |
| DEEP+ cannot flag repricing | Order-ID + timing heuristics (§4.3) |
| Too few events | More days or lower thresholds |
| Backtest fills too optimistic | Compare with stale-quote survival measured in the data |

---

## 11. Deliverables
- GitHub repo: parsers, research code, strategy, sweep scripts, reproducible instructions.
- Final report (README): question, background, data and methods, findings, latency sweep, evolution of research, limitations.
- Presentation.

---

## References
- IEX Technology (Speed Bump): https://www.iex.io/technology
- SEC Release 34-101018 (IEX 2024 data center migration): https://sec.gov/files/rules/sro/iex/2024/34-101018.pdf
- IEX, Updating the IEX Exchange Architecture for 2021: https://iex.io/article/updating-the-iex-exchange-architecture-for-2021
- IEX D-Peg / D-Limit: https://www.iex.io/products/equities/order-types/d-peg
- Nasdaq, Tracking All-In Costs to Trade: https://www.nasdaq.com/articles/tracking-all-in-costs-to-trade
- Previous FIN 556 projects (Fall 2025): https://github.com/uiuc-fin556-algo-market-micro-fall-2025
