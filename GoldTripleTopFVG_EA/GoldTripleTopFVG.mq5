//+------------------------------------------------------------------+
//| GoldTripleTopFVG.mq5                                             |
//| Gold Triple Top + Fair Value Gap Expert Advisor                  |
//| Platform: MetaTrader 5 | Asset: XAUUSD/GC=F                     |
//| Strategy: Identifies Triple Top formations + FVG confluence      |
//|           entries on M15/H1 with H4 trend filter                 |
//|                                                                  |
//| Backtest Config:                                                 |
//|   Symbol:   XAUUSD                                               |
//|   TF:       M15                                                  |
//|   Period:   2023.01.01 – 2026.04.09                              |
//|   Model:    Every tick based on real ticks                       |
//|   Deposit:  $10,000 | Leverage: 1:100                           |
//|   Optimize: TripleTopTolerance, SLBufferPips, RiskPercent,TargetRR|
//+------------------------------------------------------------------+
#property copyright "GoldBot EA v1.0"
#property version   "1.00"
#property strict

#include "Modules\MarketStructure.mqh"
#include "Modules\TripleTopDetector.mqh"
#include "Modules\FVGDetector.mqh"
#include "Modules\RiskManager.mqh"
#include "Modules\TradeManager.mqh"
#include "Modules\Logger.mqh"

//============================================================
//  INPUT PARAMETERS
//============================================================

//--- Triple Top Settings
input group "=== Triple Top Settings ==="
input double TripleTopTolerance  = 0.003;   // Top price tolerance (0.3%)
input int    MinBarsBetweenTops  = 5;       // Min bars between swing highs
input int    MaxBarsBetweenTops  = 50;      // Max bars between swing highs
input int    LookbackBars        = 200;     // Bars to scan for patterns
input bool   UseRetestEntry      = true;    // true=wait for neckline retest, false=break entry
input double SLBufferPips        = 15.0;    // SL buffer above triple top high (pips)

//--- FVG Settings
input group "=== FVG Settings ==="
input bool   EnableFVG           = true;    // Enable Fair Value Gap module
input bool   FVGTimeframeM15     = true;    // Scan M15 for FVGs
input bool   FVGTimeframeH1      = true;    // Scan H1 for FVGs
input bool   UseMidFVGEntry      = true;    // Enter at 50% midpoint of FVG
input int    FVGMaxAgeHours      = 48;      // Invalidate FVGs older than X hours

//--- Risk Management
input group "=== Risk Management ==="
input double RiskPercent         = 0.5;     // % of account risked per trade
input double MaxDailyRiskPercent = 2.0;     // Max daily loss % before shutdown
input double MaxDrawdownPercent  = 5.0;     // Max drawdown % before 24h pause
input int    MaxConcurrentTrades = 3;       // Max open positions at once
input double ConfluenceMultiplier = 1.5;    // Size multiplier for TT+FVG confluence
input double MaxRiskPerTrade     = 1.0;     // Hard cap per trade regardless of confluence
input int    MaxTradeHours       = 48;      // Close trades older than this (hours)
input double TargetRR            = 5.0;     // Target R:R ratio

//--- Filters
input group "=== Entry Filters ==="
input int    RSIPeriod           = 14;      // RSI period
input double RSIMaxEntry         = 65.0;    // Max RSI for short entry
input bool   UseVolumeFilter     = true;    // Volume on H3 < Volume on H1
input bool   UseTimeFilter       = true;    // Avoid news windows
input bool   RequireH4Bearish    = false;   // Only trade if H4 structure is bearish

//--- Execution
input group "=== Execution Settings ==="
input int    MagicNumber         = 20260409;
input string TradeComment        = "GoldTT_FVG";
input int    MaxSlippage         = 10;      // Max slippage in points
input bool   EnableAlerts        = true;    // Mobile push + terminal alerts
input bool   EnableCSVLog        = true;    // Log trades to CSV

//============================================================
//  GLOBAL OBJECTS
//============================================================
CTripleTopDetector  g_ttDetector;
CFVGDetector        g_fvgDetector;
CRiskManager        g_riskMgr;
CTradeManager       g_tradeMgr;
CLogger             g_logger;

//--- RSI indicator handle
int   g_rsiHandle       = INVALID_HANDLE;
bool  g_initialized     = false;
bool  g_firstTickDone   = false;
datetime g_lastBarTime  = 0;
string g_symbol;

//============================================================
//  NEWS / TIME FILTER WINDOWS (EST times stored as offsets)
//  7:25-7:35 AM, 8:25-8:35 AM, 1:55-2:05 PM EST
//  These correspond to pre/post major US data releases
//  Offset from midnight EST: adjust for broker's server time
//============================================================
struct NewsWindow
{
    int startMin; // Minutes from midnight (server time proxy)
    int endMin;
};

