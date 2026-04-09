//+------------------------------------------------------------------+
//| FVGDetector.mqh                                                  |
//| Fair Value Gap Detection and Management                         |
//| Detects bearish FVGs on M15 and H1, manages zones lifecycle     |
//| No repainting — confirmed closed candles only                   |
//+------------------------------------------------------------------+
#pragma once

#define MAX_FVG_ZONES 50

//--- FVG Zone structure
struct FVGZone
{
    double          topPrice;       // Upper boundary of the gap
    double          botPrice;       // Lower boundary of the gap
    double          midPrice;       // 50% midpoint (entry target)
    datetime        createdAt;      // Time of the middle candle (candle 2 of 3)
    ENUM_TIMEFRAMES tf;             // Timeframe this FVG was found on
    bool            isBearish;      // true = bearish FVG (we look for these)
    bool            isActive;       // false = invalidated
    bool            isFilled;       // true = price fully traversed the gap
    int             touches;        // How many times price has entered the zone
    bool            tradeEntered;   // One trade per gap
    int             zoneId;         // Unique ID
};

//+------------------------------------------------------------------+
//| CFVGDetector class                                               |
//+------------------------------------------------------------------+
class CFVGDetector
{
private:
    string          m_symbol;
    bool            m_scanM15;
    bool            m_scanH1;
    bool            m_useMidEntry;
    int             m_maxAgeHours;
    int             m_lookback;

    FVGZone         m_zones[];
    int             m_zoneCount;
    int             m_nextId;

public:
    //+----------------------------------------------------------------+
    //| Constructor                                                     |
    //+----------------------------------------------------------------+
    CFVGDetector(void) : m_zoneCount(0), m_nextId(1)
    {
        ArrayResize(m_zones, MAX_FVG_ZONES);
    }

    //+----------------------------------------------------------------+
    //| Init                                                            |
    //+----------------------------------------------------------------+
    bool Init(const string symbol,
              const bool scanM15,   const bool scanH1,
              const bool useMidEntry, const int maxAgeHours,
              const int lookback = 100)
    {
        m_symbol      = symbol;
        m_scanM15     = scanM15;
        m_scanH1      = scanH1;
        m_useMidEntry = useMidEntry;
        m_maxAgeHours = maxAgeHours;
        m_lookback    = lookback;
        m_zoneCount   = 0;
        m_nextId      = 1;
        return true;
    }

    //+----------------------------------------------------------------+
    //| Scan — call on every new bar                                   |
    //| Detects new FVGs, expires old ones, marks filled ones         |
    //+----------------------------------------------------------------+
    void Scan()
    {
        if(m_scanM15) ScanTimeframe(PERIOD_M15);
        if(m_scanH1)  ScanTimeframe(PERIOD_H1);

        ExpireOldZones();
        CheckFilledZones();
        PurgeInactiveZones();
    }

    //+----------------------------------------------------------------+
    //| GetActiveZones — fills out[] with all active bearish FVG zones |
    //| Returns count                                                   |
    //+----------------------------------------------------------------+
    int GetActiveZones(FVGZone &out[])
    {
        int n = 0;
        ArrayResize(out, 0);
        for(int i = 0; i < m_zoneCount; i++)
        {
            if(m_zones[i].isActive && m_zones[i].isBearish && !m_zones[i].isFilled)
            {
                ArrayResize(out, n + 1);
                out[n] = m_zones[i];
                n++;
            }
        }
        return n;
    }

    //+----------------------------------------------------------------+
    //| IsPriceInZone                                                   |
    //| Returns true if current bid is inside the FVG zone            |
    //+----------------------------------------------------------------+
    bool IsPriceInZone(const FVGZone &zone) const
    {
        double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
        return (bid <= zone.topPrice && bid >= zone.botPrice);
    }

    //+----------------------------------------------------------------+
    //| IsPriceAtMid                                                    |
    //| Returns true if bid has reached the 50% midpoint of the gap   |
    //+----------------------------------------------------------------+
    bool IsPriceAtMid(const FVGZone &zone) const
    {
        double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
        double mid = zone.midPrice;
        // Allow 1/4 of zone height as tolerance
        double tol = (zone.topPrice - zone.botPrice) * 0.25;
        return (bid <= mid + tol && bid >= mid - tol);
    }

    //+----------------------------------------------------------------+
    //| MarkTradeEntered                                                |
    //+----------------------------------------------------------------+
    void MarkTradeEntered(const int zoneId)
    {
        for(int i = 0; i < m_zoneCount; i++)
        {
            if(m_zones[i].zoneId == zoneId)
            {
                m_zones[i].tradeEntered = true;
                m_zones[i].touches++;
            }
        }
    }

