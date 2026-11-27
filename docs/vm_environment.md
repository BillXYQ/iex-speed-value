# Course VM Environment (fin556 VM)

What we found on the course VM on 2026-11-27, by read-only inspection (Yiqi). Nothing shared was modified.
Re-check before relying on anything here: the VM is shared and may change.

## Access
- Browser remote desktop through `vpn2.fintech.illinois.edu` (session `rdp_fin556vm`), Xfce desktop, login = NetID.
- Copy/paste between your own computer and the VM does not work in the web client. Workaround: open a browser **inside** the VM and copy/paste within the VM (terminal paste is `Ctrl+Shift+V`, copy is `Ctrl+Shift+C`).

## Machine
- Ubuntu 22.04.3 LTS, 192 cores, 125 GB RAM. **Shared by the whole class** (50+ accounts): be considerate with CPU and memory.
- Tools present: `python3` (3.10), `git`, `g++`, `code` (VS Code), `zstd`, `tcpdump`, `sqlite3`. Not present: `tshark`.

## Disk (the main constraint)
| Mount | Size | Free | Notes |
|---|---|---|---|
| `/` (includes `/home`) | 62 GB | ~5 GB | Shared by everyone. **Never write large files to your home directory.** |
| `/db_pcaps` | 28 TB | 3.3 TB | Raw market data (read only for us) |
| `/vagrant` | 913 GB | 123 GB | Course setup files, Strategy Studio installers, course IEX parser |

- Last year's scripts reference a per-student workspace `/mnt/students_7tb_ssd/<netid>`, but it is **not mounted** on this VM. Asked the professor where to write large intermediate files.
- Process raw data as a stream (e.g. `zstd -dc file.pcap.zst | parser --symbol SPY`) so only the small SPY output is written.

## Market data on the VM
| Path | Venue / feed | Dates | Size per day | Layout |
|---|---|---|---|---|
| `/db_pcaps/xnas_pcaps/YYYYMMDD/` | NASDAQ TotalView-ITCH (`ny4-xnas-tvitch`) | 2025-02-01 to 2025-04-30 | ~24 GB (zstd) | 96 files × 10 minutes, `ny4-xnas-tvitch-a-YYYYMMDDTHHMMSS.pcap.zst` |
| `/db_pcaps/glbx_pcaps/YYYYMMDD/` | CME Globex (`dc3-glbx`), all products | 2025-02-01 onward, 89 days | ~388 GB (zstd) | 10-minute files, `dc3-glbx-a-YYYYMMDDTHHMMSS.pcap.zst` |
| `/vagrant/iexdownloaderparser/data/iex_downloads/DEEP/` | IEX | none | — | Only a README; **no IEX data on the VM** |

- `xnas_pcaps` also contains 72 empty placeholder folders with impossible dates (`20250229` to `20250300`); ignore them. A `pcap_list.txt` sits at the top level of `xnas_pcaps`. Per-day completeness: `results/xnas_inventory/summary.md`.
- Weekend folders exist (e.g. 2025-02-01 is a Saturday); use weekdays.
- Missing piece for our study: IEX DEEP/DEEP+ for the same Feb–Apr 2025 dates (IEX HIST downloads are paused). Asked the professor.

## Strategy Studio
Shared install (owned by `vagrant`, **do not edit**): `/shared/ss/bt` (backtester) and `/shared/ss/sdk/RCM` (SDK).

| File | What it holds |
|---|---|
| `bt/backtester_config.txt` | `BACKTEST_SOURCE=TextTickReader`, `TEXT_TICK_COMPRESSED=true`, `TEXT_TICK_DIRECTORY=text_tick_data/`, feed config `./preferred_feeds.csv` |
| `bt/preferred_feeds.csv` | Market centers to load. Default: only `IEX,DEPTH,CONSOLIDATED`. For our project add a `NASDAQ` line in **your own copy** |
| `bt/text_tick_data` | Symlink to `/vagrant/iexdownloaderparser/data/text_tick_data` (shared) |
| `bt/db/strategy.db` | SQLite: fill simulator, fees, strategy instances |
| `bt/db/reference.db` | SQLite: instruments, market centers (NASDAQ = ID 663, MIC `XNAS`) |
| `bt/utilities/StrategyCommandLine` | CLI to create instances and run backtests; config in `cmd_config.txt` (server 127.0.0.1:13001, `RUN_MODE=1` = backtesting) |

**Fill simulator** (`strategy.db`, table `FillSimulatorParameters`), current shared defaults:

| Column | Value | Meaning |
|---|---|---|
| `latencyToExchange` | 0 | order → exchange latency (**units unconfirmed**; test by backtest) |
| `latencyFromExchange` | 0 | exchange → strategy latency |
| `excessSlippage` | 0.0 | extra slippage |
| `liquidityMultiplier` | 1.0 | fillable size = displayed size × this |
| `ignoreTradeTicks`, `waitToFillIfLockedCrossed`, `useTradeConditionsForAuctionSim`, `waitForNextTrade` | 0 | off |

Default latency is zero, which is the natural starting point of our latency sweep. Last year's group_06 set latency from the command line: `StrategyCommandLine cmd set_simulator_params -latency_to_exchange <value>`.

**Fees** (`strategy.db`, table `AccountFees`): `costPerContract = 0.0012` ($ per share), `salesFeesPercentageOfNotional = 2.24e-05` (sell-side regulatory fee), others 0. This is one venue-independent fee; venue-specific IEX vs. NASDAQ take fees will be handled in our evaluation code.

**Own copy:** last year each student ran Strategy Studio from `$HOME/ss/bt` (a copy of the shared install) and edited `backtester_config.txt` / `preferred_feeds.csv` there. Nobody on our team has set this up yet on this VM; note the 5 GB free on `/`.

## Open questions (sent to the professor)
1. IEX DEEP/DEEP+ for any Feb–Apr 2025 dates?
2. Where should students write large intermediate files?
