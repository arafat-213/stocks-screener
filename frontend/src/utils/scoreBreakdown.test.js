import { describe, it, expect } from 'vitest';
import { inferScoreBreakdown } from './scoreBreakdown';

describe('inferScoreBreakdown', () => {
  const mockSignal = {
    ema_signal: 'bullish',
    macd: 1.0,
    rsi_signal: 'bullish_strong',
    volume_signal: 'bullish',
    adx: 25,
    momentum_3m: 10,
  };

  it('handles null dailySignal gracefully', () => {
    const result = inferScoreBreakdown(null);
    expect(result).toEqual([]);
  });

  describe('Technical Score rules (Recalibrated to 100 pts)', () => {
    it('awards 28.5 pts for bullish_cross EMA', () => {
      const result = inferScoreBreakdown({ ema_signal: 'bullish_cross' });
      expect(result.find((r) => r.label === 'EMA Alignment').earned).toBe(28.5);
    });

    it('awards 21.5 pts for bullish_pullback EMA', () => {
      const result = inferScoreBreakdown({ ema_signal: 'bullish_pullback' });
      expect(result.find((r) => r.label === 'EMA Alignment').earned).toBe(21.5);
    });

    it('awards 11.5 pts for bullish EMA', () => {
      const result = inferScoreBreakdown({ ema_signal: 'bullish' });
      expect(result.find((r) => r.label === 'EMA Alignment').earned).toBe(11.5);
    });

    it('awards 11.5 pts for correlated MACD cross (EMA cross + MACD > 0)', () => {
      const result = inferScoreBreakdown({
        ema_signal: 'bullish_cross',
        macd: 1.0,
      });
      expect(result.find((r) => r.label === 'MACD').earned).toBe(11.5);
    });

    it('awards 14.5 pts for MACD > 0 in bullish regime', () => {
      const result = inferScoreBreakdown({ ema_signal: 'bullish', macd: 1.0 });
      expect(result.find((r) => r.label === 'MACD').earned).toBe(14.5);
    });

    it('awards 7.0 pts for MACD < 0 in bullish regime', () => {
      const result = inferScoreBreakdown({
        ema_signal: 'bullish_pullback',
        macd: -1.0,
      });
      expect(result.find((r) => r.label === 'MACD').earned).toBe(7.0);
    });

    it('awards 21.5 pts for RSI recovery', () => {
      const result = inferScoreBreakdown({ rsi_signal: 'bullish_recovery' });
      expect(result.find((r) => r.label === 'RSI').earned).toBe(21.5);
    });

    it('awards 14.5 pts for RSI crossing 50', () => {
      const result = inferScoreBreakdown({ rsi_signal: 'bullish_crossing' });
      expect(result.find((r) => r.label === 'RSI').earned).toBe(14.5);
    });

    it('awards 21.5 pts for Volume breakout', () => {
      const result = inferScoreBreakdown({ volume_breakout: true });
      expect(result.find((r) => r.label === 'Volume').earned).toBe(21.5);
    });

    it('awards Trend Quality points correctly (ADX + Momentum)', () => {
      const result = inferScoreBreakdown({ adx: 35, momentum_3m: 20 });
      // 4.5 (ADX) + 3.0 (Mom) = 7.5, capped at 7.0
      expect(result.find((r) => r.label === 'Trend Quality').earned).toBe(7.0);
    });

    it('awards partial Trend Quality points', () => {
      const result = inferScoreBreakdown({ adx: 20, momentum_3m: 10 });
      // 1.5 (ADX) + 1.5 (Mom) = 3.0
      expect(result.find((r) => r.label === 'Trend Quality').earned).toBe(3.0);
    });
  });

  it('contains only technical category items', () => {
    const result = inferScoreBreakdown(mockSignal);
    const hasFundamental = result.some((r) => r.category === 'fundamental');
    expect(hasFundamental).toBe(false);
    expect(result.length).toBe(5); // EMA, MACD, RSI, Volume, Trend Quality
  });
});
