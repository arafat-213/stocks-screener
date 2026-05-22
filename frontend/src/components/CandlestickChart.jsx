import { useEffect, useRef } from 'react';
import { createChart, ColorType, CandlestickSeries } from 'lightweight-charts';

const CandlestickChart = ({ data, isDark, containerHeight = 400 }) => {
  const chartContainerRef = useRef();
  const chartRef = useRef();

  useEffect(() => {
    if (!data || data.length === 0 || !chartContainerRef.current) return;

    const handleResize = () => {
      if (chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: isDark ? '#020617' : '#F8FAFC' },
        textColor: isDark ? '#F8FAFC' : '#0F172A',
      },
      grid: {
        vertLines: { color: isDark ? '#1E293B' : '#E2E8F0' },
        horzLines: { color: isDark ? '#1E293B' : '#E2E8F0' },
      },
      width: chartContainerRef.current.clientWidth,
      height: containerHeight,
      timeScale: {
        borderColor: isDark ? '#1E293B' : '#E2E8F0',
      },
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22C55E',
      downColor: '#EF4444',
      borderVisible: false,
      wickUpColor: '#22C55E',
      wickDownColor: '#EF4444',
    });

    candlestickSeries.setData(data);

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data, containerHeight, isDark]);

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.applyOptions({
        layout: {
          background: { color: isDark ? '#020617' : '#F8FAFC' },
          textColor: isDark ? '#F8FAFC' : '#0F172A',
        },
        grid: {
          vertLines: { color: isDark ? '#1E293B' : '#E2E8F0' },
          horzLines: { color: isDark ? '#1E293B' : '#E2E8F0' },
        }
      });
    }
  }, [isDark]);

  return <div ref={chartContainerRef} className="w-full" />;
};

export default CandlestickChart;
