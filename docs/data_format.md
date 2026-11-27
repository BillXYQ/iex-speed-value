# Shared Data Format (draft v0.1)

The contract between the parsers (Aditi) and the research/evaluation code (Yiqi).
The parsers write these files; the research code reads only these files.
Owners: Yiqi (Yiqi Xu), Aditi Bhatt. Status: **draft, to be confirmed by Aditi.**

Strategy Studio tick files are a separate output with their own fixed format (`TextTickReader` / `DepthUpdateByPrice`) and are not covered here.

---

## 1. Files

```
{parsed_data_dir}/{venue}/{YYYYMMDD}/SPY_{table}.parquet
```

- `parsed_data_dir`: set in `config/config.local.yaml` (default `data/parsed`, gitignored). Never write parsed output into the raw OneDrive folder.
- `venue`: `iex` or `nasdaq` (lowercase).
- `table`: `orders` or `bbo`.
- One file per venue / trading day / table. Rows sorted by `seq`.
- Format: Parquet. Small samples (< 50MB) may go in `data/sample/` using the same layout.

## 2. Conventions

| Item | Rule |
|---|---|
| Timestamps | `int64`, **nanoseconds since Unix epoch, UTC**. NASDAQ ITCH timestamps (ns since midnight, US Eastern) must be converted using the trade date. |
| Prices | `int64`, **price × 10,000** (e.g. $409.17 → 4091700). No floats. |
| Sizes | `int64`, shares. |
| Side | `"B"` (bid/buy) or `"S"` (ask/sell). |
| Missing values | Parquet null. Never use 0 or -1 as "missing". |
| Symbol | Uppercase ticker, e.g. `SPY`. |

Two timestamps on every row:
- `ts_exch_ns`: the exchange's own timestamp inside the message (the event time), not the packet send time. **Used for all cross-venue comparisons.** Note: the course DEEP parser's tick files only keep the IEX-TP packet send time; the Stage 1 prototype uses that as a stand-in.
- `ts_recv_ns`: capture/receive time (pcap or vendor timestamp). Kept for latency accounting; may be null if unavailable.

## 3. Table `orders` (order-by-order events)

One row per order-level message, in feed order. **Do not merge, drop or reinterpret events**: if a feed represents a price change as delete + add with the same order ID, write both rows as they appear. The research code detects such patterns itself.

| Column | Type | Description |
|---|---|---|
| `ts_exch_ns` | int64 | Exchange timestamp |
| `ts_recv_ns` | int64, nullable | Capture/receive timestamp |
| `seq` | int64 | Message sequence number in the feed (strictly increasing within a file) |
| `venue` | string | `iex` / `nasdaq` |
| `symbol` | string | `SPY` |
| `event` | string | `ADD`, `MODIFY`, `REPLACE`, `DELETE`, `EXECUTE` (see below) |
| `order_id` | int64 | Venue order ID |
| `old_order_id` | int64, nullable | Only for `REPLACE`: the order ID being replaced |
| `side` | string | `B` / `S` |
| `px` | int64, nullable | See per-event meaning below |
| `size` | int64, nullable | See per-event meaning below |
| `new_px` | int64, nullable | Only for `MODIFY`: price after the change |
| `new_size` | int64, nullable | Only for `MODIFY`: displayed size after the change |
| `raw_msg_type` | string | Message type code exactly as in the feed |
| `flags` | int64, nullable | Raw flag byte(s) from the message, unparsed |

Per-event meaning of `px` and `size`:

| event | `px` | `size` |
|---|---|---|
| `ADD` | limit price | displayed shares |
| `MODIFY` (same order ID) | price before the change | displayed shares before the change |
| `REPLACE` (new order ID) | new price | new displayed shares |
| `DELETE` | price of the deleted order (if known) | shares removed (if known) |
| `EXECUTE` | execution price | executed shares |

If a feed has no separate `MODIFY`/`REPLACE` message types, they simply never appear.

## 4. Table `bbo` (best bid/offer)

One row each time the venue's best bid or best offer changes (price **or** size), computed by the parser after applying each `orders` event.

| Column | Type | Description |
|---|---|---|
| `ts_exch_ns` | int64 | Timestamp of the event that caused the change |
| `ts_recv_ns` | int64, nullable | Capture/receive timestamp of that event |
| `seq` | int64 | `seq` of that event (joins back to `orders`) |
| `venue` | string | `iex` / `nasdaq` |
| `symbol` | string | `SPY` |
| `bid_px`, `bid_sz` | int64, nullable | Best bid price and total displayed size (null if no bid) |
| `ask_px`, `ask_sz` | int64, nullable | Best ask price and total displayed size (null if no ask) |

## 5. Validation (checked by the research code on load)

Errors (file rejected):
- Missing required columns or wrong dtypes.
- `seq` not strictly increasing.
- `event`, `side`, `venue` outside the allowed values.
- `px` ≤ 0 or `size` < 0 where not null.
- `MODIFY` without `new_px`/`new_size`; `REPLACE` without `old_order_id`.

Warnings (reported, file accepted):
- `ts_exch_ns` decreasing between consecutive rows.
- `DELETE`/`EXECUTE`/`MODIFY` for an order ID never added (e.g. orders resting before the file starts).
- Crossed book (`bid_px` > `ask_px`) within one venue.

## 6. Open questions for Aditi

1. Which DEEP+ message types exist for order add / modify / delete / execute, and how does IEX publish a D-Limit reprice: as a modify on the same order ID, or as delete + add?
2. Does DEEP+ allow partial cancels (size reduced without execution)?
3. Which timestamps are available in DEEP+ and in our NASDAQ source (exchange vs. capture)?
4. Is any of this hard to produce from the parser? If so, we change the format, not the parser.

## Changelog
- v0.1: first draft (Yiqi).
- v0.2: clarify that `ts_exch_ns` is the message event time, not the packet send time (Yiqi).
