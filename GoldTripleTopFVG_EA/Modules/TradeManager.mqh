//+------------------------------------------------------------------+
//| TradeManager.mqh                                                 |
//| Trade Entry, Breakeven, Partial Close, Expiry, Exit Logic       |
//| Uses CTrade class — MQL5 only                                   |
//+------------------------------------------------------------------+
#pragma once
#include <Trade\Trade.mqh>
#include "Logger.mqh"
#include "RiskManager.mqh"

//--- Internal trade record for management
struct ManagedTrade
{
    ulong           ticket;
    double          entryPrice;
    double          stopLoss;
    double          takeProfit;
    double          initialRisk;        // |entry - SL|
    double          lotSize;
    double          originalLots;
    datetime        openTime;
    ENUM_SETUP_TYPE setupType;
    bool            beReached;          // True after SL moved to BE (1.5R)
    bool            partialClosed;      // True after 50% closed at 2.5R
    int             maxTradeHours;
    string          symbol;
    double          equityAtEntry;
    double          riskAmount;
};

#define MAX_MANAGED_TRADES 10

//+------------------------------------------------------------------+
//| CTradeManager class                                              |
//+------------------------------------------------------------------+
class CTradeManager
{
private:
    CTrade          m_trade;
    CRiskManager   *m_riskMgr;
    CLogger        *m_logger;

    string          m_symbol;
    int             m_magicNumber;
    int             m_maxSlippage;
    string          m_comment;
    int             m_maxTradeHours;
    double          m_targetRR;
    double          m_slBufferPips;
    double          m_pip;

    ManagedTrade    m_trades[MAX_MANAGED_TRADES];
    int             m_tradeCount;

public:
    //+----------------------------------------------------------------+
    //| Constructor                                                     |
    //+----------------------------------------------------------------+
    CTradeManager(void) : m_tradeCount(0)
    {}

    //+----------------------------------------------------------------+
    //| Init                                                            |
    //+----------------------------------------------------------------+
    void Init(const string symbol, const int magic,
              const int maxSlippage, const string comment,
              const int maxTradeHours, const double targetRR,
              const double slBufferPips,
              CRiskManager *riskMgr, CLogger *logger)
    {
        m_symbol        = symbol;
        m_magicNumber   = magic;
        m_maxSlippage   = maxSlippage;
        m_comment       = comment;
        m_maxTradeHours = maxTradeHours;
        m_targetRR      = targetRR;
        m_slBufferPips  = slBufferPips;
        m_riskMgr       = riskMgr;
        m_logger        = logger;
        m_pip           = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10.0;

        m_trade.SetExpertMagicNumber(magic);
        m_trade.SetDeviationInPoints((ulong)maxSlippage);
        m_trade.SetTypeFilling(ORDER_FILLING_IOC);
        m_trade.LogLevel(LOG_LEVEL_ERRORS);
    }

    //+----------------------------------------------------------------+
    //| OpenSell                                                        |
    //| Opens a sell order with full risk sizing and logging           |
    //| Returns ticket or 0 on failure                                 |
    //+----------------------------------------------------------------+
    ulong OpenSell(const double stopLoss, const double takeProfit,
                   const ENUM_SETUP_TYPE setupType,
                   const bool isConfluence = false)
    {
        if(IsTradeContextBusy())
        {
            Print("[TradeManager] Trade context busy — skipping entry.");
            return 0;
        }

        double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
        if(ask <= 0.0 || bid <= 0.0) return 0;

        double entry = bid; // Sell at bid

        double lots = m_riskMgr->CalculateLotSize(m_symbol, entry, stopLoss, isConfluence);
        if(lots <= 0.0)
        {
            Print("[TradeManager] Invalid lot size calculated.");
            return 0;
        }

        // Normalize SL and TP to symbol digits
        int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
        double sl  = NormalizeDouble(stopLoss,  digits);
        double tp  = NormalizeDouble(takeProfit, digits);

        string fullComment = m_comment + "_" + CLogger::SetupTypeToString(setupType);

        bool result = m_trade.Sell(lots, m_symbol, bid, sl, tp, fullComment);

        if(!result)
        {
            int err = (int)m_trade.ResultRetcode();
            Print("[TradeManager] Sell failed. Code: ", err,
                  " | Desc: ", m_trade.ResultRetcodeDescription());
            return 0;
        }

        ulong ticket = m_trade.ResultOrder();
        if(ticket == 0) ticket = m_trade.ResultDeal();

        // Register managed trade
        if(m_tradeCount < MAX_MANAGED_TRADES)
        {
            ManagedTrade mt;
            mt.ticket        = ticket;
            mt.entryPrice    = m_trade.ResultPrice() > 0 ? m_trade.ResultPrice() : bid;
            mt.stopLoss      = sl;
            mt.takeProfit    = tp;
            mt.initialRisk   = MathAbs(mt.entryPrice - sl);
            mt.lotSize       = lots;
            mt.originalLots  = lots;
            mt.openTime      = TimeCurrent();
            mt.setupType     = setupType;
            mt.beReached     = false;
            mt.partialClosed = false;
            mt.maxTradeHours = m_maxTradeHours;
            mt.symbol        = m_symbol;
            mt.equityAtEntry = AccountInfoDouble(ACCOUNT_EQUITY);
            mt.riskAmount    = AccountInfoDouble(ACCOUNT_BALANCE)
                               * (m_riskMgr->GetDailyPnL() + 0.0); // placeholder

            m_trades[m_tradeCount] = mt;
            m_tradeCount++;

            // Log open
            TradeLogRecord logRec;
            logRec.ticket       = ticket;
            logRec.openTime     = mt.openTime;
            logRec.symbol       = m_symbol;
            logRec.tradeType    = "SELL";
            logRec.entryPrice   = mt.entryPrice;
            logRec.slPrice      = sl;
            logRec.tpPrice      = tp;
            logRec.lotSize      = lots;
            logRec.riskAmount   = lots * mt.initialRisk
                                  * SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE)
                                  / SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
            logRec.setupType    = setupType;
            logRec.dailyPnL     = m_riskMgr->GetDailyPnL();
            logRec.equityAtEntry = mt.equityAtEntry;

            m_logger->LogTradeOpen(logRec);
        }

