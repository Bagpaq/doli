# Gold Triple Top + FVG Expert Advisor

**Platform:** MetaTrader 5 (MQL5)  
**Asset:** XAUUSD / GC=F (Gold Spot / Futures)  
**Strategy:** Triple Top Pattern + Fair Value Gap confluence entries  
**Version:** 1.0

---

## Strategy Overview

The EA identifies **Triple Top** reversal patterns combined with **Fair Value Gap (FVG)** imbalance zones to enter short trades on Gold with a 5R target.

### Triple Top Logic
- Scans for 3 swing highs within a configurable tolerance band (default 0.3%)
- Requires minimum 5 and maximum 50 bars between each high
- Neckline = lowest low between the three highs
- **Entry trigger:** Price closes BELOW the neckline (no anticipatory entries)
- Optional retest entry: wait for price to return to neckline from below

### FVG Logic
- Bearish FVG: Candle 3's high < Candle 1's low (downward price gap)
- Scans M15 and H1 timeframes
- Entry at the 50% midpoint of the gap (default) for best R:R
- Zones expire after 48 hours or when fully filled

### Confluence
When a bearish FVG sits below a confirmed Triple Top neckline, position size increases by the `ConfluenceMultiplier` (default 1.5×, capped at `MaxRiskPerTrade`).

---

## File Structure

```
GoldTripleTopFVG_EA/
├── GoldTripleTopFVG.mq5          ← Main EA file
└── Modules/
    ├── MarketStructure.mqh       ← Swing high/low detection
    ├── TripleTopDetector.mqh     ← Triple top pattern engine
    ├── FVGDetector.mqh           ← FVG zone detection & management
    ├── RiskManager.mqh           ← Position sizing, kill switches
    ├── TradeManager.mqh          ← Entry, BE, partial close, expiry
    └── Logger.mqh                ← CSV + terminal logging
```

---

## Installation

1. Open MetaTrader 5
2. Go to **File → Open Data Folder → MQL5 → Experts**
3. Copy the entire `GoldTripleTopFVG_EA/` folder into `Experts/`
4. In MT5, press **F5** or right-click `Experts` → **Refresh**
5. Drag the EA onto an **XAUUSD M15** chart
6. Enable **Algo Trading** (the play button in the toolbar)

### Required Modules
The `Modules/` folder must be placed inside the EA folder. The `#include` paths use relative references — keep the directory structure intact.

---

## Recommended Broker Settings

| Setting | Value |
|---|---|
| Symbol | XAUUSD (5-digit, e.g. 1.23456) |
| Timeframe | M15 (primary execution) |
| Spread | < 50 points ($0.50) recommended |
| Leverage | 1:100 to 1:500 |
| Account type | ECN/STP preferred |
| GMT offset | Configure news windows to match broker server time |

> **Important:** The default news window times assume a **GMT+3 broker server**. If your broker uses a different timezone, adjust the `g_newsWindows` values in `OnInit()` of the main `.mq5` file.

---

## Input Parameters

### Triple Top Settings
| Parameter | Default | Description |
|---|---|---|
| `TripleTopTolerance` | 0.003 | Tolerance for top price alignment (0.3%) |
| `MinBarsBetweenTops` | 5 | Minimum bars separating swing highs |
| `MaxBarsBetweenTops` | 50 | Maximum bars separating swing highs |
| `LookbackBars` | 200 | How far back to scan for patterns |
| `UseRetestEntry` | true | Wait for neckline retest vs immediate break |
| `SLBufferPips` | 15 | Buffer above triple top high for SL |

### FVG Settings
| Parameter | Default | Description |
|---|---|---|
| `EnableFVG` | true | Enable FVG module |
| `FVGTimeframeM15` | true | Scan M15 timeframe |
| `FVGTimeframeH1` | true | Scan H1 timeframe |
| `UseMidFVGEntry` | true | Enter at 50% of FVG (better R:R) |
| `FVGMaxAgeHours` | 48 | Expire FVGs older than this |