    //+----------------------------------------------------------------+
    //| GetZoneCount                                                    |
    //+----------------------------------------------------------------+
    int GetZoneCount() const { return m_zoneCount; }

private:
    //+----------------------------------------------------------------+
    //| ScanTimeframe                                                   |
    //| Scans the last m_lookback bars on tf for bearish FVGs          |
    //+----------------------------------------------------------------+
    void ScanTimeframe(const ENUM_TIMEFRAMES tf)
    {
        // FVG uses candle triplets: [bar+2, bar+1, bar] with bar >= 2 (not bar[0] or bar[1])
        int startBar = 2;
        int endBar   = m_lookback - 1;

        for(int bar = startBar; bar <= endBar; bar++)
        {
            // Candle indices (bar+2 = oldest, bar = most recent of the three)
            int c1Bar = bar + 2;  // First candle (oldest)
            int c2Bar = bar + 1;  // Middle candle
            int c3Bar = bar;      // Third candle (most recent, but still closed)

            double c1High = iHigh(m_symbol, tf, c1Bar);
            double c3Low  = iLow(m_symbol,  tf, c3Bar);

            if(c1High <= 0.0 || c3Low <= 0.0) continue;

            // Bearish FVG: C1.High < C3.Low (gap between c3Low and c1High going up)
            // Actually: Bearish FVG means there is a gap ABOVE — candle 3 gaps DOWN
            // C1.High < C3.Low is a BULLISH FVG (unfilled space below)
            // Bearish FVG (downward move): C3.High < C1.Low
            double c1Low  = iLow(m_symbol,  tf, c1Bar);
            double c3High = iHigh(m_symbol, tf, c3Bar);

            bool bearishFVG = (c3High < c1Low);   // Gap between c3.high and c1.low

            if(!bearishFVG) continue;

            // Gap boundaries: top = c1.low, bot = c3.high
            double gapTop = c1Low;
            double gapBot = c3High;
            double gapMid = (gapTop + gapBot) / 2.0;

            // Minimum gap size: at least 1 pip
            double pip = SymbolInfoDouble(m_symbol, SYMBOL_POINT) * 10.0;
            if((gapTop - gapBot) < pip) continue;

            datetime createdAt = iTime(m_symbol, tf, c2Bar);

            // Skip if already tracked
            if(ZoneAlreadyTracked(createdAt, tf)) continue;

            // Add new zone
            AddZone(gapTop, gapBot, gapMid, createdAt, tf, true);
        }
    }

    //+----------------------------------------------------------------+
    //| AddZone                                                         |
    //+----------------------------------------------------------------+
    void AddZone(const double top, const double bot, const double mid,
                 const datetime created, const ENUM_TIMEFRAMES tf,
                 const bool isBearish)
    {
        if(m_zoneCount >= MAX_FVG_ZONES)
        {
            // Remove oldest active zone
            int oldest = 0;
            for(int i = 1; i < m_zoneCount; i++)
            {
                if(m_zones[i].createdAt < m_zones[oldest].createdAt)
                    oldest = i;
            }
            // Shift
            for(int i = oldest; i < m_zoneCount - 1; i++)
                m_zones[i] = m_zones[i + 1];
            m_zoneCount--;
        }

        FVGZone z;
        z.topPrice    = top;
        z.botPrice    = bot;
        z.midPrice    = mid;
        z.createdAt   = created;
        z.tf          = tf;
        z.isBearish   = isBearish;
        z.isActive    = true;
        z.isFilled    = false;
        z.touches     = 0;
        z.tradeEntered = false;
        z.zoneId      = m_nextId++;

        m_zones[m_zoneCount] = z;
        m_zoneCount++;
    }

    //+----------------------------------------------------------------+
    //| ZoneAlreadyTracked                                              |
    //+----------------------------------------------------------------+
    bool ZoneAlreadyTracked(const datetime created, const ENUM_TIMEFRAMES tf) const
    {
        for(int i = 0; i < m_zoneCount; i++)
        {
            if(m_zones[i].createdAt == created && m_zones[i].tf == tf)
                return true;
        }
        return false;
    }

    //+----------------------------------------------------------------+
    //| ExpireOldZones                                                  |
    //| Marks zones inactive if older than m_maxAgeHours              |
    //+----------------------------------------------------------------+
    void ExpireOldZones()
    {
        datetime now    = TimeCurrent();
        datetime maxAge = (datetime)(m_maxAgeHours * 3600);

        for(int i = 0; i < m_zoneCount; i++)
        {
            if(!m_zones[i].isActive) continue;
            if((now - m_zones[i].createdAt) > maxAge)
            {
                m_zones[i].isActive = false;
            }
        }
    }

    //+----------------------------------------------------------------+
    //| CheckFilledZones                                                |
    //| Marks a zone filled if a candle has fully closed inside it    |
    //| and then price has closed below botPrice                      |
    //+----------------------------------------------------------------+
    void CheckFilledZones()
    {
        for(int i = 0; i < m_zoneCount; i++)
        {
            if(!m_zones[i].isActive || m_zones[i].isFilled) continue;

            // Check last 3 closed bars for a full traversal
            for(int b = 1; b <= 5; b++)
            {
                double closeB = iClose(m_symbol, m_zones[i].tf, b);
                if(closeB <= 0.0) continue;

                // If price closed ABOVE the top of the gap — fully filled from below
                if(closeB > m_zones[i].topPrice)
                {
                    m_zones[i].isFilled = true;
                    m_zones[i].isActive = false;
                    break;
                }
            }
        }
    }

    //+----------------------------------------------------------------+
    //| PurgeInactiveZones                                              |
    //| Removes inactive/filled zones to manage memory                 |
    //+----------------------------------------------------------------+
    void PurgeInactiveZones()
    {
        int write = 0;
        for(int i = 0; i < m_zoneCount; i++)
        {
            if(m_zones[i].isActive)
            {
                if(write != i)
                    m_zones[write] = m_zones[i];
                write++;
            }
        }
        m_zoneCount = write;
    }
};
