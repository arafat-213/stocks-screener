import { useEffect, useRef, memo } from 'react';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  LineStyle,
} from 'lightweight-charts';

const CandlestickChart = memo(
  ({ data, isDark, containerHeight = 400, emaLevels = {} }) => {
    const chartContainerRef = useRef();
    const chartRef = useRef();
    const seriesRef = useRef();

    useEffect(() => {
      if (!data || data.length === 0 || !chartContainerRef.current) return;

      const handleResize = () => {
        if (chartRef.current) {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth,
          });
        }
      };

      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: {
            type: ColorType.Solid,
            color: isDark ? '#020617' : '#F8FAFC',
          },
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
      seriesRef.current = candlestickSeries;

      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        chart.remove();
        chartRef.current = null;
        seriesRef.current = null;
      };
    }, [data, containerHeight, isDark]);

    useEffect(() => {
      if (!seriesRef.current || !emaLevels) return;

      const priceLines = [];
      const config = [
        { key: 'ema5', color: '#3B82F6', label: 'EMA 5' },
        { key: 'ema13', color: '#F59E0B', label: 'EMA 13' },
        { key: 'ema20', color: '#10B981', label: 'EMA 20' },
        { key: 'ema26', color: '#EF4444', label: 'EMA 26' },
      ];

      config.forEach(({ key, color, label }) => {
        if (emaLevels[key]) {
          const line = seriesRef.current.createPriceLine({
            price: emaLevels[key],
            color: color,
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: label,
          });
          priceLines.push(line);
        }
      });

      return () => {
        if (seriesRef.current) {
          priceLines.forEach((line) => seriesRef.current.removePriceLine(line));
        }
      };
    }, [emaLevels, data]); // Add data to deps to ensure lines are re-added if series is recreated

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
          },
        });
      }
    }, [isDark]);

    return <div ref={chartContainerRef} className='w-full' />;
  }
);

export default CandlestickChart;
