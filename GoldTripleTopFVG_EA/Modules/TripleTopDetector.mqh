//+------------------------------------------------------------------+
//| TripleTopDetector.mqh                                            |
//| Triple Top Pattern Detection for Gold EA                        |
//| Detects 3 swing highs within tolerance, calculates neckline,    |
//| confirms pattern on neckline close break.                        |
//| No repainting — uses only confirmed closed bars.                 |
//+------------------------------------------------------------------+
#pragma once
#include "MarketStructure.mqh"

//--- Triple Top pattern state
enum ENUM_TT_STATE
{
    TT_STATE_NONE      = 0,   // No pattern in progress
    TT_STATE_H1_FOUND  = 1,   // First high found
    TT_STATE_H2_FOUND  = 2,   // Second high found
    TT_STATE_H3_FOUND  = 3,   // Third high found, awaiting neckline break
    TT_STATE_CONFIRMED = 4,   // Neckline broken — trade ready
    TT_STATE_ACTIVE    = 5,   // Trade entered
    TT_STATE_INVALID   = 6    // Pattern invalidated (price broke above tops)
};

//--- Full triple top structure
struct TripleTopPattern
{
    // Three highs
    double   h1Price;
    int      h1Bar;
    datetime h1Time;

    double   h2Price;
    int      h2Bar;
    datetime h2Time;

    double   h3Price;
    int      h3Bar;
    datetime h3Time;

    double   topHigh;       // Highest of the three (for SL placement)

    // Neckline
    double   necklinePrice;
    double   necklineSupport1;  // Low between H1-H2
    double   necklineSupport2;  // Low between H2-H3

    // Confirmation
    bool     confirmed;          // True after close below neckline
    int      confirmBar;
    datetime confirmTime;

    // Entry levels
    double   entryPrice;         // Immediate break entry or retest level
    double   stopLoss;
    double   takeProfit;

    // State
    ENUM_TT_STATE state;

    // Volume at H1 and H3 for exhaustion filter
    long     h1Volume;
    long     h3Volume;
};

//--- Maximum concurrent patterns to track
#define MAX_TT_PATTERNS 5

//+------------------------------------------------------------------+
//| CTripleTopDetector class                                         |
//+------------------------------------------------------------------+
class CTripleTopDetector
{
private:
    string              m_symbol;
    ENUM_TIMEFRAMES     m_tf;
    double              m_tolerance;       // e.g. 0.003 = 0.3%
    int                 m_minBars;
    int                 m_maxBars;
    int                 m_lookback;
    double              m_slBufferPips;
    double              m_pipSize;         // Point size for gold ($0.01 per point, 1 pip = $0.10)

    TripleTopPattern    m_patterns[];
    int                 m_patternCount;

    //--- Pivot strength for swing detection
    int                 m_leftBars;
    int                 m_rightBars;

public:
    //+----------------------------------------------------------------+
    //| Constructor                                                     |
    //+----------------------------------------------------------------+
    CTripleTopDetector(void) : m_patternCount(0),
                               m_leftBars(3), m_rightBars(3)
    {
        ArrayResize(m_patterns, MAX_TT_PATTERNS);
    }

    //+----------------------------------------------------------------+
    //| Init — call once from OnInit                                   |
    //+----------------------------------------------------------------+
    bool Init(const string symbol, const ENUM_TIMEFRAMES tf,
              const double tolerance,  const int minBars,
              const int maxBars,       const int lookback,
              const double slBufferPips)
    {
        m_symbol       = symbol;
        m_tf           = tf;
        m_tolerance    = tolerance;
        m_minBars      = minBars;
        m_maxBars      = maxBars;
        m_lookback     = lookback;
        m_slBufferPips = slBufferPips;
        m_pipSize      = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10.0; // 1 pip

        // Validate
        if(m_tolerance <= 0.0 || m_minBars < 1 || m_maxBars <= m_minBars)
        {
            Print("[TripleTopDetector] Invalid parameters");
            return false;
        }

        m_patternCount = 0;
        return true;
    }

