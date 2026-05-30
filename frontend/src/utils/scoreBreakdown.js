/**
 * Helper to normalize percentage values (e.g. > 5.0) and apply scoring rules.
 */
function normalizeAndScore(
  value,
  threshold = 5.0,
  rules = [
    { min: 0.15, points: 5 },
    { min: 0.1, points: 2 },
  ]
) {
  if (value == null || isNaN(value)) return { earned: 0, normalized: null };
  const normalized = value > threshold ? value / 100 : value;
  let earned = 0;
  for (const rule of rules) {
    if (normalized > rule.min) {
      earned = rule.points;
      break;
    }
  }
  return { earned, normalized };
}

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

  // EMA Alignment: 20 pts
  let emaEarned = 0;
  if (dailySignal.ema_signal === 'bullish_cross') emaEarned = 20;
  else if (dailySignal.ema_signal === 'bullish_pullback') emaEarned = 15;
  else if (dailySignal.ema_signal === 'bullish') emaEarned = 8;

  breakdown.push({
    label: 'EMA Alignment',
    earned: emaEarned,
    max: 20,
    signal: dailySignal.ema_signal || 'neutral',
    category: 'technical',
  });

  // MACD: 15 pts (Max)
  let macdEarned = 0;
  const isBullishRegime = [
    'bullish',
    'bullish_pullback',
    'bullish_cross',
  ].includes(dailySignal.ema_signal);

  if (!isNaN(dailySignal.macd) && dailySignal.macd != null) {
    if (dailySignal.ema_signal === 'bullish_cross' && dailySignal.macd > 0) {
      macdEarned = 8; // Correlated same-day EMA/MACD cross
    } else if (isBullishRegime && dailySignal.macd > 0) {
      macdEarned = 10;
    } else if (isBullishRegime && dailySignal.macd < 0) {
      macdEarned = 5;
    }
  }

  breakdown.push({
    label: 'MACD',
    earned: macdEarned,
    max: 15,
    signal:
      !isNaN(dailySignal.macd) && dailySignal.macd != null
        ? dailySignal.macd > 0
          ? 'bullish'
          : 'bearish'
        : 'no data',
    category: 'technical',
  });

  // RSI: 15 pts — use rsi_signal field
  let rsiEarned = 0;
  if (
    ['bullish_recovery', 'bullish_recovery_confirmed'].includes(
      dailySignal.rsi_signal
    )
  ) {
    rsiEarned = 15;
  } else if (dailySignal.rsi_signal === 'bullish_crossing') {
    rsiEarned = 10;
  } else if (dailySignal.rsi_signal === 'bullish_strong') {
    rsiEarned = 5;
  }

  breakdown.push({
    label: 'RSI',
    earned: rsiEarned,
    max: 15,
    signal: dailySignal.rsi_signal || 'neutral',
    category: 'technical',
  });

  // Volume: 15 pts
  breakdown.push({
    label: 'Volume',
    earned:
      dailySignal.volume_signal === 'bullish' || dailySignal.volume_breakout
        ? 15
        : 0,
    max: 15,
    signal:
      dailySignal.volume_signal ||
      (dailySignal.volume_breakout ? 'breakout' : 'neutral'),
    category: 'technical',
  });

  // Trend Quality: 5 pts (ADX + 3m Momentum)
  let trendEarned = 0;
  if (!isNaN(dailySignal.adx) && dailySignal.adx != null) {
    if (dailySignal.adx >= 35) trendEarned += 3;
    else if (dailySignal.adx >= 25) trendEarned += 2;
    else if (dailySignal.adx >= 20) trendEarned += 1;
  }
  if (!isNaN(dailySignal.momentum_3m) && dailySignal.momentum_3m != null) {
    if (dailySignal.momentum_3m > 15) trendEarned += 2;
    else if (dailySignal.momentum_3m > 5) trendEarned += 1;
  }
  trendEarned = Math.min(trendEarned, 5);

  breakdown.push({
    label: 'Trend Quality',
    earned: trendEarned,
    max: 5,
    signal: !isNaN(dailySignal.adx)
      ? `ADX ${dailySignal.adx.toFixed(1)}`
      : 'neutral',
    category: 'technical',
  });

  // Fundamental sub-scores (max 30) — inferred from fundamentals object
  // PE: max 10 pts
  const pe = fundamentals?.pe;
  const peEarned =
    pe == null || isNaN(pe) ? 0 : pe < 25 ? 10 : pe < 40 ? 6 : pe < 60 ? 2 : 0;
  breakdown.push({
    label: 'P/E Ratio',
    earned: peEarned,
    max: 10,
    signal: !isNaN(pe) && pe != null ? `PE ${pe.toFixed(1)}` : 'no data',
    category: 'fundamental',
  });

  // ROE: max 5 pts
  const { earned: roeEarned, normalized: normalizedRoe } = normalizeAndScore(
    fundamentals?.roe,
    5.0
  );
  breakdown.push({
    label: 'ROE',
    earned: roeEarned,
    max: 5,
    signal:
      !isNaN(normalizedRoe) && normalizedRoe != null
        ? `${(normalizedRoe * 100).toFixed(1)}%`
        : 'no data',
    category: 'fundamental',
  });

  // ROCE: max 5 pts
  const roce = fundamentals?.roce;
  const roceEarned =
    roce == null || isNaN(roce) ? 0 : roce > 0.15 ? 5 : roce > 0.1 ? 2 : 0;
  breakdown.push({
    label: 'ROCE',
    earned: roceEarned,
    max: 5,
    signal:
      !isNaN(roce) && roce != null ? `${(roce * 100).toFixed(1)}%` : 'no data',
    category: 'fundamental',
  });

  // Pledge: max 5 pts
  const pledged = fundamentals?.pledged_percent;
  let pledgedEarned = 0;
  if (pledged != null && !isNaN(pledged)) {
    if (pledged === 0) pledgedEarned = 5;
    else if (pledged < 0.1) pledgedEarned = 3;
    else if (pledged < 0.2) pledgedEarned = 1;
  }
  breakdown.push({
    label: 'Pledge',
    earned: pledgedEarned,
    max: 5,
    signal:
      !isNaN(pledged) && pledged != null
        ? `${(pledged * 100).toFixed(1)}%`
        : 'no data',
    category: 'fundamental',
  });

  // D/E: max 5 pts
  const de = fundamentals?.debt_equity;
  const deEarned =
    de == null || isNaN(de) ? 0 : de < 0.5 ? 5 : de < 1.0 ? 2 : 0;
  breakdown.push({
    label: 'Debt/Equity',
    earned: deEarned,
    max: 5,
    signal: !isNaN(de) && de != null ? `D/E ${de.toFixed(2)}` : 'no data',
    category: 'fundamental',
  });

  return breakdown;
}