        return ticket;
    }

    //+----------------------------------------------------------------+
    //| OpenSellLimit                                                   |
    //| Places a sell limit order at limitPrice (retest entry)        |
    //+----------------------------------------------------------------+
    ulong OpenSellLimit(const double limitPrice,
                        const double stopLoss, const double takeProfit,
                        const ENUM_SETUP_TYPE setupType,
                        const bool isConfluence = false)
    {
        if(IsTradeContextBusy()) return 0;

        double lots = m_riskMgr->CalculateLotSize(m_symbol, limitPrice, stopLoss, isConfluence);
        if(lots <= 0.0) return 0;

        int    digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
        double sl     = NormalizeDouble(stopLoss,   digits);
        double tp     = NormalizeDouble(takeProfit,  digits);
        double lp     = NormalizeDouble(limitPrice,  digits);

        string fullComment = m_comment + "_" + CLogger::SetupTypeToString(setupType) + "_LIMIT";

        bool result = m_trade.SellLimit(lots, lp, m_symbol, sl, tp,
                                        ORDER_TIME_GTC, 0, fullComment);

        if(!result)
        {
            Print("[TradeManager] SellLimit failed. Code: ",
                  m_trade.ResultRetcode());
            return 0;
        }

        return m_trade.ResultOrder();
    }

    //+----------------------------------------------------------------+
    //| ManageTrades — call every tick                                 |
    //| Handles: BE at 1.5R, partial close at 2.5R, time expiry,     |
    //|          full TP close confirmation                            |
    //+----------------------------------------------------------------+
    void ManageTrades()
    {
        for(int i = m_tradeCount - 1; i >= 0; i--)
        {
            ManagedTrade &mt = m_trades[i];

            // Verify position still open
            if(!PositionSelectByTicket(mt.ticket))
            {
                // Position closed — log it and remove
                OnTradeClosed(i);
                continue;
            }

            double bid       = SymbolInfoDouble(m_symbol, SYMBOL_BID);
            double profit    = mt.entryPrice - bid; // positive = in profit for sell
            double rMultiple = (mt.initialRisk > 0.0) ? profit / mt.initialRisk : 0.0;

            // --- Time expiry check ---
            long hoursOpen = (long)((TimeCurrent() - mt.openTime) / 3600);
            if(hoursOpen >= mt.maxTradeHours)
            {
                ClosePosition(mt.ticket, "MaxTradeHours expiry");
                RemoveTrade(i);
                continue;
            }

            // --- Breakeven at 1.5R ---
            if(!mt.beReached && rMultiple >= 1.5)
            {
                double newSL = mt.entryPrice; // Move SL to entry (BE)
                int digits   = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
                newSL        = NormalizeDouble(newSL, digits);

                if(ModifyStopLoss(mt.ticket, newSL))
                {
                    mt.beReached = true;
                    mt.stopLoss  = newSL;
                    Print("[TradeManager] Ticket ", mt.ticket,
                          " — SL moved to breakeven @ ", DoubleToString(newSL, digits));
                }
            }

            // --- Partial close at 2.5R ---
            if(!mt.partialClosed && rMultiple >= 2.5)
            {
                double halfLots = NormalizeDouble(mt.originalLots * 0.5, 2);
                double minLot   = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
                if(halfLots >= minLot)
                {
                    if(PartialClose(mt.ticket, halfLots))
                    {
                        mt.partialClosed = true;
                        mt.lotSize       = mt.originalLots - halfLots;
                        Print("[TradeManager] Ticket ", mt.ticket,
                              " — Partial close ", DoubleToString(halfLots, 2),
                              " lots at 2.5R");
                    }
                }
                else
                {
                    // Lots too small to split — just close all
                    ClosePosition(mt.ticket, "2.5R full close (min lot constraint)");
                    RemoveTrade(i);
                    continue;
                }
            }

            // --- Full TP at 5R ---
            if(rMultiple >= m_targetRR)
            {
                ClosePosition(mt.ticket, "Target R reached");
                RemoveTrade(i);
                continue;
            }
        }
    }

    //+----------------------------------------------------------------+
    //| CloseAllPositions — used by daily kill switch                  |
    //+----------------------------------------------------------------+
    void CloseAllPositions(const string reason)
    {
        for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
            ulong ticket = PositionGetTicket(i);
            if(ticket == 0) continue;
            if(PositionGetInteger(POSITION_MAGIC) != m_magicNumber) continue;
            if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

            ClosePosition(ticket, reason);
        }
        m_tradeCount = 0;
    }

    //+----------------------------------------------------------------+
    //| GetTradeCount                                                   |
    //+----------------------------------------------------------------+
    int GetTradeCount() const { return m_tradeCount; }