NewsWindow g_newsWindows[3];

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
    g_symbol = Symbol();

    // Validate symbol — must be XAUUSD family
    if(StringFind(g_symbol, "XAU") < 0 && StringFind(g_symbol, "GOLD") < 0
       && StringFind(g_symbol, "GC") < 0)
    {
        Print("[GoldBot] WARNING: Symbol ", g_symbol,
              " may not be XAUUSD. Verify settings.");
        // Not fatal — allow running for backtesting on any mapped symbol
    }

    // Initialize RSI handle on M15
    g_rsiHandle = iRSI(g_symbol, PERIOD_M15, RSIPeriod, PRICE_CLOSE);
    if(g_rsiHandle == INVALID_HANDLE)
    {
        Print("[GoldBot] ERROR: Failed to create RSI indicator. Error: ", GetLastError());
        return INIT_FAILED;
    }

    // Initialize modules
    if(!g_ttDetector.Init(g_symbol, PERIOD_M15,
                           TripleTopTolerance, MinBarsBetweenTops,
                           MaxBarsBetweenTops, LookbackBars, SLBufferPips))
    {
        Print("[GoldBot] TripleTopDetector init failed.");
        return INIT_FAILED;
    }

    if(!g_fvgDetector.Init(g_symbol,
                            FVGTimeframeM15, FVGTimeframeH1,
                            UseMidFVGEntry, FVGMaxAgeHours, 100))
    {
        Print("[GoldBot] FVGDetector init failed.");
        return INIT_FAILED;
    }

    g_riskMgr.Init(RiskPercent, MaxDailyRiskPercent, MaxDrawdownPercent,
                   MaxRiskPerTrade, ConfluenceMultiplier, MagicNumber);

    g_tradeMgr.Init(g_symbol, MagicNumber, MaxSlippage, TradeComment,
                    MaxTradeHours, TargetRR, SLBufferPips,
                    &g_riskMgr, &g_logger);

    if(!g_logger.Init(EnableCSVLog, EnableAlerts))
    {
        Print("[GoldBot] Logger init warning — CSV logging disabled.");
    }

    // News windows: approximate server time offsets
    // Most brokers run GMT+2 or GMT+3. EST = GMT-5.
    // We use simple hour:minute checks relative to server time.
    // User should verify server time offset in broker settings.
    // Default assumes GMT+3 server (EST+8):
    //   7:25 EST = 15:25 server | 8:25 EST = 16:25 server | 13:55 EST = 21:55 server
    g_newsWindows[0].startMin = 15 * 60 + 25;   // 15:25 server
    g_newsWindows[0].endMin   = 15 * 60 + 35;   // 15:35 server
    g_newsWindows[1].startMin = 16 * 60 + 25;   // 16:25 server
    g_newsWindows[1].endMin   = 16 * 60 + 35;   // 16:35 server
    g_newsWindows[2].startMin = 21 * 60 + 55;   // 21:55 server
    g_newsWindows[2].endMin   = 22 * 60 + 5;    // 22:05 server

    g_initialized   = true;
    g_firstTickDone = false;
    g_lastBarTime   = 0;

    Print("[GoldBot] Initialized successfully. Symbol: ", g_symbol,
          " | Magic: ", MagicNumber,
          " | Risk: ", RiskPercent, "%");

    Comment("[GoldBot v1.0] Running | ", g_symbol,
            " | Risk: ", DoubleToString(RiskPercent, 1), "%");

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    if(g_rsiHandle != INVALID_HANDLE)
    {
        IndicatorRelease(g_rsiHandle);
        g_rsiHandle = INVALID_HANDLE;
    }

    g_logger.Deinit();
    Comment("");
    Print("[GoldBot] Deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| OnTick — main execution loop                                     |
//+------------------------------------------------------------------+
void OnTick()
{
    if(!g_initialized) return;

    // Wait for first bar to close after EA attachment (anti-repainting)
    if(!g_firstTickDone)
    {
        g_lastBarTime  = iTime(g_symbol, PERIOD_M15, 1);
        g_firstTickDone = true;
        return;
    }

    // --- Update risk manager every tick ---
    g_riskMgr.Update();

    // --- Manage open trades every tick ---
    g_tradeMgr.ManageTrades();

    // --- Close all if daily kill active ---
    if(g_riskMgr.IsDailyKillActive())
    {
        g_tradeMgr.CloseAllPositions("Daily Kill Switch");
        return;
    }

    // --- Only scan for new setups on new bar ---
    datetime currentBar = iTime(g_symbol, PERIOD_M15, 1);
    if(currentBar == g_lastBarTime) return;
    g_lastBarTime = currentBar;

    // --- New bar processing ---
    if(!g_riskMgr.CanTrade())                           return;
    if(g_riskMgr.CountOpenTrades() >= MaxConcurrentTrades) return;
    if(UseTimeFilter && IsNewsTime())                    return;

    // H4 structure filter (optional)
    if(RequireH4Bearish && !IsH4Bearish(g_symbol))      return;

    // RSI filter
    double rsiValue = GetRSIValue();
    if(rsiValue < 0.0)                                   return;
    if(rsiValue > RSIMaxEntry)                           return;

    // --- Scan detectors ---
    g_ttDetector.Scan();

    if(EnableFVG)
        g_fvgDetector.Scan();

    // --- Evaluate Triple Top setups ---
    EvaluateTripleTopSetups();

    // --- Evaluate FVG setups ---
    if(EnableFVG)
        EvaluateFVGSetups();

    // Update chart comment
    UpdateComment(rsiValue);
}

//+------------------------------------------------------------------+
//| EvaluateTripleTopSetups                                          |
//| Checks all confirmed triple top patterns for trade entry         |
//+------------------------------------------------------------------+
void EvaluateTripleTopSetups()
{
    TripleTopPattern patterns[];
    int count = g_ttDetector.GetConfirmedPatterns(patterns);

    for(int i = 0; i < count; i++)
    {
        TripleTopPattern &pat = patterns[i];

        // Volume filter: H3 volume should be less than H1 volume (exhaustion)
        if(UseVolumeFilter && pat.h3Volume >= pat.h1Volume) continue;

        // Neckline break candle strength: body >= 50% of range
        if(!IsBreakCandleStrong(pat.confirmBar)) continue;

        // Check if neckline body close conviction was valid
        double entryPrice;
        double stopLoss;
        double takeProfit;
        bool   isRetest = false;

        if(UseRetestEntry)
        {
            // Wait for price to retest the neckline from below
            double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
            double nk  = pat.necklinePrice;
            double pip = SymbolInfoDouble(g_symbol, SYMBOL_POINT) * 10.0;

            // Price must be near neckline and coming from below
            // (bid is between neckline - 5pips and neckline + 2pips)
            if(bid < nk - 5.0 * pip || bid > nk + 2.0 * pip)
                continue;

            isRetest   = true;
            entryPrice = bid;
        }
        else
        {
            // Immediate break entry: use current market
            double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
            // Entry must be below neckline (confirmed we broke it)
            if(bid >= pat.necklinePrice) continue;
            entryPrice = bid;
        }

        stopLoss  = pat.stopLoss;
        double risk = MathAbs(entryPrice - stopLoss);
        if(risk <= 0.0) continue;
        takeProfit = entryPrice - TargetRR * risk;

        // Check confluence with any active FVG below neckline
        bool isConfluence = false;
        if(EnableFVG)
        {
            FVGZone fvgZones[];
            int fvgCount = g_fvgDetector.GetActiveZones(fvgZones);
            for(int f = 0; f < fvgCount; f++)
            {
                // FVG must be below neckline (in the breakdown zone)
                if(fvgZones[f].topPrice < pat.necklinePrice)
                {
                    isConfluence = true;
                    break;
                }
            }
        }

        // Execute entry
        ulong ticket = g_tradeMgr.OpenSell(stopLoss, takeProfit,
                                            isConfluence ? SETUP_CONFLUENCE : SETUP_TRIPLE_TOP,
                                            isConfluence);

        if(ticket > 0)
        {
            g_ttDetector.MarkPatternActive(pat.confirmTime);
            string msg = StringFormat(
                "[GoldBot] Triple Top SELL | Entry:%.2f SL:%.2f TP:%.2f | "
                "Confluence:%s | Ticket:%llu",
                entryPrice, stopLoss, takeProfit,
                isConfluence ? "YES" : "NO", ticket);
            Print(msg);
            if(EnableAlerts) Alert(msg);
            break; // One trade per bar
        }
    }
}

//+------------------------------------------------------------------+
//| EvaluateFVGSetups                                                |
//| Checks active bearish FVG zones for mid-point entry             |
//+------------------------------------------------------------------+
void EvaluateFVGSetups()
{
    FVGZone zones[];
    int count = g_fvgDetector.GetActiveZones(zones);

    for(int i = 0; i < count; i++)
    {
        FVGZone &z = zones[i];

        // Skip if trade already entered for this gap
        if(z.tradeEntered) continue;

        // Check if price is at/near midpoint
        bool atMid = g_fvgDetector.IsPriceAtMid(z);
        bool inZone = g_fvgDetector.IsPriceInZone(z);

        bool triggerEntry = UseMidFVGEntry ? atMid : inZone;
        if(!triggerEntry) continue;

        // Additional RSI filter for FVG entry
        double rsi = GetRSIValue();
        if(rsi > RSIMaxEntry || rsi < 0.0) continue;

        double entryPrice = SymbolInfoDouble(g_symbol, SYMBOL_BID);
        double stopLoss   = z.topPrice + SLBufferPips
                            * SymbolInfoDouble(g_symbol, SYMBOL_POINT) * 10.0;
        double risk       = MathAbs(entryPrice - stopLoss);
        if(risk <= 0.0) continue;
        double takeProfit = entryPrice - TargetRR * risk;

        ulong ticket = g_tradeMgr.OpenSell(stopLoss, takeProfit,
                                            SETUP_FVG, false);

        if(ticket > 0)
        {
            g_fvgDetector.MarkTradeEntered(z.zoneId);
            string msg = StringFormat(
                "[GoldBot] FVG SELL | Entry:%.2f SL:%.2f TP:%.2f | "
                "Zone:[%.2f-%.2f] | Ticket:%llu",
                entryPrice, stopLoss, takeProfit,
                z.botPrice, z.topPrice, ticket);
            Print(msg);
            if(EnableAlerts) Alert(msg);
            break;
        }
    }
}

//+------------------------------------------------------------------+
//| GetRSIValue                                                       |
//| Returns current RSI(14) on M15 bar[1] (confirmed close)         |
//| Returns -1.0 on failure                                          |
//+------------------------------------------------------------------+
double GetRSIValue()
{
    if(g_rsiHandle == INVALID_HANDLE) return -1.0;

    double buf[1];
    if(CopyBuffer(g_rsiHandle, 0, 1, 1, buf) != 1) return -1.0;
    return buf[0];
}

//+------------------------------------------------------------------+
//| IsNewsTime                                                        |
//| Returns true if current server time falls in a news window      |
//+------------------------------------------------------------------+
bool IsNewsTime()
{
    MqlDateTime dt;
    TimeToStruct(TimeCurrent(), dt);
    int minutesFromMidnight = dt.hour * 60 + dt.min;

    for(int i = 0; i < ArraySize(g_newsWindows); i++)
    {
        if(minutesFromMidnight >= g_newsWindows[i].startMin &&
           minutesFromMidnight <= g_newsWindows[i].endMin)
            return true;
    }
    return false;
}

//+------------------------------------------------------------------+
//| IsBreakCandleStrong                                              |
//| Returns true if the neckline break candle body >= 50% of range  |
//+------------------------------------------------------------------+
bool IsBreakCandleStrong(const int bar)
{
    if(bar <= 0) return false;

    double high  = iHigh(g_symbol,  PERIOD_M15, bar);
    double low   = iLow(g_symbol,   PERIOD_M15, bar);
    double open  = iOpen(g_symbol,  PERIOD_M15, bar);
    double close = iClose(g_symbol, PERIOD_M15, bar);

    double range = high - low;
    if(range <= 0.0) return false;

    double body = MathAbs(close - open);
    return (body / range >= 0.50);
}

//+------------------------------------------------------------------+
//| UpdateComment — dashboard display on chart                       |
//+------------------------------------------------------------------+
void UpdateComment(const double rsi)
{
    double eq      = AccountInfoDouble(ACCOUNT_EQUITY);
    double bal     = AccountInfoDouble(ACCOUNT_BALANCE);
    double ddPct   = g_riskMgr.GetCurrentDrawdownPct();
    int    trades  = g_riskMgr.CountOpenTrades();
    double dpnl    = g_riskMgr.GetDailyPnL();

    string status = g_riskMgr.IsDailyKillActive()  ? "DAILY KILL"   :
                    g_riskMgr.IsDrawdownPaused()    ? "DD PAUSE"     : "ACTIVE";

    string msg = StringFormat(
        "[GoldBot v1.0] %s | %s\n"
        "Equity: $%.2f | Balance: $%.2f\n"
        "DD: %.2f%% | DailyPnL: $%.2f\n"
        "OpenTrades: %d/%d | RSI(14)M15: %.1f\n"
        "TT Patterns: %d | FVG Zones: %d",
        g_symbol, status,
        eq, bal,
        ddPct, dpnl,
        trades, MaxConcurrentTrades, rsi,
        g_ttDetector.GetPatternCount(),
        g_fvgDetector.GetZoneCount());

    Comment(msg);
}

//+------------------------------------------------------------------+
//| OnTradeTransaction — sync managed trades on external closes     |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,
                        const MqlTradeResult      &result)
{
    // Position fully closed externally → TradeManager handles via PositionSelectByTicket
    // No action needed here — ManageTrades() detects missing positions each tick
}
