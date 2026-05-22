import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, Info, Activity, Loader2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
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
  const { data, loading, error } = useFetch(fetchStockDetail, { deps: [symbol] });

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[80vh] gap-5 text-text-muted bg-background">
        <Loader2 className="animate-spin" size={48} />
        <p>Fetching stock data and technicals...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-[80vh] gap-5 text-text-muted bg-background">
        <ErrorBanner message={error || "Stock not found"} />
        <Link to="/" className="flex items-center gap-2 text-bullish no-underline font-medium transition-opacity hover:opacity-80 mt-4">
          <ArrowLeft size={18} /> Back to Dashboard
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
  const priceChangePct = prevOhlc?.close && prevOhlc.close !== 0 ? (priceChange / prevOhlc.close) * 100 : 0;
  const isPositive = priceChange >= 0;

  const renderScoreCard = (tf, label) => {
    const scoreData = latest_scores?.[tf];
    if (!scoreData) return (
      <div className="bg-bg-secondary rounded-lg p-5 border border-border" key={tf}>
        <h3 className="text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold">{label} Timeframe</h3>
        <div className="flex justify-between items-center">
          <div className="text-[42px] font-extrabold text-text-muted">--</div>
          <div className="text-right">
            <div className="inline-block px-3 py-1.5 rounded-lg text-sm font-bold bg-text-muted/10 text-text-muted">No Signal</div>
          </div>
        </div>
      </div>
    );

    const isBullish = scoreData.ema_signal?.toLowerCase() === 'bullish';

    return (
      <div className="bg-bg-secondary rounded-lg p-5 border border-border" key={tf}>
        <h3 className="text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold">{label} Timeframe</h3>
        <div className="flex justify-between items-center">
          <div className="text-[42px] font-extrabold text-text">{scoreData.score?.toFixed(1) || scoreData.score}</div>
          <div className="text-right">
            <div className={`inline-block px-3 py-1.5 rounded-lg text-sm font-bold ${isBullish ? 'bg-bullish/10 text-bullish' : 'bg-bearish/10 text-bearish'}`}>
              EMA: {scoreData.ema_signal}
            </div>
            <div className="mt-2 text-[12px] text-text-muted">
              RSI: {scoreData.rsi?.toFixed(1)}
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
    <div className="p-6 max-w-[1600px] mx-auto text-text bg-background min-h-screen">
      <Link to="/" className="flex items-center gap-2 text-bullish no-underline font-medium mb-6 transition-opacity hover:opacity-80">
        <ArrowLeft size={18} /> Back to Dashboard
      </Link>

      <header className="flex flex-col sm:flex-row justify-between items-start mb-8 gap-4 sm:gap-0">
        <div className="flex flex-col">
          <div className="flex items-baseline gap-3">
            <h1 className="text-[28px] sm:text-[36px] m-0 text-text font-extrabold">{symbol.replace('.NS', '')}</h1>
            <span className="bg-bg-elevated px-3 py-1 rounded-md text-sm text-text-muted border border-border">{sector}</span>
          </div>
          <div className="text-lg text-text-muted mt-1">{name}</div>
        </div>
        <div className="text-left sm:text-right">
          <div className="text-[28px] sm:text-[36px] font-extrabold text-text">₹{latestOhlc.close.toLocaleString('en-IN')}</div>
          <div className={`text-lg font-semibold mt-1 ${isPositive ? 'text-bullish' : 'text-bearish'}`}>
            {isPositive ? '+' : ''}{priceChange.toFixed(2)} ({isPositive ? '+' : ''}{priceChangePct.toFixed(2)}%)
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6 items-start">
        <div className="flex flex-col gap-6">
          <section className="bg-bg-secondary rounded-lg p-6 border border-border min-h-[400px]">
            <h2 className="text-lg font-bold flex items-center gap-2 mb-6 text-text">
              <TrendingUp size={20} /> Price Action
            </h2>
            <div className="h-[400px] lg:h-[calc(100vh-350px)] lg:min-h-[400px] w-full">
              <CandlestickChart data={ohlcv} isDark={isDark} containerHeight={500} />
            </div>
          </section>

          <section className="bg-bg-secondary rounded-lg p-6 border border-border">
            <h2 className="text-lg font-bold flex items-center gap-2 mb-6 text-text">
              <Activity size={20} /> Daily Score Trend (30D)
            </h2>
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={score_history}>
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#2B2B43" : "#E5E7EB"} />
                  <XAxis 
                    dataKey="date" 
                    stroke="var(--color-text-muted)" 
                    fontSize={12}
                    tickFormatter={(str) => {
                      const date = new Date(str);
                      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
                    }}
                  />
                  <YAxis stroke="var(--color-text-muted)" fontSize={12} domain={[0, 100]} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: 'var(--color-bg-secondary)', 
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text)',
                      borderRadius: '8px'
                    }}
                    itemStyle={{ color: 'var(--color-text)' }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="score" 
                    stroke="var(--color-bullish)" 
                    strokeWidth={3} 
                    dot={{ r: 4, fill: 'var(--color-bullish)' }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        </div>

        <div className="flex flex-col gap-5 lg:sticky lg:top-6">
          <div className="flex flex-col gap-5">
            <TradingPlan setup={setup} />
            <h2 className="text-lg font-bold flex items-center gap-2 mb-1 text-text">
              <Activity size={20} /> Technical Confluence
            </h2>
            {renderScoreCard('D', 'Daily')}
            {renderScoreCard('W', 'Weekly')}
            {renderScoreCard('M', 'Monthly')}

            <section className="bg-bg-secondary rounded-lg p-5 border border-border">
              <h3 className="text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold">
                <Activity size={16} className="inline mr-1" /> Technical Insights
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">RS Score</span>
                  <span className="text-[15px] font-bold text-text">{dailyScore?.rs_score?.toFixed(1) || 'N/A'}</span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">ADX</span>
                  <span className="text-[15px] font-bold text-text">{dailyScore?.adx?.toFixed(1) || 'N/A'}</span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">Mom. (1m)</span>
                  <span className={`text-[15px] font-bold ${(dailyScore?.momentum_1m || 0) >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {dailyScore?.momentum_1m ? `${(dailyScore.momentum_1m).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">Mom. (3m)</span>
                  <span className={`text-[15px] font-bold ${(dailyScore?.momentum_3m || 0) >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {dailyScore?.momentum_3m ? `${(dailyScore.momentum_3m).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">Mom. (6m)</span>
                  <span className={`text-[15px] font-bold ${(dailyScore?.momentum_6m || 0) >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {dailyScore?.momentum_6m ? `${(dailyScore.momentum_6m).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">Mom. (12m)</span>
                  <span className={`text-[15px] font-bold ${(dailyScore?.momentum_12m || 0) >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {dailyScore?.momentum_12m ? `${(dailyScore.momentum_12m).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
              </div>
            </section>

            <div className="bg-bg-secondary rounded-lg p-5 border border-border">
              <h3 className="text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold">
                <Info size={16} className="inline mr-1" /> Fundamental Data
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">P/E Ratio</span>
                  <span className="text-[15px] font-bold text-text">{fundamentals.pe?.toFixed(1) || 'N/A'}</span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">ROE</span>
                  <span className="text-[15px] font-bold text-text">{fundamentals.roe ? `${(fundamentals.roe * 100).toFixed(1)}%` : 'N/A'}</span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">D/E Ratio</span>
                  <span className="text-[15px] font-bold text-text">{fundamentals.debt_equity?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="bg-bg-elevated p-3 rounded-md border border-border">
                  <span className="block text-[11px] text-text-muted mb-1 uppercase font-semibold">Market Cap</span>
                  <span className="text-[15px] font-bold text-text">{formatMarketCap(fundamentals.market_cap)}</span>
                </div>
              </div>
            </div>

            {dailyScore && (
              <div className="bg-bg-secondary rounded-lg p-5 border border-border">
                <h3 className="text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold">Score Breakdown</h3>
                <ScoreBreakdown breakdown={breakdown} totalScore={dailyScore.score} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StockDetail;
