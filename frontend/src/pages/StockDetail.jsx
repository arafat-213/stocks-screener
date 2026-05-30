import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, Activity, Loader2 } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { getStockDetail } from '../api/client';
import { useTheme } from '../hooks/useTheme';
import { useFetch } from '../hooks/useFetch';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import CandlestickChart from '../components/CandlestickChart';
import ScoreBreakdown from '../components/ScoreBreakdown';
import TradingPlan from '../components/TradingPlan';
import { inferScoreBreakdown } from '../utils/scoreBreakdown';
import { useCallback } from 'react';

const StockDetail = () => {
  const { symbol } = useParams();
  const { isDark } = useTheme();
  const fetchStockDetail = useCallback(() => getStockDetail(symbol), [symbol]);
  const { data, loading, error } = useFetch(fetchStockDetail, {
    deps: [symbol],
  });

  if (loading) {
    return (
      <div className='flex flex-col items-center justify-center h-[80vh] gap-5 text-text-muted bg-background'>
        <Loader2 className='animate-spin' size={48} />
        <p>Fetching stock data and technicals...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className='flex flex-col items-center justify-center h-[80vh] gap-5 text-text-muted bg-background px-6 text-center'>
        <ErrorBanner message={error || 'Stock not found'} />
        <Link
          to='/'
          className='hidden lg:inline-flex items-center gap-2 text-slate-500 hover:text-blue-500 no-underline font-black transition-colors group'
        >
          <ArrowLeft
            size={20}
            className='group-hover:-translate-x-1 transition-transform'
          />
          <span className='text-xs uppercase tracking-[0.2em]'>
            Return to Market Control
          </span>
        </Link>
      </div>
    );
  }

  const ohlcv = data?.ohlcv || [];
  const latest_scores = data?.scores || {};
  const score_history = data?.score_history || [];
  const name = data?.name || '';
  const sector = data?.sector || '';
  const fundamentals = data?.fundamentals || {};
  const setup = data?.setup;

  const dailyScore = latest_scores?.['D'];
  const breakdown = inferScoreBreakdown(dailyScore, fundamentals);

  const latestOhlc = ohlcv.length > 0 ? ohlcv[ohlcv.length - 1] : { close: 0 };
  const prevOhlc = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : latestOhlc;
  const priceChange = latestOhlc.close - (prevOhlc?.close || 0);
  const priceChangePct =
    prevOhlc?.close && prevOhlc.close !== 0
      ? (priceChange / prevOhlc.close) * 100
      : 0;
  const isPositive = priceChange >= 0;

  const renderScoreCard = (tf, label) => {
    const scoreData = latest_scores?.[tf];
    if (!scoreData)
      return (
        <div
          className='bg-bg-secondary rounded-lg p-5 border border-border'
          key={tf}
        >
          <h3 className='text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold'>
            {label} Timeframe
          </h3>
          <div className='flex justify-between items-center'>
            <div className='text-[42px] font-extrabold text-text-muted'>--</div>
            <div className='text-right'>
              <div className='inline-block px-3 py-1.5 rounded-lg text-sm font-bold bg-text-muted/10 text-text-muted'>
                No Signal
              </div>
            </div>
          </div>
        </div>
      );

    const isBullish = scoreData.ema_signal?.toLowerCase() === 'bullish';

    return (
      <div
        className='bg-bg-secondary rounded-xl p-6 border-2 border-border shadow-sm hover:border-blue-500/30 transition-colors'
        key={tf}
      >
        <h3 className='text-[11px] text-slate-500 dark:text-slate-400 mb-4 uppercase tracking-[0.2em] font-black'>
          {label} Timeframe
        </h3>
        <div className='flex justify-between items-center'>
          <div
            className={`text-5xl font-black ${scoreData.score >= 70 ? 'text-green-500' : scoreData.score >= 50 ? 'text-blue-500' : 'text-text'}`}
          >
            {scoreData.score?.toFixed(1) || scoreData.score}
          </div>
          <div className='text-right flex flex-col gap-2'>
            <div
              className={`inline-block px-3 py-1.5 rounded-lg text-xs font-black uppercase tracking-wider ${isBullish ? 'bg-green-500 text-white shadow-lg shadow-green-500/20' : 'bg-red-500 text-white shadow-lg shadow-red-500/20'}`}
            >
              {scoreData.ema_signal}
            </div>
            <div className='text-[13px] font-mono font-bold text-slate-500 dark:text-slate-400'>
              RSI:{' '}
              <span
                className={
                  scoreData.rsi <= 30
                    ? 'text-green-500'
                    : scoreData.rsi >= 70
                      ? 'text-red-500'
                      : 'text-text'
                }
              >
                {scoreData.rsi?.toFixed(1)}
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const formatMarketCap = (val) => {
    if (!val) return 'N/A';
    const crores = (val / 10000000).toFixed(0);
    return `₹${Number(crores).toLocaleString('en-IN')} Cr`;
  };

  return (
    <div className='w-full text-text animate-fade-in pb-20'>
      <Link
        to='/'
        className='hidden lg:inline-flex items-center gap-2 text-slate-500 hover:text-blue-500 no-underline font-bold mb-8 transition-colors group'
      >
        <ArrowLeft
          size={20}
          className='group-hover:-translate-x-1 transition-transform'
        />
        <span className='text-sm uppercase tracking-widest'>
          Back to Dashboard
        </span>
      </Link>

      <header className='flex flex-col sm:flex-row justify-between items-start mb-10 gap-6 sm:gap-0 mt-4 lg:mt-0'>
        <div className='flex flex-col gap-2 w-full sm:w-auto'>
          <div className='flex items-center gap-3 sm:gap-4 flex-wrap'>
            <h1 className='text-3xl sm:text-5xl m-0 text-text font-black tracking-tighter'>
              {symbol.replace('.NS', '')}
            </h1>
            <span className='bg-blue-500 text-white px-2.5 py-1 rounded-lg text-[10px] sm:text-xs font-black uppercase tracking-widest shadow-lg shadow-blue-500/20'>
              {sector}
            </span>
          </div>
          <div className='text-lg sm:text-xl text-slate-500 dark:text-slate-400 font-medium'>
            {name}
          </div>
        </div>
        <div className='text-left sm:text-right flex flex-col gap-1.5 sm:gap-2 w-full sm:w-auto'>
          <div className='text-3xl sm:text-5xl font-black font-mono text-text tracking-tighter'>
            ₹{latestOhlc.close.toLocaleString('en-IN')}
          </div>
          <div
            className={`text-lg sm:text-xl font-black flex items-center gap-2 sm:justify-end ${isPositive ? 'text-green-500' : 'text-red-500'}`}
          >
            <span>{isPositive ? '▲' : '▼'}</span>
            <span>
              {isPositive ? '+' : ''}
              {priceChange.toFixed(2)} ({isPositive ? '+' : ''}
              {priceChangePct.toFixed(2)}%)
            </span>
          </div>
        </div>
      </header>

      <div className='grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-8 items-start'>
        <div className='flex flex-col gap-8'>
          <section className='bg-bg-secondary rounded-2xl p-8 border-2 border-border shadow-sm'>
            <h2 className='text-xl font-black flex items-center gap-3 mb-8 text-text uppercase tracking-tight'>
              <TrendingUp size={24} className='text-blue-500' /> Price Action
            </h2>
            <div className='h-[400px] lg:h-[600px] w-full rounded-xl overflow-hidden border border-border'>
              <CandlestickChart
                data={ohlcv}
                isDark={isDark}
                containerHeight={600}
              />
            </div>
          </section>

          <section className='bg-bg-secondary rounded-2xl p-8 border-2 border-border shadow-sm'>
            <h2 className='text-xl font-black flex items-center gap-3 mb-8 text-text uppercase tracking-tight'>
              <div className='bg-blue-500/10 p-2 rounded-lg'>
                <Activity size={24} className='text-blue-500' />
              </div>
              Daily Score Trend
            </h2>
            <div className='w-full h-[350px] min-h-[350px]'>
              <ResponsiveContainer width='100%' height='100%'>
                <LineChart data={score_history}>
                  <CartesianGrid
                    strokeDasharray='3 3'
                    stroke={isDark ? '#1E293B' : '#E2E8F0'}
                    vertical={false}
                  />
                  <XAxis
                    dataKey='date'
                    stroke='#64748B'
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    dy={10}
                    tickFormatter={(str) => {
                      const date = new Date(str);
                      return date.toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                      });
                    }}
                  />
                  <YAxis
                    stroke='#64748B'
                    fontSize={12}
                    domain={[0, 100]}
                    tickLine={false}
                    axisLine={false}
                    dx={-10}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: isDark ? '#0F172A' : '#FFFFFF',
                      borderColor: isDark ? '#1E293B' : '#E2E8F0',
                      color: isDark ? '#F8FAFC' : '#0F172A',
                      borderRadius: '12px',
                      boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
                      border: '2px solid',
                    }}
                    itemStyle={{ fontWeight: '800' }}
                  />
                  <Line
                    type='monotone'
                    dataKey='score'
                    stroke='#3B82F6'
                    strokeWidth={4}
                    dot={{ r: 0 }}
                    activeDot={{ r: 6, strokeWidth: 0, fill: '#3B82F6' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        </div>

        <div className='flex flex-col gap-6 lg:sticky lg:top-6'>
          <TradingPlan setup={setup} />

          <div className='flex flex-col gap-4'>
            <h2 className='text-xl font-black flex items-center gap-3 text-text uppercase tracking-tight mb-2'>
              <div className='bg-blue-500/10 p-2 rounded-lg'>
                <Activity size={24} className='text-blue-500' />
              </div>
              Technical Context
            </h2>
            {renderScoreCard('D', 'Daily')}
            {renderScoreCard('W', 'Weekly')}
            {renderScoreCard('M', 'Monthly')}

            <section className='bg-bg-secondary rounded-2xl p-6 border-2 border-border shadow-sm'>
              <h3 className='text-[11px] text-slate-500 dark:text-slate-400 mb-6 uppercase tracking-[0.2em] font-black'>
                Technical Insights
              </h3>
              <div className='grid grid-cols-2 gap-4'>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    RS Score
                  </span>
                  <span className='text-lg font-black text-blue-600 dark:text-blue-400'>
                    {dailyScore?.rs_score?.toFixed(1) || 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    ADX
                  </span>
                  <span className='text-lg font-black text-text'>
                    {dailyScore?.adx?.toFixed(1) || 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    Mom. (1m)
                  </span>
                  <span
                    className={`text-lg font-black ${(dailyScore?.momentum_1m || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}
                  >
                    {dailyScore?.momentum_1m
                      ? `${dailyScore.momentum_1m.toFixed(1)}%`
                      : 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    Resistance
                  </span>
                  <span className='text-lg font-black text-text'>
                    {dailyScore?.resistance
                      ? `₹${dailyScore.resistance.toFixed(1)}`
                      : 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border col-span-2'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-2 uppercase font-black'>
                    52W High/Low Range
                  </span>
                  <div className='flex items-center justify-between font-mono font-black'>
                    <span className='text-green-500 text-sm'>
                      H: ₹
                      {dailyScore?.week52_high?.toLocaleString('en-IN') ||
                        'N/A'}
                    </span>
                    <div className='flex-1 mx-4 h-1 bg-slate-200 dark:bg-slate-800 rounded-full relative'>
                      <div
                        className='absolute top-1/2 -translate-y-1/2 w-2 h-2 bg-blue-500 rounded-full shadow-lg shadow-blue-500/50'
                        style={{ left: '60%' }}
                      ></div>
                    </div>
                    <span className='text-red-500 text-sm'>
                      L: ₹
                      {dailyScore?.week52_low?.toLocaleString('en-IN') || 'N/A'}
                    </span>
                  </div>
                </div>
                {dailyScore?.volume_breakout && (
                  <div className='bg-blue-600 p-4 rounded-xl border border-blue-700 col-span-2 flex items-center justify-between shadow-lg shadow-blue-500/20 animate-pulse'>
                    <span className='text-[10px] text-white uppercase font-black tracking-widest'>
                      Volume Breakout
                    </span>
                    <span className='text-white font-black'>DETECTED</span>
                  </div>
                )}
              </div>
            </section>

            <div className='bg-bg-secondary rounded-2xl p-6 border-2 border-border shadow-sm'>
              <h3 className='text-[11px] text-slate-500 dark:text-slate-400 mb-6 uppercase tracking-[0.2em] font-black'>
                Fundamental Health
              </h3>
              <div className='grid grid-cols-2 gap-4'>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    P/E Ratio
                  </span>
                  <span className='text-lg font-black text-text'>
                    {fundamentals.pe?.toFixed(1) || 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    ROE %
                  </span>
                  <span
                    className={`text-lg font-black ${fundamentals.roe > 0.15 ? 'text-green-500' : 'text-text'}`}
                  >
                    {fundamentals.roe
                      ? `${(fundamentals.roe * 100).toFixed(1)}%`
                      : 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    D/E Ratio
                  </span>
                  <span
                    className={`text-lg font-black ${fundamentals.debt_equity > 1.5 ? 'text-red-500' : 'text-text'}`}
                  >
                    {fundamentals.debt_equity?.toFixed(2) || 'N/A'}
                  </span>
                </div>
                <div className='bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-border'>
                  <span className='block text-[10px] text-slate-500 dark:text-slate-400 mb-1 uppercase font-black'>
                    Market Cap
                  </span>
                  <span className='text-lg font-black text-text truncate'>
                    {formatMarketCap(fundamentals.market_cap)}
                  </span>
                </div>
              </div>
            </div>

            {dailyScore && (
              <div className='bg-bg-secondary rounded-2xl p-6 border-2 border-border shadow-sm'>
                <h3 className='text-[11px] text-slate-500 dark:text-slate-400 mb-6 uppercase tracking-[0.2em] font-black'>
                  Score Attribution
                </h3>
                <ScoreBreakdown
                  breakdown={breakdown}
                  totalScore={dailyScore.score}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StockDetail;
