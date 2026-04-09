//+------------------------------------------------------------------+
//| MarketStructure.mqh                                              |
//| Swing High/Low Detection for Gold Triple Top + FVG EA           |
//| Purpose: Identify swing highs and lows on closed bars only       |
//+------------------------------------------------------------------+
#pragma once

//--- Swing point structure
struct SwingPoint
{
    double   price;      // Price level of swing
    int      bar;        // Bar index (0 = most recent closed)
    datetime time;       // Bar open time
    bool     isHigh;     // true = swing high, false = swing low
};

//+------------------------------------------------------------------+
//| IsSwingHigh                                                       |
//| Returns true if bar[bar] is a confirmed swing high               |
//| Requires leftBars bars to the left and rightBars to the right    |
//| to all be LOWER than the candidate bar.                          |
//| NEVER uses bar[0] — only confirmed closed bars.                  |
//+------------------------------------------------------------------+
bool IsSwingHigh(const string symbol, const ENUM_TIMEFRAMES tf,
                 const int bar, const int leftBars, const int rightBars)
{
    // bar must be at least rightBars away from bar[0]
    if(bar < rightBars) return false;
    if(bar < 0)         return false;

    double high = iHigh(symbol, tf, bar);
    if(high <= 0.0) return false;

    // Left side: bars further back (higher index)
    for(int i = bar + 1; i <= bar + leftBars; i++)
    {
        double h = iHigh(symbol, tf, i);
        if(h <= 0.0) return false;
        if(h >= high) return false;
    }

    // Right side: bars more recent (lower index), all must be confirmed closed
    for(int i = bar - 1; i >= bar - rightBars; i--)
    {
        if(i < 0) return false;  // Do not use bar[0]
        double h = iHigh(symbol, tf, i);
        if(h <= 0.0) return false;
        if(h >= high) return false;
    }

    return true;
}

//+------------------------------------------------------------------+
//| IsSwingLow                                                        |
//| Returns true if bar[bar] is a confirmed swing low                |
//+------------------------------------------------------------------+
bool IsSwingLow(const string symbol, const ENUM_TIMEFRAMES tf,
                const int bar, const int leftBars, const int rightBars)
{
    if(bar < rightBars) return false;
    if(bar < 0)         return false;

    double low = iLow(symbol, tf, bar);
    if(low <= 0.0) return false;

    for(int i = bar + 1; i <= bar + leftBars; i++)
    {
        double l = iLow(symbol, tf, i);
        if(l <= 0.0) return false;
        if(l <= low) return false;
    }

    for(int i = bar - 1; i >= bar - rightBars; i--)
    {
        if(i < 0) return false;
        double l = iLow(symbol, tf, i);
        if(l <= 0.0) return false;
        if(l <= low) return false;
    }

    return true;
}

//+------------------------------------------------------------------+
//| FindSwingHighs                                                    |
//| Scans lookback bars and fills result[] with swing highs          |
//| leftBars/rightBars define the pivot strength                     |
//| Returns count of swing highs found                               |
//+------------------------------------------------------------------+
int FindSwingHighs(const string symbol, const ENUM_TIMEFRAMES tf,
                   const int lookback, const int leftBars, const int rightBars,
                   SwingPoint &result[])
{
    ArrayResize(result, 0);
    int count = 0;

    // Start from rightBars+1 so the most recent candidates are confirmed
    int startBar = rightBars + 1;
    int endBar   = lookback;

    for(int bar = startBar; bar <= endBar; bar++)
    {
        if(IsSwingHigh(symbol, tf, bar, leftBars, rightBars))
        {
            ArrayResize(result, count + 1);
            result[count].price  = iHigh(symbol, tf, bar);
            result[count].bar    = bar;
            result[count].time   = iTime(symbol, tf, bar);
            result[count].isHigh = true;
            count++;
        }
    }

    return count;
}

