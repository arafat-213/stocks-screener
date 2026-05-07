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
        background: { type: ColorType.Solid, color: isDark ? '#161616' : '#FFFFFF' },
        textColor: isDark ? '#FFFFFF' : '#111827',
      },
      grid: {
        vertLines: { color: isDark ? '#1F1F1F' : '#F0F2F1' },
        horzLines: { color: isDark ? '#1F1F1F' : '#F0F2F1' },
      },
      width: chartContainerRef.current.clientWidth,
      height: containerHeight,
      timeScale: {
        borderColor: isDark ? '#1F1F1F' : '#F0F2F1',
      },
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
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
          background: { color: isDark ? '#161616' : '#FFFFFF' },
          textColor: isDark ? '#FFFFFF' : '#111827',
        },
        grid: {
          vertLines: { color: isDark ? '#1F1F1F' : '#F0F2F1' },
          horzLines: { color: isDark ? '#1F1F1F' : '#F0F2F1' },
        }
      });
    }
  }, [isDark]);

  return <div ref={chartContainerRef} style={{ width: '100%' }} />;
};

export default CandlestickChart;
