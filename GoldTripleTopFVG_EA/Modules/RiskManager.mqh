//+------------------------------------------------------------------+
//| RiskManager.mqh                                                  |
//| Position Sizing, Daily Kill Switch, Drawdown Protection          |
//| All risk calculations use LIVE account data                      |
//+------------------------------------------------------------------+
#pragma once

//+------------------------------------------------------------------+
//| CRiskManager class                                               |
//+------------------------------------------------------------------+
class CRiskManager
{
private:
    // Parameters
    double  m_riskPercent;         // % per trade
    double  m_maxDailyRiskPercent; // Daily stop
    double  m_maxDrawdownPercent;  // Weekly drawdown pause
    double  m_maxRiskPerTrade;     // Hard cap per trade %
    double  m_confluenceMultiplier;
    int     m_magicNumber;

    // State
    double  m_dailyStartBalance;   // Balance at start of trading day
    double  m_dailyPnL;            // Realized + unrealized P&L today
    double  m_peakEquity;          // Highest equity recorded since EA start
    bool    m_dailyKillActive;     // True = no new trades today
    bool    m_drawdownPauseActive; // True = paused for 24h
    datetime m_drawdownPauseUntil; // When 24h pause expires
    datetime m_lastDayCheck;       // For daily reset detection

public:
    //+----------------------------------------------------------------+
    //| Constructor                                                     |
    //+----------------------------------------------------------------+
    CRiskManager(void) : m_dailyKillActive(false),
                         m_drawdownPauseActive(false),
                         m_drawdownPauseUntil(0),
                         m_lastDayCheck(0),
                         m_peakEquity(0.0),
                         m_dailyPnL(0.0)
    {}

    //+----------------------------------------------------------------+
    //| Init                                                            |
    //+----------------------------------------------------------------+
    void Init(const double riskPct,    const double maxDailyRiskPct,
              const double maxDDPct,   const double maxRiskPerTrade,
              const double confluenceMult, const int magic)
    {
        m_riskPercent          = riskPct;
        m_maxDailyRiskPercent  = maxDailyRiskPct;
        m_maxDrawdownPercent   = maxDDPct;
        m_maxRiskPerTrade      = maxRiskPerTrade;
        m_confluenceMultiplier = confluenceMult;
        m_magicNumber          = magic;

        m_peakEquity         = AccountInfoDouble(ACCOUNT_EQUITY);
        m_dailyStartBalance  = AccountInfoDouble(ACCOUNT_BALANCE);
        m_lastDayCheck       = TimeCurrent();
    }

    //+----------------------------------------------------------------+
    //| Update — call every tick                                       |
    //| Checks daily reset, updates PnL, checks kill conditions       |
    //+----------------------------------------------------------------+
    void Update()
    {
        // Check for new trading day (midnight roll)
        MqlDateTime now;
        TimeToStruct(TimeCurrent(), now);

        MqlDateTime last;
        TimeToStruct(m_lastDayCheck, last);

        if(now.day != last.day || now.mon != last.mon)
        {
            // New day — reset daily trackers
            m_dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
            m_dailyPnL          = 0.0;
            m_dailyKillActive   = false;
            m_lastDayCheck      = TimeCurrent();
            Print("[RiskManager] New trading day — daily risk reset.");
        }

        // Update peak equity
        double eq = AccountInfoDouble(ACCOUNT_EQUITY);
        if(eq > m_peakEquity)
            m_peakEquity = eq;

        // Update daily PnL: equity minus start balance (includes open trades)
        m_dailyPnL = eq - m_dailyStartBalance;

        // Check drawdown pause expiry
        if(m_drawdownPauseActive && TimeCurrent() >= m_drawdownPauseUntil)
        {
            m_drawdownPauseActive = false;
            Print("[RiskManager] Drawdown pause expired — resuming normal operation.");
        }

        // Daily kill switch check
        double dailyLossLimit = -(m_dailyStartBalance * m_maxDailyRiskPercent / 100.0);
        if(!m_dailyKillActive && m_dailyPnL <= dailyLossLimit)
        {
            m_dailyKillActive = true;
            Print("[RiskManager] DAILY KILL SWITCH TRIGGERED. DailyPnL: ",
                  DoubleToString(m_dailyPnL, 2),
                  " | Limit: ", DoubleToString(dailyLossLimit, 2));
            Alert("[GoldBot] DAILY KILL SWITCH — Daily loss limit reached! EA in observe mode.");
        }

        // Drawdown protection check
        if(!m_drawdownPauseActive && m_peakEquity > 0.0)
        {
            double drawdownPct = (m_peakEquity - eq) / m_peakEquity * 100.0;
            if(drawdownPct >= m_maxDrawdownPercent)
            {
                m_drawdownPauseActive = true;
                m_drawdownPauseUntil  = TimeCurrent() + 86400; // 24h
                Print("[RiskManager] DRAWDOWN PROTECTION TRIGGERED. DrawdownPct: ",
                      DoubleToString(drawdownPct, 2), "% | Paused for 24h.");
                Alert("[GoldBot] DRAWDOWN LIMIT — EA paused for 24 hours.");
            }
        }
    }