//+------------------------------------------------------------------+
//| FindSwingLows                                                     |
//| Scans lookback bars and fills result[] with swing lows           |
//| Returns count of swing lows found                                |
//+------------------------------------------------------------------+
int FindSwingLows(const string symbol, const ENUM_TIMEFRAMES tf,
                  const int lookback, const int leftBars, const int rightBars,
                  SwingPoint &result[])
{
    ArrayResize(result, 0);
    int count = 0;

    int startBar = rightBars + 1;
    int endBar   = lookback;

    for(int bar = startBar; bar <= endBar; bar++)
    {
        if(IsSwingLow(symbol, tf, bar, leftBars, rightBars))
        {
            ArrayResize(result, count + 1);
            result[count].price  = iLow(symbol, tf, bar);
            result[count].bar    = bar;
            result[count].time   = iTime(symbol, tf, bar);
            result[count].isHigh = false;
            count++;
        }
    }

    return count;
}

//+------------------------------------------------------------------+
//| GetLowestLowBetweenBars                                          |
//| Returns the lowest low between bar indices barA and barB         |
//| (barA < barB means barA is more recent)                          |
//+------------------------------------------------------------------+
double GetLowestLowBetweenBars(const string symbol, const ENUM_TIMEFRAMES tf,
                                const int barA, const int barB)
{
    int lo = MathMin(barA, barB);
    int hi = MathMax(barA, barB);
    double lowest = DBL_MAX;

    for(int i = lo; i <= hi; i++)
    {
        double l = iLow(symbol, tf, i);
        if(l > 0.0 && l < lowest)
            lowest = l;
    }

    return (lowest == DBL_MAX) ? 0.0 : lowest;
}

//+------------------------------------------------------------------+
//| GetHighestHighBetweenBars                                        |
//| Returns the highest high between bar indices barA and barB       |
//+------------------------------------------------------------------+
double GetHighestHighBetweenBars(const string symbol, const ENUM_TIMEFRAMES tf,
                                  const int barA, const int barB)
{
    int lo = MathMin(barA, barB);
    int hi = MathMax(barA, barB);
    double highest = 0.0;

    for(int i = lo; i <= hi; i++)
    {
        double h = iHigh(symbol, tf, i);
        if(h > highest)
            highest = h;
    }

    return highest;
}

//+------------------------------------------------------------------+
//| IsH4Bearish                                                       |
//| Returns true if H4 structure is bearish (lower highs+lows)       |
//| Checks last 3 swing highs on H4                                  |
//+------------------------------------------------------------------+
bool IsH4Bearish(const string symbol)
{
    SwingPoint highs[];
    SwingPoint lows[];

    int hCount = FindSwingHighs(symbol, PERIOD_H4, 100, 3, 3, highs);
    int lCount = FindSwingLows(symbol,  PERIOD_H4, 100, 3, 3, lows);

    if(hCount < 2 || lCount < 2) return false;

    // Lower highs: highs[0] (most recent) < highs[1]
    bool lowerHighs = (highs[0].price < highs[1].price);
    // Lower lows: lows[0] < lows[1]
    bool lowerLows  = (lows[0].price  < lows[1].price);

    return (lowerHighs && lowerLows);
}

//+------------------------------------------------------------------+
//| IsH4Bullish                                                       |
//| Returns true if H4 structure is bullish (higher highs+lows)      |
//+------------------------------------------------------------------+
bool IsH4Bullish(const string symbol)
{
    SwingPoint highs[];
    SwingPoint lows[];

    int hCount = FindSwingHighs(symbol, PERIOD_H4, 100, 3, 3, highs);
    int lCount = FindSwingLows(symbol,  PERIOD_H4, 100, 3, 3, lows);

    if(hCount < 2 || lCount < 2) return false;

    bool higherHighs = (highs[0].price > highs[1].price);
    bool higherLows  = (lows[0].price  > lows[1].price);

    return (higherHighs && higherLows);
}
