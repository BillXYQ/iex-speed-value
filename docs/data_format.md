# Shared Data Format (v0.3)

The contract between the parsers (Aditi Bhatt, in her own repo) and the research/evaluation code in this repo (Yiqi (Yiqi Xu)).
**The source of truth is `docs/data_format.md` in Aditi's parser repo.** This file mirrors it and adds notes for the research side. If the two ever disagree, hers wins and this file gets updated.

Strategy Studio tick files are a separate output with their own fixed format (`TextTickReader` / `DepthUpdateByPrice`) and are not covered here.

---

## 1. Files

```
{parsed_data_dir}/{venue}/{YYYYMMDD}/SPY_{table}.parquet
```

- `parsed_data_dir`: set in `config/config.local.yaml` (default `data/parsed`, gitignored). Never write parsed output into the raw OneDrive folder.
- Directory `venue` is lowercase (`iex`, `nasdaq`); the `venue` column inside the files is uppercase (`IEX`, `NASDAQ`).
- `table`: `orders`, `bbo`, `admin`. The parser writes CSV first; `scripts/to_parquet.py` in Aditi's repo converts it to typed Parquet (zstd).
- Read files with `src.research.schema.load_table(path, "orders" | "bbo")`. It keeps integer columns with nulls as nullable integers (the default pandas reader turns them into float64, which corrupts ns timestamps and order IDs) and casts uint64 sequence/size columns to int64. `order_id` stays uint64.

## 2. Conventions

| Item | Rule |
|---|---|
| Timestamps | Signed 64-bit integer **nanoseconds since Unix epoch, UTC**. Never convert to float. NASDAQ ITCH timestamps (ns since midnight, US Eastern) must be converted using the trade date. |
| Prices | Signed 64-bit integer, **price × 10,000** (5000100 = $500.01). No floats. |
| Side | `B` or `S`. For referenced orders it is recovered from book state. |
| Missing values | Empty in CSV, null in Parquet. |
| Empty book side | Null price, size 0. |

Three timestamps:
- `ts_exch_ns`: exchange message timestamp (event time). **Used for all cross-venue comparisons.**
- `ts_capture_ns`: packet capture time, converted to ns without adding precision.
- `ts_send_ns` (orders only): IEX-TP segment send time.

Exchange and capture timestamps mean different things; cross-venue comparison needs documented clock comparability.

## 3. Table `orders`

| Column | Meaning |
|---|---|
| `ts_exch_ns`, `ts_capture_ns`, `ts_send_ns` | See above |
| `venue`, `symbol` | `IEX` / `NASDAQ`, `SPY` |
| `event` | `add`, `modify`, `delete`, `execute`, `clear` (lowercase) |
| `order_id` | Unsigned 64-bit; null on `clear` |
| `side` | `B` / `S`; null on `clear` |
| `price`, `size` | Booking price and remaining size **before** the update; on `add`, the newly added values |
| `new_price`, `new_size` | Booking price and remaining size **after** the update; terminal orders have null price and size 0 |
| `flags` | Raw second byte; interpret by message type |
| `seq` | Transport message sequence |
| `message_type` | Original wire message type |
| `executed_size`, `execution_price` | Trade quantity and actual execution price (execute only) |
| `channel`, `session` | Transport stream identity |

Rules that matter for the research:
- `clear` applies to all displayed orders in the symbol's book. Keep it when computing order fates.
- An execution can have a different price from the order's booking price.
- A `modify` replaces the total remaining quantity.
- **A `modify` or `delete` is not labeled as a customer action or a D-Limit action.** The DEEP+ spec allows both user and system causes, and modify flag bit 0 describes priority treatment, not the actor. Separating reprices from cancels is research work (Yiqi), not parser output.
- Rebuild books in `seq` order. Do not sort by timestamp before applying updates.

## 4. Table `bbo`

Columns: `ts_exch_ns`, `ts_capture_ns`, `venue`, `symbol`, `bid_px`, `bid_sz`, `ask_px`, `ask_sz`, `seq`.

- Sizes sum all displayed orders at the best price.
- A row is emitted when a best price or aggregate size changes.
- The CSV contains intermediate per-message changes; same-time messages may form one atomic exchange event. Collapse these before interpreting momentary spreads.

## 5. Table `admin`

Columns: `ts_exch_ns`, `ts_capture_ns`, `venue`, `symbol`, `message_type`, `flags`, `seq`. A minimal audit record of selected-symbol administrative, trade and trade-break messages. Halt/session state needs explicit filtering before strategy research.

## 6. Validation in this repo (`src/research/schema.py`)

Errors (file rejected):
- Missing columns or non-integer dtypes where integers are expected; nulls in non-nullable columns.
- `venue` not `IEX`/`NASDAQ`; `event` outside the five values; `side` not `B`/`S` on non-clear events; null `order_id` on non-clear events.
- Non-positive prices or negative sizes.
- `bbo`: `seq` not strictly increasing; empty side (null price) with non-zero size.
- `orders`: `seq` decreasing; `execute` without `executed_size`/`execution_price`.

Warnings (file accepted): `ts_exch_ns` decreasing; crossed book (`bid_px` > `ask_px`).

## 7. Notes on the DEEP stand-in

Until DEEP+ data is available, `src/research/course_parser_io.py` builds a `bbo` table from the course parser's DEEP tick file (SPY, 2022-08-01). That file only keeps the IEX-TP packet send time, which is `ts_send_ns` in this format; the adapter uses it as a stand-in for `ts_exch_ns`. It carries no `orders` table.

## Changelog
- v0.1: first draft (Yiqi).
- v0.2: clarify that `ts_exch_ns` is the message event time, not the packet send time (Yiqi).
- v0.3: adopt Aditi's format as the source of truth: `ts_recv_ns` → `ts_capture_ns`, `px` → `price`, lowercase events with `clear`, uppercase venue, execution fields, empty side = null price + size 0 (Yiqi).
