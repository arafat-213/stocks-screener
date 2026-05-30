import { describe, it, expect } from 'vitest';
import { inferScoreBreakdown } from './scoreBreakdown';

describe('inferScoreBreakdown', () => {
  const mockSignal = {
    ema_signal: 'bullish',
    macd: 1.5,
    rsi_signal: 'bullish_strong',
    volume_signal: 'bullish',
  };

  it('normalizes ROE if > 5.0', () => {
    const fundamentals = { roe: 20.0 }; // 20%
    const result = inferScoreBreakdown(mockSignal, fundamentals);
    const roeRow = result.find((r) => r.label === 'ROE');
    expect(roeRow.earned).toBe(5);
    expect(roeRow.signal).toBe('20.0%');
  });

  it('does not normalize ROE if <= 5.0', () => {
    const fundamentals = { roe: 0.2 }; // 20% decimal
    const result = inferScoreBreakdown(mockSignal, fundamentals);
    const roeRow = result.find((r) => r.label === 'ROE');
    expect(roeRow.earned).toBe(5);
    expect(roeRow.signal).toBe('20.0%');
  });

  it('does NOT normalize ROCE even if > 5.0', () => {
    // ROCE should be decimal from backend. If it's 20.0, it should be treated as 2000%
    const fundamentals = { roce: 20.0 };
    const result = inferScoreBreakdown(mockSignal, fundamentals);
    const roceRow = result.find((r) => r.label === 'ROCE');
    expect(roceRow.earned).toBe(5);
    expect(roceRow.signal).toBe('2000.0%');
  });

  it('handles ROCE as decimal', () => {
    const fundamentals = { roce: 0.2 };
    const result = inferScoreBreakdown(mockSignal, fundamentals);
    const roceRow = result.find((r) => r.label === 'ROCE');
    expect(roceRow.earned).toBe(5);
    expect(roceRow.signal).toBe('20.0%');
  });

  it('handles NaN and nulls gracefully', () => {
    const fundamentals = { roe: NaN, roce: null, pe: undefined };
    const result = inferScoreBreakdown(mockSignal, fundamentals);

    expect(result.find((r) => r.label === 'ROE').signal).toBe('no data');
    expect(result.find((r) => r.label === 'ROCE').signal).toBe('no data');
    expect(result.find((r) => r.label === 'P/E Ratio').signal).toBe('no data');
  });

  it('uses fixed(1) for signals', () => {
    const fundamentals = { roe: 0.1567 };
    const result = inferScoreBreakdown(mockSignal, fundamentals);
    expect(result.find((r) => r.label === 'ROE').signal).toBe('15.7%');
  });

  describe('Technical Score rules', () => {
    it('awards 20 pts for bullish_cross EMA', () => {
      const result = inferScoreBreakdown({ ema_signal: 'bullish_cross' }, {});
      expect(result.find((r) => r.label === 'EMA Alignment').earned).toBe(20);
    });

    it('awards 15 pts for bullish_pullback EMA', () => {
      const result = inferScoreBreakdown(
        { ema_signal: 'bullish_pullback' },
        {}
      );
      expect(result.find((r) => r.label === 'EMA Alignment').earned).toBe(15);
    });

    it('awards 8 pts for bullish EMA', () => {
      const result = inferScoreBreakdown({ ema_signal: 'bullish' }, {});
      expect(result.find((r) => r.label === 'EMA Alignment').earned).toBe(8);
    });

    it('awards 8 pts for correlated MACD cross (EMA cross + MACD > 0)', () => {
      const result = inferScoreBreakdown(
        { ema_signal: 'bullish_cross', macd: 1.0 },
        {}
      );
      expect(result.find((r) => r.label === 'MACD').earned).toBe(8);
    });

    it('awards 10 pts for MACD > 0 in bullish regime', () => {
      const result = inferScoreBreakdown(
        { ema_signal: 'bullish', macd: 1.0 },
        {}
      );
      expect(result.find((r) => r.label === 'MACD').earned).toBe(10);
    });

    it('awards 5 pts for MACD < 0 in bullish regime', () => {
      const result = inferScoreBreakdown(
        { ema_signal: 'bullish_pullback', macd: -1.0 },
        {}
      );
      expect(result.find((r) => r.label === 'MACD').earned).toBe(5);
    });

    it('awards 15 pts for RSI recovery', () => {
      const result = inferScoreBreakdown(
        { rsi_signal: 'bullish_recovery' },
        {}
      );
      expect(result.find((r) => r.label === 'RSI').earned).toBe(15);
    });

    it('awards 10 pts for RSI crossing', () => {
      const result = inferScoreBreakdown(
        { rsi_signal: 'bullish_crossing' },
        {}
      );
      expect(result.find((r) => r.label === 'RSI').earned).toBe(10);
    });

    it('awards 15 pts for Volume breakout', () => {
      const result = inferScoreBreakdown({ volume_breakout: true }, {});
      expect(result.find((r) => r.label === 'Volume').earned).toBe(15);
    });

    it('awards Trend Quality points correctly', () => {
      const result = inferScoreBreakdown({ adx: 35, momentum_3m: 20 }, {});
      expect(result.find((r) => r.label === 'Trend Quality').earned).toBe(5); // 3 (ADX) + 2 (Mom) = 5
    });

    it('caps Trend Quality at 5 points', () => {
      const result = inferScoreBreakdown({ adx: 40, momentum_3m: 30 }, {});
      expect(result.find((r) => r.label === 'Trend Quality').earned).toBe(5);
    });
  });

  describe('Pledge rules', () => {
    it('awards 5 pts for 0 pledge', () => {
      const result = inferScoreBreakdown(mockSignal, { pledged_percent: 0 });
      expect(result.find((r) => r.label === 'Pledge').earned).toBe(5);
    });

    it('awards 3 pts for < 10% pledge', () => {
      const result = inferScoreBreakdown(mockSignal, { pledged_percent: 0.05 });
      expect(result.find((r) => r.label === 'Pledge').earned).toBe(3);
    });

    it('awards 1 pt for < 20% pledge', () => {
      const result = inferScoreBreakdown(mockSignal, { pledged_percent: 0.15 });
      expect(result.find((r) => r.label === 'Pledge').earned).toBe(1);
    });

    it('awards 0 pts for >= 20% pledge', () => {
      const result = inferScoreBreakdown(mockSignal, { pledged_percent: 0.25 });
      expect(result.find((r) => r.label === 'Pledge').earned).toBe(0);
    });
  });
});