    //+----------------------------------------------------------------+
    //| IsDailyKillActive                                               |
    //+----------------------------------------------------------------+
    bool IsDailyKillActive() const { return m_dailyKillActive; }

    //+----------------------------------------------------------------+
    //| IsDrawdownPaused                                                |
    //+----------------------------------------------------------------+
    bool IsDrawdownPaused() const { return m_drawdownPauseActive; }

    //+----------------------------------------------------------------+
    //| CanTrade — returns false if any kill/pause is active           |
    //+----------------------------------------------------------------+
    bool CanTrade() const
    {
        return (!m_dailyKillActive && !m_drawdownPauseActive);
    }

    //+----------------------------------------------------------------+
    //| CalculateLotSize                                                |
    //| Params:                                                         |
    //|   entryPrice   — intended entry price                          |
    //|   stopLoss     — stop loss price                               |
    //|   isConfluence — if true, applies confluenceMultiplier         |
    //| Returns: normalized lot size clamped to symbol limits          |
    //+----------------------------------------------------------------+
    double CalculateLotSize(const string symbol,
                            const double entryPrice,
                            const double stopLoss,
                            const bool   isConfluence = false)
    {
        double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
        double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
        double tickVal  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);

        if(tickSize <= 0.0 || tickVal <= 0.0) return 0.0;

        double pip      = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10.0;
        double riskPct  = m_riskPercent;

        if(isConfluence)
        {
            riskPct *= m_confluenceMultiplier;
            riskPct  = MathMin(riskPct, m_maxRiskPerTrade); // Hard cap
        }

        double riskAmount  = balance * (riskPct / 100.0);
        double priceDiff   = MathAbs(entryPrice - stopLoss);
        if(priceDiff < pip) priceDiff = pip; // Minimum 1 pip

        // Value per lot per 1 unit price move
        double pointsRisk    = priceDiff / tickSize;
        double valuePerLot   = pointsRisk * tickVal;
        if(valuePerLot <= 0.0) return 0.0;

        double lotSize = riskAmount / valuePerLot;

        // Clamp to symbol limits
        double minLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
        double maxLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
        double lotStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

        if(lotStep > 0.0)
            lotSize = MathFloor(lotSize / lotStep) * lotStep;

        lotSize = MathMax(minLot, MathMin(maxLot, lotSize));

        return NormalizeDouble(lotSize, 2);
    }

    //+----------------------------------------------------------------+
    //| GetDailyPnL                                                     |
    //+----------------------------------------------------------------+
    double GetDailyPnL()    const { return m_dailyPnL; }

    //+----------------------------------------------------------------+
    //| GetPeakEquity                                                   |
    //+----------------------------------------------------------------+
    double GetPeakEquity()  const { return m_peakEquity; }

    //+----------------------------------------------------------------+
    //| GetCurrentDrawdownPct                                           |
    //+----------------------------------------------------------------+
    double GetCurrentDrawdownPct() const
    {
        double eq = AccountInfoDouble(ACCOUNT_EQUITY);
        if(m_peakEquity <= 0.0) return 0.0;
        return (m_peakEquity - eq) / m_peakEquity * 100.0;
    }

    //+----------------------------------------------------------------+
    //| CountOpenTrades — counts EA's own open positions               |
    //+----------------------------------------------------------------+
    int CountOpenTrades() const
    {
        int count = 0;
        for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
            ulong ticket = PositionGetTicket(i);
            if(ticket == 0) continue;
            if(PositionGetInteger(POSITION_MAGIC) == m_magicNumber)
                count++;
        }
        return count;
    }

    //+----------------------------------------------------------------+
    //| GetOpenTradesBySymbol                                           |
    //+----------------------------------------------------------------+
    int CountOpenTradesBySymbol(const string symbol) const
    {
        int count = 0;
        for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
            ulong ticket = PositionGetTicket(i);
            if(ticket == 0) continue;
            if(PositionGetInteger(POSITION_MAGIC) != m_magicNumber) continue;
            if(PositionGetString(POSITION_SYMBOL) != symbol) continue;
            count++;
        }
        return count;
    }
};
