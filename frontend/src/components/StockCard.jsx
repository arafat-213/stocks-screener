
import { Link } from 'react-router-dom';
import './StockCard.css';

const StockCard = ({ stock }) => {
  const {
    symbol,
    name,
    sector,
    close_price,
    price_change_pct,
    timeframes,
    fundamentals,
    confluence_count
  } = stock;

  const daily = timeframes?.D || {};
  const isPositive = price_change_pct >= 0;

  const renderTimeframe = (tf, label) => {
    const data = timeframes?.[tf];
    const isBullish = data?.is_bullish;
    return (
      <div className={`tf-indicator ${isBullish ? 'bullish' : 'bearish'}`}>
        <span className="tf-label">{label}</span>
        <span className="tf-status">{isBullish ? '▲' : '▼'}</span>
      </div>
    );
  };

  const formatMCap = (val) => {
    if (!val) return '-';
    if (val >= 100000) return `${(val / 100000).toFixed(1)}L Cr`;
    if (val >= 1000) return `${(val / 1000).toFixed(1)}k Cr`;
    return `${val.toFixed(0)} Cr`;
  };

  return (
    <Link to={`/stocks/${symbol}`} className="stock-card-link">
      <div className="stock-card">
        <div className="card-top">
          <div className="symbol-section">
            <div className="symbol-row">
              <span className="stock-symbol">{symbol.replace('.NS', '')}</span>
              <span className="sector-tag">{sector}</span>
            </div>
            <div className="stock-name">{name}</div>
          </div>
          <div className="price-section">
            <div className="price-value">₹{close_price?.toLocaleString('en-IN') || '-'}</div>
            <div className={`price-change ${isPositive ? 'positive' : 'negative'}`}>
              {isPositive ? '+' : ''}{price_change_pct?.toFixed(2)}%
            </div>
          </div>
        </div>

        <div className="confluence-section">
          <div className={`confluence-badge confluence-${confluence_count}`}>
            {confluence_count}/3 Confluence
          </div>
          <div className="tf-indicators">
            {renderTimeframe('D', 'D')}
            {renderTimeframe('W', 'W')}
            {renderTimeframe('M', 'M')}
          </div>
        </div>

        <div className="metrics-section">
          <div className="metrics-row technical">
            <div className="metric-item">
              <span className="m-label">Score</span>
              <span className="m-value bold">{daily.score || '-'}</span>
            </div>
            <div className="metric-item">
              <span className="m-label">RSI</span>
              <span className="m-value">{daily.rsi?.toFixed(1) || '-'}</span>
            </div>
            <div className="metric-item">
              <span className="m-label">EMA</span>
              <span className={`m-value ${daily.ema_signal?.toLowerCase() === 'bullish' ? 'positive' : 'negative'}`}>
                {daily.ema_signal || '-'}
              </span>
            </div>
          </div>

          <div className="metrics-row fundamental">
            <div className="metric-item">
              <span className="m-label">P/E</span>
              <span className="m-value">{fundamentals.pe?.toFixed(1) || '-'}</span>
            </div>
            <div className="metric-item">
              <span className="m-label">ROE</span>
              <span className="m-value">{fundamentals.roe ? `${fundamentals.roe.toFixed(1)}%` : '-'}</span>
            </div>
            <div className="metric-item">
              <span className="m-label">MCap</span>
              <span className="m-value">{formatMCap(fundamentals.market_cap)}</span>
            </div>
          </div>

          <div className="metrics-row technical-extra">
            <div className="metric-item">
              <span className="m-label">RS Score</span>
              <span className="m-value bold text-primary">{daily.rs_score?.toFixed(0) || '-'}</span>
            </div>
            <div className="metric-item">
              <span className="m-label">ADX</span>
              <span className="m-value">{daily.adx?.toFixed(1) || '-'}</span>
            </div>
            <div className="metric-item">
              <span className="m-label">52W High</span>
              <span className={`m-value ${Math.abs(daily.pct_from_52wh) < 5 ? 'positive' : ''}`}>
                {daily.pct_from_52wh != null ? `${daily.pct_from_52wh.toFixed(1)}%` : '-'}
              </span>
            </div>
          </div>
          
          {daily.volume_breakout && (
            <div className="volume-badge">
              <span className="pulse-dot"></span>
              Volume Breakout
            </div>
          )}
        </div>
      </div>
    </Link>
  );
};

export default StockCard;