private:
    //+----------------------------------------------------------------+
    //| ClosePosition                                                   |
    //+----------------------------------------------------------------+
    bool ClosePosition(const ulong ticket, const string reason)
    {
        if(!PositionSelectByTicket(ticket)) return false;
        if(IsTradeContextBusy())            return false;

        bool ok = m_trade.PositionClose(ticket, m_maxSlippage);
        if(!ok)
        {
            Print("[TradeManager] Failed to close ticket ", ticket,
                  " Reason: ", reason,
                  " Error: ", m_trade.ResultRetcode());
        }
        else
        {
            Print("[TradeManager] Closed ticket ", ticket, " | Reason: ", reason);
        }
        return ok;
    }

    //+----------------------------------------------------------------+
    //| PartialClose                                                    |
    //+----------------------------------------------------------------+
    bool PartialClose(const ulong ticket, const double lots)
    {
        if(!PositionSelectByTicket(ticket)) return false;
        if(IsTradeContextBusy())            return false;

        return m_trade.PositionClosePartial(ticket, lots, m_maxSlippage);
    }

    //+----------------------------------------------------------------+
    //| ModifyStopLoss                                                  |
    //+----------------------------------------------------------------+
    bool ModifyStopLoss(const ulong ticket, const double newSL)
    {
        if(!PositionSelectByTicket(ticket)) return false;
        if(IsTradeContextBusy())            return false;

        double tp = PositionGetDouble(POSITION_TP);
        return m_trade.PositionModify(ticket, newSL, tp);
    }

    //+----------------------------------------------------------------+
    //| OnTradeClosed — called when position disappears from tracker   |
    //+----------------------------------------------------------------+
    void OnTradeClosed(const int index)
    {
        ManagedTrade &mt = m_trades[index];

        // Try to get history deal info
        if(HistorySelectByPosition(mt.ticket))
        {
            int total = HistoryDealsTotal();
            for(int d = total - 1; d >= 0; d--)
            {
                ulong deal = HistoryDealGetTicket(d);
                if(HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_OUT ||
                   HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_OUT_BY)
                {
                    double closePrice = HistoryDealGetDouble(deal, DEAL_PRICE);
                    double pnl        = HistoryDealGetDouble(deal, DEAL_PROFIT)
                                       + HistoryDealGetDouble(deal, DEAL_SWAP)
                                       + HistoryDealGetDouble(deal, DEAL_COMMISSION);
                    double rMult      = (mt.initialRisk > 0.0)
                                        ? (mt.entryPrice - closePrice) / mt.initialRisk
                                        : 0.0;

                    TradeLogRecord logRec;
                    logRec.ticket       = mt.ticket;
                    logRec.openTime     = mt.openTime;
                    logRec.symbol       = mt.symbol;
                    logRec.tradeType    = "SELL";
                    logRec.entryPrice   = mt.entryPrice;
                    logRec.slPrice      = mt.stopLoss;
                    logRec.tpPrice      = mt.takeProfit;
                    logRec.lotSize      = mt.lotSize;
                    logRec.riskAmount   = 0.0;
                    logRec.setupType    = mt.setupType;
                    logRec.closePrice   = closePrice;
                    logRec.closeTime    = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
                    logRec.pnl          = pnl;
                    logRec.rMultiple    = rMult;
                    logRec.dailyPnL     = m_riskMgr->GetDailyPnL();
                    logRec.equityAtEntry = mt.equityAtEntry;

                    m_logger->LogTradeClose(logRec);
                    break;
                }
            }
        }

        RemoveTrade(index);
    }

    //+----------------------------------------------------------------+
    //| RemoveTrade — removes trade at index from managed array        |
    //+----------------------------------------------------------------+
    void RemoveTrade(const int index)
    {
        if(index < 0 || index >= m_tradeCount) return;
        for(int i = index; i < m_tradeCount - 1; i++)
            m_trades[i] = m_trades[i + 1];
        m_tradeCount--;
    }
};
