//+------------------------------------------------------------------+
//| Logger.mqh                                                       |
//| Trade Logging to CSV + Terminal output                          |
//| Writes: DateTime,Symbol,Type,Entry,SL,TP,Lots,Risk,Setup,       |
//|         ClosePrice,CloseTime,PnL,RMultiple,DailyPnL,Equity     |
//+------------------------------------------------------------------+
#pragma once

//--- Setup type identifier
enum ENUM_SETUP_TYPE
{
    SETUP_TRIPLE_TOP  = 0,
    SETUP_FVG         = 1,
    SETUP_CONFLUENCE  = 2
};

//--- Trade log record
struct TradeLogRecord
{
    datetime        openTime;
    string          symbol;
    string          tradeType;    // "SELL"
    double          entryPrice;
    double          slPrice;
    double          tpPrice;
    double          lotSize;
    double          riskAmount;
    ENUM_SETUP_TYPE setupType;
    double          closePrice;
    datetime        closeTime;
    double          pnl;
    double          rMultiple;
    double          dailyPnL;
    double          equityAtEntry;
    ulong           ticket;
};

//+------------------------------------------------------------------+
//| CLogger class                                                    |
//+------------------------------------------------------------------+
class CLogger
{
private:
    string  m_logFilePath;
    bool    m_enableCSV;
    bool    m_enableAlerts;
    int     m_fileHandle;
    bool    m_headerWritten;

public:
    //+----------------------------------------------------------------+
    //| Constructor                                                     |
    //+----------------------------------------------------------------+
    CLogger(void) : m_fileHandle(INVALID_HANDLE),
                    m_headerWritten(false)
    {}

    //+----------------------------------------------------------------+
    //| Init                                                            |
    //+----------------------------------------------------------------+
    bool Init(const bool enableCSV, const bool enableAlerts)
    {
        m_enableCSV    = enableCSV;
        m_enableAlerts = enableAlerts;

        if(m_enableCSV)
        {
            // Build filename: GoldBot_Trades_YYYYMMDD.csv
            MqlDateTime dt;
            TimeToStruct(TimeCurrent(), dt);
            m_logFilePath = StringFormat("GoldBot_Trades_%04d%02d%02d.csv",
                                         dt.year, dt.mon, dt.day);

            m_fileHandle = FileOpen(m_logFilePath,
                                    FILE_WRITE | FILE_READ | FILE_CSV | FILE_ANSI,
                                    ',');

            if(m_fileHandle == INVALID_HANDLE)
            {
                Print("[Logger] Failed to open log file: ", m_logFilePath,
                      " Error: ", GetLastError());
                m_enableCSV = false;
                return false;
            }

            // Seek to end to append
            FileSeek(m_fileHandle, 0, SEEK_END);
            long fileSize = FileTell(m_fileHandle);

            if(fileSize == 0)
            {
                // Write header
                string header = "DateTime,Symbol,Type,EntryPrice,SLPrice,TPPrice,"
                                "LotSize,RiskAmount,SetupType,"
                                "ClosePrice,CloseTime,PnL,RMultiple,DailyPnL,EquityAtEntry,Ticket";
                FileWriteString(m_fileHandle, header + "\n");
                m_headerWritten = true;
            }
        }
        return true;
    }

    //+----------------------------------------------------------------+
    //| Deinit — close file handle                                     |
    //+----------------------------------------------------------------+
    void Deinit()
    {
        if(m_fileHandle != INVALID_HANDLE)
        {
            FileClose(m_fileHandle);
            m_fileHandle = INVALID_HANDLE;
        }
    }

    //+----------------------------------------------------------------+
    //| LogTradeOpen                                                    |
    //+----------------------------------------------------------------+
    void LogTradeOpen(const TradeLogRecord &rec)
    {
        string msg = StringFormat(
            "[TRADE OPEN] Ticket:%llu | %s %s @ %.2f | SL:%.2f TP:%.2f | "
            "Lots:%.2f | Risk:$%.2f | Setup:%s | Equity:$%.2f",
            rec.ticket, rec.symbol, rec.tradeType,
            rec.entryPrice, rec.slPrice, rec.tpPrice,
            rec.lotSize, rec.riskAmount,
            SetupTypeToString(rec.setupType),
            rec.equityAtEntry);

        Print(msg);

        if(m_enableAlerts)
            Alert(msg);

        if(m_enableCSV && m_fileHandle != INVALID_HANDLE)
        {
            string line = StringFormat(
                "%s,%s,%s,%.5f,%.5f,%.5f,%.2f,%.2f,%s,,,,%.2f,%.2f,%llu\n",
                TimeToString(rec.openTime, TIME_DATE | TIME_SECONDS),
                rec.symbol, rec.tradeType,
                rec.entryPrice, rec.slPrice, rec.tpPrice,
                rec.lotSize, rec.riskAmount,
                SetupTypeToString(rec.setupType),
                rec.dailyPnL, rec.equityAtEntry, rec.ticket);
            FileWriteString(m_fileHandle, line);
            FileFlush(m_fileHandle);
        }
    }

    //+----------------------------------------------------------------+
    //| LogTradeClose                                                   |
    //+----------------------------------------------------------------+
    void LogTradeClose(const TradeLogRecord &rec)
    {
        string msg = StringFormat(
            "[TRADE CLOSE] Ticket:%llu | %s %s | Close:%.2f | "
            "PnL:$%.2f | R:%.2fR | DailyPnL:$%.2f",
            rec.ticket, rec.symbol, rec.tradeType,
            rec.closePrice, rec.pnl, rec.rMultiple, rec.dailyPnL);

        Print(msg);

        if(m_enableAlerts)
            Alert(msg);

        if(m_enableCSV && m_fileHandle != INVALID_HANDLE)
        {
            string line = StringFormat(
                "%s,%s,%s,%.5f,%.5f,%.5f,%.2f,%.2f,%s,%.5f,%s,%.2f,%.2f,%.2f,%.2f,%llu\n",
                TimeToString(rec.openTime, TIME_DATE | TIME_SECONDS),
                rec.symbol, rec.tradeType,
                rec.entryPrice, rec.slPrice, rec.tpPrice,
                rec.lotSize, rec.riskAmount,
                SetupTypeToString(rec.setupType),
                rec.closePrice,
                TimeToString(rec.closeTime, TIME_DATE | TIME_SECONDS),
                rec.pnl, rec.rMultiple,
                rec.dailyPnL, rec.equityAtEntry, rec.ticket);
            FileWriteString(m_fileHandle, line);
            FileFlush(m_fileHandle);
        }
    }

    //+----------------------------------------------------------------+
    //| LogEvent — general EA event (kill switch, pause, etc.)        |
    //+----------------------------------------------------------------+
    void LogEvent(const string msg)
    {
        Print("[GoldBot EVENT] ", msg);
        if(m_enableAlerts)
            Alert("[GoldBot] ", msg);

        if(m_enableCSV && m_fileHandle != INVALID_HANDLE)
        {
            string line = StringFormat("%s,EVENT,,,,,,,,%s\n",
                TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), msg);
            FileWriteString(m_fileHandle, line);
            FileFlush(m_fileHandle);
        }
    }

    //+----------------------------------------------------------------+
    //| SetupTypeToString                                               |
    //+----------------------------------------------------------------+
    static string SetupTypeToString(const ENUM_SETUP_TYPE st)
    {
        switch(st)
        {
            case SETUP_TRIPLE_TOP: return "TripleTop";
            case SETUP_FVG:        return "FVG";
            case SETUP_CONFLUENCE: return "Confluence";
        }
        return "Unknown";
    }
};
