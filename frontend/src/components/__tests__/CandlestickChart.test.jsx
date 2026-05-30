import { render } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import CandlestickChart from '../CandlestickChart';
import * as lightweightCharts from 'lightweight-charts';

vi.mock('lightweight-charts', () => {
  const mockPriceLine = {
    applyOptions: vi.fn(),
  };

  const mockSeries = {
    setData: vi.fn(),
    createPriceLine: vi.fn(() => mockPriceLine),
    removePriceLine: vi.fn(),
  };

  const mockChart = {
    applyOptions: vi.fn(),
    addSeries: vi.fn(() => mockSeries),
    remove: vi.fn(),
    timeScale: vi.fn(() => ({
      fitContent: vi.fn(),
    })),
  };

  return {
    createChart: vi.fn(() => mockChart),
    ColorType: { Solid: 'Solid' },
    CandlestickSeries: 'CandlestickSeries',
    LineStyle: { Dashed: 2 },
  };
});

describe('CandlestickChart EMA Price Lines', () => {
  const mockData = [
    { time: '2023-01-01', open: 100, high: 110, low: 90, close: 105 },
    { time: '2023-01-02', open: 105, high: 115, low: 100, close: 110 },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing', () => {
    render(<CandlestickChart data={mockData} isDark={false} />);
    expect(lightweightCharts.createChart).toHaveBeenCalled();
  });

  it('creates price lines when emaLevels are provided', () => {
    const emaLevels = {
      ema5: 108.5,
      ema20: 102.0,
    };

    render(
      <CandlestickChart data={mockData} isDark={false} emaLevels={emaLevels} />
    );

    const mockChart = vi.mocked(lightweightCharts.createChart).mock.results[0]
      .value;
    const mockSeries = mockChart.addSeries.mock.results[0].value;

    expect(mockSeries.createPriceLine).toHaveBeenCalledTimes(2);
    expect(mockSeries.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({
        price: 108.5,
        title: 'EMA 5',
        color: '#3B82F6',
      })
    );
    expect(mockSeries.createPriceLine).toHaveBeenCalledWith(
      expect.objectContaining({
        price: 102.0,
        title: 'EMA 20',
        color: '#10B981',
      })
    );
  });

  it('removes old price lines when emaLevels change', () => {
    const { rerender } = render(
      <CandlestickChart
        data={mockData}
        isDark={false}
        emaLevels={{ ema5: 100 }}
      />
    );

    const mockChart = vi.mocked(lightweightCharts.createChart).mock.results[0]
      .value;
    const mockSeries = mockChart.addSeries.mock.results[0].value;

    expect(mockSeries.createPriceLine).toHaveBeenCalledTimes(1);

    rerender(
      <CandlestickChart
        data={mockData}
        isDark={false}
        emaLevels={{ ema5: 105 }}
      />
    );

    expect(mockSeries.removePriceLine).toHaveBeenCalled();
    expect(mockSeries.createPriceLine).toHaveBeenCalledTimes(2);
  });
});
