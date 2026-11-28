# Telling D-Limit repricing apart from user actions in DEEP+

Author: Yiqi (Yiqi Xu). Status: desk research, to be checked on the first real DEEP+ file.
Question: DEEP+ does not say *who* changed or removed an order. How can we separate IEX's D-Limit repricing from users' own cancels and replaces?

## 1. What the feed tells us

DEEP+ v1.06 (updated 2026-10-08):
- **Order Modify (M)**: "A displayed order that had its Price, Size, or Priority component changed as a result of user or system action." It references the Order ID of the original Add Order. Modify Flags bit 0: `0 = Reset Priority`, `1 = Maintain Priority`.
- **Order Delete (R)**: "removed from the IEX Book ... caused by user request or due to an internal system action."
- **Order Executed (L)**: the execution price "may differ from the original displayed price of the order, due to system price improvement or price sliding."
- Only **displayed** orders appear. Non-displayed orders, the hidden part of reserve orders, and all pegged orders (Rule 11.190(b)(8)(H): "Pegged orders are always non-displayed") are invisible. D-Peg is therefore out of scope.
- Add Order carries no order-type field, so we **cannot see which orders are D-Limit**.

So the actor is never labeled. We have to infer it from the price, the timing and the pattern.

## 2. What can change a displayed order's price (IEX Rule Book, 2026-11-27)

| Source | What happens | Priority |
|---|---|---|
| **User Cancel/Replace** (Rule 11.190(d)) | User changes limit price, quantity or minimum quantity. Changing any other term requires cancel + new order | New timestamp on a price change or size increase; kept on a size decrease (11.220(a)(1)(C)(i)–(iii), (a)(3)) |
| **D-Limit adjustment** (11.190(b)(7)) | When quote instability (the "crumbling quote", CQI) is determined at a price level, a D-Limit buy (sell) resting at or above (below) that level is moved to **1 MPV less aggressive than that level** | New timestamp (11.190(b)(7)(F)) |
| **D-Limit opt-in re-price** (11.190(b)(7)(E)) | If the adjusted order is still less aggressive than the NBB (NBO) **10 ms** after the latest instability determination, it is moved back to the less aggressive of its limit and the NBB (NBO) | New timestamp |
| **D-Limit opt-in cancel** (same rule) | Same trigger, but the order is cancelled | — (Delete) |
| **Display-price sliding** (11.190(h)) | Keeps displayed prices from locking/crossing protected quotes. Otherwise "IEX will ... never re-price a displayed order already posted on the Order Book to a less aggressive price" | New timestamp (11.220(a)(1)(C)(vi), (a)(4)) |
| **Reserve replenishment** | Displayed portion refilled from reserve | New timestamp (11.220(a)(1)(C)(v)) |

Key consequence: **my earlier guess was wrong.** Users *can* reprice an order with a Cancel/Replace, and DEEP+ describes Modify as covering both user and system price changes. So "same order ID, new price" does **not** by itself mean D-Limit. (Whether a user Cancel/Replace keeps the DEEP+ Order ID or shows up as Delete + Add is not stated explicitly; the Modify definition implies the former. Check on real data.)

## 3. Quote instability facts that matter for us

- Inputs are protected quotes from eleven "Signal Exchanges" including **XNGS (NASDAQ)**, plus IEX's own quote (11.190(g)).
- Determinations are made separately for the bid and the offer; each lasts **2 ms** at that price level; a new one on the same side needs **≥ 250 µs** since the last.
- It is rare: on average on 1.64 s per symbol per day (0.007% of regular hours) in Sep 2019, and 0.021%–0.125% in Q4 2019 – Apr 2020 (SEC approval, 85 FR, 2020-09-01).
- After the adjustment the order **does not revert** when the CQI turns off, unless it is adjusted again, opted in to re-price/cancel, or slid.

## 4. Fingerprints we can use

A D-Limit adjustment should look like this in DEEP+ (all testable):

1. **Modify, price less aggressive by moving to exactly one tick beyond a price level**, usually the NBB−1¢ for bids (NBO+1¢ for asks), with **priority reset** (flag bit 0 = 0) and size unchanged.
2. **Batched**: every D-Limit order on that side at or through the unstable level is adjusted by the same determination, so several order IDs get modified **at the same `ts_exch_ns`**. A user's own replace is usually one order at a time.
3. **Early relative to NASDAQ**: the CQI predicts the move, so the adjustment happens just *before* or right at the NASDAQ/NBBO change. A user reacting to a NASDAQ change goes through the **350 µs inbound speed bump**, so a user action cannot hit IEX's book until ≥ 350 µs + reaction time after the NASDAQ change. System actions are not delayed.
4. **Follow-up 10 ms later** (opt-in users only): a Modify back to the NBB/NBO (more aggressive) or a Delete on the same Order ID about 10 ms after the adjustment.
5. Display-price sliding is the other system reprice. It is distinguishable because it never makes a resting displayed order less aggressive.

User actions, by contrast:
- **Delete** with no batch and no matching CQI-style modify → cancel (user, or D-Limit opt-in cancel if ~10 ms after an adjustment).
- **Modify, size down, priority kept** → user partial cancel.
- **Modify, price change, not batched, ≥ 350 µs after the triggering NASDAQ move** → likely user replace.

## 5. Proposed classification for the order-fate code

| Label | Rule (first match wins) |
|---|---|
| `dlimit_adjust` | Modify, price less aggressive, size unchanged, priority reset, and (batch of ≥ 2 same-side modifies at the same `ts_exch_ns` **or** new price = NBB−1¢ / NBO+1¢ at that moment) |
| `dlimit_optin_reprice` | Modify, price more aggressive back to NBB/NBO, 10 ms (± tolerance) after a `dlimit_adjust` on the same Order ID |
| `dlimit_optin_cancel` | Delete 10 ms (± tolerance) after a `dlimit_adjust` on the same Order ID |
| `user_partial_cancel` | Modify, size down, price unchanged, priority kept |
| `user_replace` | Other Modify with a price change |
| `user_cancel` | Other Delete |
| `execute`, `clear` | As on the feed |

Sensitivity checks: drop the batch condition; drop the NBB−1¢ condition; vary the 10 ms tolerance. Report how many events move between labels.

Caveats: a user could mimic the D-Limit pattern; IEX and NASDAQ clocks need a documented comparability check before using the 350 µs timing test; NBB here means the NBBO built from our data (IEX + NASDAQ only), not the full SIP.

## 6. Other consequences for the project

- DEEP+ spec history starts 2024-09-03 (v1.00); v1.02 (2025-01-14) updated the overview "for the feed launch". **DEEP+ does not exist for 2020**, so the D-Limit before/after stretch goal could only use DEEP (price levels), where modifies and deletes are not visible. Treat it as aggregate-level only.
- The CQI uses NASDAQ as one of eleven inputs, so NASDAQ alone will not explain every adjustment.

## Sources

- IEX DEEP+ Specification v1.06: https://www.iex.io/documents/iex-deep-plus-specification
- IEX Exchange Rule Book (2026-11-27), Rules 11.190(b)(7), (b)(8), (d), (g), (h), 11.220: https://www.iex.io/documents/iex-exchange-rule-book
- SEC approval of D-Limit, 85 FR (2020-09-01): https://www.govinfo.gov/content/pkg/FR-2020-09-01/pdf/2020-19204.pdf
- IEX, D-Limit hit rates / cancel-reprice option: https://iex.io/article/d-limit-hit-rates-are-better-than-ever
- IEX D-Limit product page: https://www.iex.io/products/equities/order-types/d-limit
