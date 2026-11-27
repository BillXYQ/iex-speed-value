# Exchange Fees for the Backtest

Fees for **taking** (removing displayed liquidity) in **SPY** (Tape B, price ≥ $1.00) during our NASDAQ data window, **2025-02-03 to 2025-04-30**. Machine-readable values: `config/fees.yaml`; code: `src/research/fees.py`. Compiled by Yiqi (Yiqi Xu), 2026-11-27.

## Summary ($ per share)

| Venue | Remove displayed liquidity | Notes |
|---|---|---|
| IEX | **$0.0030** (Tier 1) | Applies to a member adding < 25,000 ADV of displayed liquidity, which is our taking-only strategy. Members adding ≥ 25,000 ADV pay $0.0022 (raised from $0.0020 effective 2025-02-01). Removing non-displayed liquidity: $0.0010. |
| NASDAQ | **$0.0030** | Default "All MPIDs" fee to remove liquidity. Default credit for adding displayed liquidity: $0.0018 (not used). |
| SEC Section 31 (sells only) | **$27.80 per $1 million** of notional | Through 2025-05-13; $0.00 from 2025-05-14. |

A round trip on IEX (buy + sell, 100 shares of SPY at ~$580) therefore costs about $0.60 in exchange fees plus ~$1.61 in Section 31 fees on the sell, about **2.2¢ per share** in total. At SPY's price the Section 31 fee (~1.6¢ per share sold) is larger than the exchange fees (0.6¢ per round trip). A stale-quote trade has to capture **more than about 2 cents per share** round trip to break even, i.e. the stale quote must be off by at least 2–3 ticks.

## Why this matters for the study
- IEX used to charge a separate **Crumbling Quote Remove Fee** ($0.0030 on top of the normal fee) on orders that removed liquidity while its crumbling quote indicator was on, above a 5% monthly volume threshold. That fee was **eliminated in 2020**, so it does not apply to our 2025 data. It is still worth mentioning in the report: it was an explicit price on exactly the stale-quote sniping we study.
- Strategy Studio's shared default (`strategy.db`, `AccountFees`) is $0.0012 per share plus 2.24e-05 of notional on sells, identical for all venues. It understates our costs, so evaluation uses `config/fees.yaml` instead.

## Scenarios for sensitivity
`base` (IEX 0.0030, NASDAQ 0.0030), `iex_tier2` (IEX 0.0022), `zero` (no fees). Report results under all three.

## Caveats
- NASDAQ's figure comes from the current price list; confirm it against the Equity 7, Section 118 rule text in force in Feb–Apr 2025 before the final report.
- We ignore broker commissions, clearing fees and the FINRA TAF.
- The 2022-08-01 IEX prototype day had a different fee schedule; these numbers are only for the 2025 window.

## Sources
- IEX, SR-IEX-2025-03 (displayed removal fee $0.0020 → $0.0022, Tier 1 $0.0030 unchanged, operative 2025-02-01): https://www.sec.gov/files/rules/sro/iex/2025/34-102357-19b-4.pdf
- IEX fee schedule exhibit, SR-IEX-2025-08 (TLB $0.0022, TIB $0.0010): https://www.sec.gov/files/rules/sro/iex/2025/34-103233-ex5.pdf
- IEX, elimination of the Crumbling Quote Remove Fee (2020): https://regulations.justia.com/regulations/fedreg/2020/09/29/2020-21404.html
- NASDAQ price list: https://www.nasdaqtrader.com/Trader.aspx?id=PriceListTrading2
- SEC Section 31 fee rate advisory, FY2025: https://www.sec.gov/rules-regulations/fee-rate-advisories/2025-2