    //+----------------------------------------------------------------+
    //| Scan — call from OnTick (on new bar events)                   |
    //| Performs full pattern scan on closed bars                      |
    //+----------------------------------------------------------------+
    void Scan()
    {
        // Collect swing highs from the last m_lookback bars
        SwingPoint swings[];
        int count = FindSwingHighs(m_symbol, m_tf, m_lookback,
                                   m_leftBars, m_rightBars, swings);

        if(count < 3) return;

        // Try every combination of 3 swing highs (ordered newest→oldest)
        // swings[0] = most recent by bar index (lowest bar number = most recent)
        for(int i = 0; i < count - 2; i++)          // H3 candidate (most recent)
        {
            for(int j = i + 1; j < count - 1; j++)  // H2 candidate
            {
                for(int k = j + 1; k < count; k++)  // H1 candidate (oldest)
                {
                    // Bar spacing checks
                    int gapH3H2 = swings[j].bar - swings[i].bar;
                    int gapH2H1 = swings[k].bar - swings[j].bar;

                    if(gapH3H2 < m_minBars || gapH3H2 > m_maxBars) continue;
                    if(gapH2H1 < m_minBars || gapH2H1 > m_maxBars) continue;

                    // Price tolerance check — all three within tolerance band
                    double p1 = swings[k].price; // H1
                    double p2 = swings[j].price; // H2
                    double p3 = swings[i].price; // H3

                    double avgTop  = (p1 + p2 + p3) / 3.0;
                    double tolAbs  = avgTop * m_tolerance;

                    if(MathAbs(p1 - avgTop) > tolAbs) continue;
                    if(MathAbs(p2 - avgTop) > tolAbs) continue;
                    if(MathAbs(p3 - avgTop) > tolAbs) continue;

                    // Build candidate pattern
                    TripleTopPattern pat;
                    pat.h1Price = p1;  pat.h1Bar = swings[k].bar;  pat.h1Time = swings[k].time;
                    pat.h2Price = p2;  pat.h2Bar = swings[j].bar;  pat.h2Time = swings[j].time;
                    pat.h3Price = p3;  pat.h3Bar = swings[i].bar;  pat.h3Time = swings[i].time;
                    pat.topHigh = MathMax(p1, MathMax(p2, p3));

                    // Volume on H1 and H3
                    pat.h1Volume = (long)iVolume(m_symbol, m_tf, pat.h1Bar);
                    pat.h3Volume = (long)iVolume(m_symbol, m_tf, pat.h3Bar);

                    // Neckline: lowest low between H1-H2 and H2-H3
                    pat.necklineSupport1 = GetLowestLowBetweenBars(m_symbol, m_tf,
                                               pat.h2Bar, pat.h1Bar);
                    pat.necklineSupport2 = GetLowestLowBetweenBars(m_symbol, m_tf,
                                               pat.h3Bar, pat.h2Bar);
                    pat.necklinePrice = MathMin(pat.necklineSupport1, pat.necklineSupport2);

                    if(pat.necklinePrice <= 0.0) continue;

                    // Check confirmation: has price closed BELOW neckline since H3?
                    pat.confirmed   = false;
                    pat.confirmBar  = -1;
                    pat.state       = TT_STATE_H3_FOUND;

                    // Invalidation check: has price closed ABOVE the top?
                    bool invalidated = false;
                    for(int b = pat.h3Bar - 1; b >= 1; b--)  // bars after H3, skip bar[0]
                    {
                        double closeB = iClose(m_symbol, m_tf, b);
                        if(closeB <= 0.0) continue;

                        // Invalidated if close above topHigh
                        if(closeB > pat.topHigh)
                        {
                            invalidated = true;
                            break;
                        }

                        // Confirmed if close below neckline
                        if(closeB < pat.necklinePrice)
                        {
                            pat.confirmed    = true;
                            pat.confirmBar   = b;
                            pat.confirmTime  = iTime(m_symbol, m_tf, b);
                            pat.state        = TT_STATE_CONFIRMED;
                            pat.entryPrice   = pat.necklinePrice; // retest level
                            pat.stopLoss     = pat.topHigh + m_slBufferPips * m_pipSize;
                            double risk      = pat.stopLoss - pat.entryPrice;
                            if(risk <= 0.0) risk = m_slBufferPips * m_pipSize;
                            pat.takeProfit   = pat.entryPrice - 5.0 * risk;
                            break;
                        }
                    }

                    if(invalidated) continue;

                    // Add or update pattern list
                    if(!PatternAlreadyTracked(pat))
                    {
                        AddPattern(pat);
                    }
                }
            }
        }

        // Refresh states on existing confirmed patterns
        RefreshPatternStates();
    }