### Risk Management
| Parameter | Default | Description |
|---|---|---|
| `RiskPercent` | 0.5 | % of account per trade |
| `MaxDailyRiskPercent` | 2.0 | Daily loss limit before EA shutdown |
| `MaxDrawdownPercent` | 5.0 | Drawdown % triggering 24h pause |
| `MaxConcurrentTrades` | 3 | Max open positions |
| `ConfluenceMultiplier` | 1.5 | Size multiplier for TT+FVG confluence |
| `MaxRiskPerTrade` | 1.0 | Hard cap per trade (% account) |
| `MaxTradeHours` | 48 | Force-close trades after this many hours |
| `TargetRR` | 5.0 | Take profit target in R multiples |

### Filters
| Parameter | Default | Description |
|---|---|---|
| `RSIPeriod` | 14 | RSI calculation period |
| `RSIMaxEntry` | 65.0 | Max RSI value at entry (reversal filter) |
| `UseVolumeFilter` | true | Require H3 volume < H1 volume |
| `UseTimeFilter` | true | Skip trades during news windows |
| `RequireH4Bearish` | false | Only trade when H4 shows lower highs/lows |

---

## Trade Management Rules

| Event | Action |
|---|---|
| 1.5R profit reached | Move SL to breakeven |
| 2.5R profit reached | Close 50% of position, remainder runs |
| 5.0R profit reached | Close 100% |
| Daily loss ≥ 2% account | Close all positions, pause until midnight |
| Drawdown ≥ 5% from peak | Pause new entries for 24 hours |
| Trade open ≥ 48 hours | Close at market regardless of P&L |

---

## Backtesting Configuration

```
Symbol:         XAUUSD
Timeframe:      M15
Period:         2023.01.01 – 2026.04.09
Model:          Every tick based on real ticks
Initial Deposit: $10,000
Leverage:       1:100
Spread:         Current (or fixed 30 points)
```

### Optimization Parameters (in order of priority)
1. `TripleTopTolerance` → 0.001 to 0.005, step 0.0005
2. `SLBufferPips` → 10 to 30, step 5
3. `RiskPercent` → 0.25 to 1.0, step 0.25
4. `TargetRR` → 3.0 to 7.0, step 0.5
5. `MinBarsBetweenTops` → 3 to 10, step 1

---

## CSV Log Output

Trades are logged to `MQL5/Files/GoldBot_Trades_YYYYMMDD.csv`

Columns:
```
DateTime, Symbol, Type, EntryPrice, SLPrice, TPPrice,
LotSize, RiskAmount, SetupType, ClosePrice, CloseTime,
PnL, RMultiple, DailyPnL, EquityAtEntry, Ticket
```

---

## Gold-Specific Calibration

| Factor | Value |
|---|---|
| Pip value (standard lot) | $1.00 per pip |
| Typical daily range | $20–$80 normal, $100–200 news days |
| Typical spread | 20–50 points |
| Minimum SL buffer | 15 pips normal, 25 pips high volatility |
| Settlement/rollover | Check futures expiry dates (GC=F: ~quarterly) |

---

## Safety Rules

- **No martingale** — never increases losing position size
- **No grid** — no multiple entries in same direction without new setup
- **No averaging down** — never adds to losing positions
- **No look-ahead bias** — all pattern detection uses confirmed closed bars
- **No repainting** — swing detection requires `rightBars` confirmed bars after peak
- **State machine** — no `Sleep()` or blocking `while()` loops in `OnTick()`

---

## Known Limitations

1. **Futures rollover:** For GC=F futures, the EA does not auto-detect contract expiry. Monitor settlement dates manually (typically 3rd last business day of the delivery month).
2. **Server time offset:** News filter windows default to GMT+3. Adjust for your broker.
3. **H4 filter:** `RequireH4Bearish` defaults to `false` because Gold's mega bull trend (2020-2026 +171%) means H4 is often bullish even at local tops. Enable selectively.
4. **Spread on high-volatility days:** On major news (NFP, FOMC), gold spreads can widen to 100–200+ points. The EA's `MaxSlippage` setting provides some protection, but manual monitoring is recommended.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-04-09 | Initial release — Triple Top + FVG + full risk management |
