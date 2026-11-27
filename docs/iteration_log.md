# Iteration Log

One entry per change to data, research method, or strategy. This feeds the "evolution of research" section of the final report.

| # | Date | Author | Area | What changed | Why | Result |
|---|---|---|---|---|---|---|
| 1 | 2026-11-26 | Yiqi | Research | Stage 1 IEX prototype: BBO built from the course DEEP tick file for SPY 2022-08-01; descriptive stats and figures (`results/iex_bbo_20220801/`) | IEX HIST downloads are paused; use the one real day we have to build and test the research code | BBO matches the course parser's level-1 snapshots on 818,336/818,336 rows. IEX's own SPY spread is wide (median ~12 cents), so IEX is rarely at the NBBO. About 20% of best prices last under 350µs. Both best-price lifetimes and BBO update intervals show a spike at 450–525µs, possibly the speed bump plus a reaction time; to be tested against NASDAQ data |
