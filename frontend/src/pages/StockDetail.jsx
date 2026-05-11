import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, Info, Activity, Loader2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { getStockDetail } from '../api/client';
import { useTheme } from '../hooks/useTheme';
import { useFetch } from '../hooks/useFetch';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import CandlestickChart from '../components/CandlestickChart';
import './StockDetail.css';
import { useCallback } from 'react';

const StockDetail = () => {
  const { symbol } = useParams();
  const { isDark } = useTheme();
  const fetchStockDetail = useCallback(() => getStockDetail(symbol), [symbol]);
  const { data, loading, error } = useFetch(fetchStockDetail, { deps: [symbol] });

  if (loading) {
    return (
      <div className="loading-container">
        <Loader2 className="animate-spin" size={48} />
        <p>Fetching stock data and technicals...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="loading-container">
        <ErrorBanner message={error || "Stock not found"} />
        <Link to="/" className="back-link" style={{ marginTop: '16px' }}>
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

  const latestOhlc = ohlcv.length > 0 ? ohlcv[ohlcv.length - 1] : { close: 0 };
  const prevOhlc = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : latestOhlc;
  const priceChange = latestOhlc.close - (prevOhlc?.close || 0);
  const priceChangePct = prevOhlc?.close && prevOhlc.close !== 0 ? (priceChange / prevOhlc.close) * 100 : 0;
  const isPositive = priceChange >= 0;

  const dailyScore = latest_scores?.['D'] || {};

  const renderScoreCard = (tf, label) => {
    const scoreData = latest_scores?.[tf];
    if (!scoreData) return (
      <div className="score-card" key={tf}>
        <h3>{label} Timeframe</h3>
        <div className="score-display">
          <div className="score-value" style={{ color: 'var(--color-text-muted)' }}>--</div>
          <div className="score-signals">
            <div className="signal-tag neutral">No Signal</div>
          </div>
        </div>
      </div>
    );

    const isBullish = scoreData.ema_signal?.toLowerCase() === 'bullish';

    return (
      <div className="score-card" key={tf}>
        <h3>{label} Timeframe</h3>
        <div className="score-display">
          <div className="score-value">{scoreData.score?.toFixed(1) || scoreData.score}</div>
          <div className="score-signals">
            <div className={`signal-tag ${isBullish ? 'bullish' : 'bearish'}`}>
              EMA: {scoreData.ema_signal}
            </div>
            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--color-text-muted)' }}>
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
    <div className="stock-detail-container">
      <Link to="/" className="back-link">
        <ArrowLeft size={18} /> Back to Dashboard
      </Link>

      <header className="detail-header">
        <div className="header-left">
          <div className="symbol-row">
            <h1>{symbol.replace('.NS', '')}</h1>
            <span className="sector-badge">{sector}</span>
          </div>
          <div className="stock-name">{name}</div>
        </div>
        <div className="header-right">
          <div className="current-price">₹{latestOhlc.close.toLocaleString('en-IN')}</div>
          <div className={`price-change ${isPositive ? 'positive' : 'negative'}`}>
            {isPositive ? '+' : ''}{priceChange.toFixed(2)} ({isPositive ? '+' : ''}{priceChangePct.toFixed(2)}%)
          </div>
        </div>
      </header>

      <div className="detail-grid">
        <div className="main-col">
          <section className="chart-section">
            <h2><TrendingUp size={20} /> Price Action</h2>
            <div className="chart-wrapper">
              <CandlestickChart data={ohlcv} isDark={isDark} containerHeight={500} />
            </div>
          </section>

          <section className="trend-section">
            <h2><Activity size={20} /> Daily Score Trend (30D)</h2>
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
                      color: 'var(--color-text)'
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

        <div className="side-col">
          <div className="confluence-panel">
            <h2><Activity size={20} /> Technical Confluence</h2>
            {renderScoreCard('D', 'Daily')}
            {renderScoreCard('W', 'Weekly')}
            {renderScoreCard('M', 'Monthly')}

            <section className="score-card">
              <h3><Activity size={16} /> Technical Insights</h3>
              <div className="fundamentals-grid">
                <div className="fundamental-item">
                  <span className="f-label">RS Score</span>
                  <span className="f-value">{dailyScore?.rs_score?.toFixed(1) || 'N/A'}</span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">ADX</span>
                  <span className="f-value">{dailyScore?.adx?.toFixed(1) || 'N/A'}</span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">Mom. (1m)</span>
                  <span className={`f-value ${(dailyScore?.momentum_1m || 0) >= 0 ? 'positive' : 'negative'}`}>
                    {dailyScore?.momentum_1m ? `${(dailyScore.momentum_1m * 100).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">Mom. (3m)</span>
                  <span className={`f-value ${(dailyScore?.momentum_3m || 0) >= 0 ? 'positive' : 'negative'}`}>
                    {dailyScore?.momentum_3m ? `${(dailyScore.momentum_3m * 100).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">Mom. (6m)</span>
                  <span className={`f-value ${(dailyScore?.momentum_6m || 0) >= 0 ? 'positive' : 'negative'}`}>
                    {dailyScore?.momentum_6m ? `${(dailyScore.momentum_6m * 100).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">Mom. (12m)</span>
                  <span className={`f-value ${(dailyScore?.momentum_12m || 0) >= 0 ? 'positive' : 'negative'}`}>
                    {dailyScore?.momentum_12m ? `${(dailyScore.momentum_12m * 100).toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
              </div>
            </section>

            <div className="score-card">
              <h3><Info size={16} /> Fundamental Data</h3>
              <div className="fundamentals-grid">
                <div className="fundamental-item">
                  <span className="f-label">P/E Ratio</span>
                  <span className="f-value">{fundamentals.pe?.toFixed(1) || 'N/A'}</span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">ROE</span>
                  <span className="f-value">{fundamentals.roe ? `${fundamentals.roe.toFixed(1)}%` : 'N/A'}</span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">D/E Ratio</span>
                  <span className="f-value">{fundamentals.debt_equity?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="fundamental-item">
                  <span className="f-label">Market Cap</span>
                  <span className="f-value">{formatMarketCap(fundamentals.market_cap)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StockDetail;
