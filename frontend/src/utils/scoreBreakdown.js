/**
 * Infers the sub-score breakdown from a Daily signal object.
 * Returns an array of { label, earned, max, signal, category } objects.
 *
 * All inference is approximate — we don't store sub-scores in the DB.
 * The source of truth for rules is backend/app/pipeline/scorer.py.
 */
export function inferScoreBreakdown(dailySignal, fundamentals) {
  if (!dailySignal) return [];

  const breakdown = [];

  // Technical sub-scores (max 70)

  // EMA Alignment: 20 pts — bullish if ema_signal === 'bullish'
  breakdown.push({
    label: 'EMA Alignment',
    earned: dailySignal.ema_signal === 'bullish' ? 20 : 0,
    max: 20,
    signal: dailySignal.ema_signal || 'neutral',
    category: 'technical',
  });

  // MACD: 20 pts — macd > 0 is a proxy (actual rule: macd > signal AND macd > 0)
  // We don't have signal_line in the API response, so use ema_signal as a proxy
  // since both require bullish alignment. If ema_signal is bullish, MACD likely earned too.
  // Be conservative: only award if ema_signal === 'bullish' (they are correlated in scorer.py)
  breakdown.push({
    label: 'MACD',
    earned: dailySignal.ema_signal === 'bullish' ? 20 : 0,
    max: 20,
    signal: dailySignal.macd > 0 ? 'bullish' : 'bearish',
    category: 'technical',
  });

  // RSI: 15 pts — use rsi_signal field
  const rsiEarned =
    dailySignal.rsi_signal === 'bullish_recovery'
      ? 15
      : dailySignal.rsi_signal === 'bullish_crossing'
        ? 15
        : dailySignal.rsi_signal === 'bullish_strong'
          ? 5
          : 0;
  breakdown.push({
    label: 'RSI',
    earned: rsiEarned,
    max: 15,
    signal: dailySignal.rsi_signal || 'neutral',
    category: 'technical',
  });

  // Volume: 15 pts — use volume_signal field
  breakdown.push({
    label: 'Volume',
    earned: dailySignal.volume_signal === 'bullish' ? 15 : 0,
    max: 15,
    signal: dailySignal.volume_signal || 'neutral',
    category: 'technical',
  });

  // Fundamental sub-scores (max 30) — inferred from fundamentals object
  // PE: max 10 pts
  const pe = fundamentals?.pe;
  const peEarned =
    pe == null ? 0 : pe < 25 ? 10 : pe < 40 ? 6 : pe < 60 ? 2 : 0;
  breakdown.push({
    label: 'P/E Ratio',
    earned: peEarned,
    max: 10,
    signal: pe ? `PE ${pe.toFixed(1)}` : 'no data',
    category: 'fundamental',
  });

  // ROE: max 5 pts (roe from fundamentals, stored as decimal e.g. 0.15)
  const roe = fundamentals?.roe;
  const normalizedRoe = roe > 1 ? roe / 100 : roe;
  const roeEarned =
    normalizedRoe == null
      ? 0
      : normalizedRoe > 0.15
        ? 5
        : normalizedRoe > 0.1
          ? 2
          : 0;
  breakdown.push({
    label: 'ROE',
    earned: roeEarned,
    max: 5,
    signal:
      normalizedRoe != null
        ? `${(normalizedRoe * 100).toFixed(1)}%`
        : 'no data',
    category: 'fundamental',
  });

  // ROCE: max 5 pts (roce stored as decimal e.g. 0.15)
  const roce = fundamentals?.roce;
  const normalizedRoce = roce > 1 ? roce / 100 : roce;
  const roceEarned =
    normalizedRoce == null
      ? 0
      : normalizedRoce > 0.15
        ? 5
        : normalizedRoce > 0.1
          ? 2
          : 0;
  breakdown.push({
    label: 'ROCE',
    earned: roceEarned,
    max: 5,
    signal:
      normalizedRoce != null
        ? `${(normalizedRoce * 100).toFixed(1)}%`
        : 'no data',
    category: 'fundamental',
  });

  // Pledge: max 5 pts (pledged_percent stored as decimal e.g. 0.05)
  const pledged = fundamentals?.pledged_percent;
  const pledgedEarned =
    pledged == null ? 0 : pledged === 0 ? 5 : pledged < 0.1 ? 2 : 0;
  breakdown.push({
    label: 'Pledge',
    earned: pledgedEarned,
    max: 5,
    signal: pledged != null ? `${(pledged * 100).toFixed(1)}%` : 'no data',
    category: 'fundamental',
  });

  // D/E: max 5 pts
  const de = fundamentals?.debt_equity;
  const deEarned = de == null ? 0 : de < 0.5 ? 5 : de < 1.0 ? 2 : 0;
  breakdown.push({
    label: 'Debt/Equity',
    earned: deEarned,
    max: 5,
    signal: de != null ? `D/E ${de.toFixed(2)}` : 'no data',
    category: 'fundamental',
  });

  return breakdown;
}