    //+----------------------------------------------------------------+
    //| GetConfirmedPatterns — fills out[] with all confirmed patterns |
    //| Returns count                                                   |
    //+----------------------------------------------------------------+
    int GetConfirmedPatterns(TripleTopPattern &out[])
    {
        int n = 0;
        ArrayResize(out, 0);
        for(int i = 0; i < m_patternCount; i++)
        {
            if(m_patterns[i].state == TT_STATE_CONFIRMED)
            {
                ArrayResize(out, n + 1);
                out[n] = m_patterns[i];
                n++;
            }
        }
        return n;
    }

    //+----------------------------------------------------------------+
    //| MarkPatternActive — after trade entry, mark pattern active     |
    //+----------------------------------------------------------------+
    void MarkPatternActive(const datetime confirmTime)
    {
        for(int i = 0; i < m_patternCount; i++)
        {
            if(m_patterns[i].confirmTime == confirmTime)
                m_patterns[i].state = TT_STATE_ACTIVE;
        }
    }

    //+----------------------------------------------------------------+
    //| GetPatternCount                                                 |
    //+----------------------------------------------------------------+
    int GetPatternCount() const { return m_patternCount; }

private:
    //+----------------------------------------------------------------+
    //| AddPattern                                                      |
    //+----------------------------------------------------------------+
    void AddPattern(const TripleTopPattern &pat)
    {
        if(m_patternCount >= MAX_TT_PATTERNS)
        {
            // Remove oldest (shift left)
            for(int i = 0; i < MAX_TT_PATTERNS - 1; i++)
                m_patterns[i] = m_patterns[i + 1];
            m_patternCount = MAX_TT_PATTERNS - 1;
        }
        m_patterns[m_patternCount] = pat;
        m_patternCount++;
    }

    //+----------------------------------------------------------------+
    //| PatternAlreadyTracked                                           |
    //| Uses H1/H2/H3 bar times as unique key                          |
    //+----------------------------------------------------------------+
    bool PatternAlreadyTracked(const TripleTopPattern &pat) const
    {
        for(int i = 0; i < m_patternCount; i++)
        {
            if(m_patterns[i].h1Time == pat.h1Time &&
               m_patterns[i].h2Time == pat.h2Time &&
               m_patterns[i].h3Time == pat.h3Time)
                return true;
        }
        return false;
    }

    //+----------------------------------------------------------------+
    //| RefreshPatternStates                                            |
    //| Invalidate confirmed patterns where price broke above tops     |
    //+----------------------------------------------------------------+
    void RefreshPatternStates()
    {
        for(int i = 0; i < m_patternCount; i++)
        {
            if(m_patterns[i].state != TT_STATE_CONFIRMED) continue;

            // Current close (bar[1] = last closed bar)
            double closeNow = iClose(m_symbol, m_tf, 1);
            if(closeNow > m_patterns[i].topHigh)
            {
                m_patterns[i].state = TT_STATE_INVALID;
                Print("[TripleTop] Pattern invalidated — price closed above top at ",
                      DoubleToString(m_patterns[i].topHigh, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS)));
            }
        }
    }

    //+----------------------------------------------------------------+
    //| IsRetestOccurring                                               |
    //| True when current bid has returned to neckline ± 1 pip        |
    //+----------------------------------------------------------------+
    bool IsRetestOccurring(const TripleTopPattern &pat) const
    {
        double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
        double pip  = m_pipSize;
        return (bid >= pat.necklinePrice - pip && bid <= pat.necklinePrice + pip * 3.0);
    }
};
