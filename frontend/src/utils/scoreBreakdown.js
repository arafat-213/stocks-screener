/**
 * Infers the sub-score breakdown from a Daily signal object.
 * Returns an array of { label, earned, max, signal, category } objects.
 *
 * All inference is approximate — we don't store sub-scores in the DB.
 * The source of truth for rules is backend/app/pipeline/scorer.py.
 */
export function inferScoreBreakdown(dailySignal) {
  if (!dailySignal) return [];

  const breakdown = [];

  // Technical sub-scores (max 70)

  // EMA Alignment: 20 pts
  let emaEarned = 0;
  if (dailySignal.ema_signal === 'bullish_cross') emaEarned = 28.5;
  else if (dailySignal.ema_signal === 'bullish_pullback') emaEarned = 21.5;
  else if (dailySignal.ema_signal === 'bullish') emaEarned = 11.5;

  breakdown.push({
    label: 'EMA Alignment',
    earned: emaEarned,
    max: 30,
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
      macdEarned = 11.5; // Correlated same-day EMA/MACD cross
    } else if (isBullishRegime && dailySignal.macd > 0) {
      macdEarned = 14.5;
    } else if (isBullishRegime && dailySignal.macd < 0) {
      macdEarned = 7.0;
    }
  }

  breakdown.push({
    label: 'MACD',
    earned: macdEarned,
    max: 21.5,
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
    rsiEarned = 21.5;
  } else if (dailySignal.rsi_signal === 'bullish_crossing') {
    rsiEarned = 14.5;
  } else if (dailySignal.rsi_signal === 'bullish_strong') {
    rsiEarned = 7.0;
  }

  breakdown.push({
    label: 'RSI',
    earned: rsiEarned,
    max: 21.5,
    signal: dailySignal.rsi_signal || 'neutral',
    category: 'technical',
  });

  // Volume: 15 pts
  breakdown.push({
    label: 'Volume',
    earned:
      dailySignal.volume_signal === 'bullish' || dailySignal.volume_breakout
        ? 21.5
        : 0,
    max: 21.5,
    signal:
      dailySignal.volume_signal ||
      (dailySignal.volume_breakout ? 'breakout' : 'neutral'),
    category: 'technical',
  });

  // Trend Quality: 5 pts (ADX + 3m Momentum)
  let trendEarned = 0;
  if (!isNaN(dailySignal.adx) && dailySignal.adx != null) {
    if (dailySignal.adx >= 35) trendEarned += 4.5;
    else if (dailySignal.adx >= 25) trendEarned += 3.0;
    else if (dailySignal.adx >= 20) trendEarned += 1.5;
  }
  if (!isNaN(dailySignal.momentum_3m) && dailySignal.momentum_3m != null) {
    if (dailySignal.momentum_3m > 15) trendEarned += 3.0;
    else if (dailySignal.momentum_3m > 5) trendEarned += 1.5;
  }
  trendEarned = Math.min(trendEarned, 7.0);

  breakdown.push({
    label: 'Trend Quality',
    earned: trendEarned,
    max: 7.0,
    signal: !isNaN(dailySignal.adx)
      ? `ADX ${dailySignal.adx.toFixed(1)}`
      : 'neutral',
    category: 'technical',
  });

  return breakdown;
}
