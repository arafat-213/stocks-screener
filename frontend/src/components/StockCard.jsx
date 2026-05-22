import { Link } from 'react-router-dom';
import WatchlistStar from './WatchlistStar';
import SetupBadge from './SetupBadge';

const StockCard = ({ stock, isWatched, onToggleWatch }) => {
  const {
    symbol,
    name,
    sector,
    close_price,
    price_change_pct,
    timeframes,
    fundamentals,
    confluence_count,
    setup
  } = stock;

  const daily = timeframes?.D || {};
  const isPositive = price_change_pct >= 0;

  const renderTimeframe = (tf, label) => {
    const data = timeframes?.[tf];
    const isBullish = data?.is_bullish;
    return (
      <div className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-bold ${
        isBullish ? 'bg-emerald-500/10 text-bullish' : 'bg-rose-500/10 text-bearish'
      }`}>
        <span className="opacity-80">{label}</span>
        <span className="text-[10px]">{isBullish ? '▲' : '▼'}</span>
      </div>
    );
  };

  const formatMCap = (val) => {
    if (!val) return '-';
    // Absolute INR to Crore conversion
    const crores = val / 10000000;
    if (crores >= 100000) return `${(crores / 100000).toFixed(2)}L Cr`;
    if (crores >= 1000) return `${(crores / 1000).toFixed(1)}k Cr`;
    return `${crores.toFixed(0)} Cr`;
  };

  const getConfluenceStyles = (count) => {
    switch (count) {
      case 3:
        return 'bg-emerald-500/15 text-bullish border-emerald-500/20';
      case 2:
        return 'bg-amber-500/15 text-amber-500 border-amber-500/20';
      case 1:
        return 'bg-bg-secondary text-text-muted border-border';
      default:
        return 'bg-bg-secondary text-text-muted border-border opacity-50';
    }
  };

  return (
    <Link to={`/stocks/${symbol}`} className="no-underline text-inherit block">
      <div className="bg-bg-secondary border border-border rounded-xl p-4 flex flex-col gap-4 transition-all duration-200 shadow-sm hover:-translate-y-0.5 hover:border-bullish hover:shadow-lg">
        <div className="flex justify-between items-start">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight text-text">{symbol.replace('.NS', '')}</span>
              <SetupBadge setup={setup} />
              <span className="text-[10px] font-semibold uppercase bg-bg-elevated text-text-muted px-1.5 py-0.5 rounded tracking-wider">{sector}</span>
              <WatchlistStar symbol={symbol} isWatched={isWatched} onToggle={onToggleWatch} />
            </div>
            <div className="text-[11px] text-text-muted truncate max-w-[160px]">{name}</div>
          </div>
          <div className="text-right flex flex-col gap-0.5">
            <div className="font-bold text-base font-mono text-text">₹{close_price?.toLocaleString('en-IN') || '-'}</div>
            <div className={`text-xs font-semibold ${isPositive ? 'text-bullish' : 'text-bearish'}`}>
              {isPositive ? '+' : ''}{price_change_pct?.toFixed(2)}%
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center bg-bg-elevated p-2.5 rounded-lg border border-border">
          <div className={`text-xs font-bold px-2.5 py-1 rounded-full border ${getConfluenceStyles(confluence_count)}`}>
            {confluence_count}/3 Confluence
          </div>
          <div className="flex gap-2">
            {renderTimeframe('D', 'D')}
            {renderTimeframe('W', 'W')}
            {renderTimeframe('M', 'M')}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-2 border-b border-border pb-2.5">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">Score</span>
              <span className="text-sm font-mono font-bold text-text">{daily.score || '-'}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">RSI</span>
              <span className="text-sm font-mono font-medium text-text">{daily.rsi?.toFixed(1) || '-'}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">EMA</span>
              <span className={`text-sm font-mono font-medium ${daily.ema_signal?.toLowerCase() === 'bullish' ? 'text-bullish' : 'text-bearish'}`}>
                {daily.ema_signal || '-'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">P/E</span>
              <span className="text-sm font-mono font-medium text-text">{fundamentals.pe?.toFixed(1) || '-'}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">ROE</span>
              <span className="text-sm font-mono font-medium text-text">{fundamentals.roe ? `${fundamentals.roe.toFixed(1)}%` : '-'}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">MCap</span>
              <span className="text-sm font-mono font-medium text-text">{formatMCap(fundamentals.market_cap)}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 mt-1">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">RS Score</span>
              <span className="text-sm font-mono font-bold text-primary">{daily.rs_score?.toFixed(0) || '-'}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">ADX</span>
              <span className="text-sm font-mono font-medium text-text">{daily.adx?.toFixed(1) || '-'}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">52W High</span>
              <span className={`text-sm font-mono font-medium ${Math.abs(daily.pct_from_52wh) < 5 ? 'text-bullish' : 'text-text'}`}>
                {daily.pct_from_52wh != null ? `${daily.pct_from_52wh.toFixed(1)}%` : '-'}
              </span>
            </div>
          </div>
          
          {daily.volume_breakout && (
            <div className="flex items-center gap-2 bg-blue-500/10 text-primary text-[10px] font-bold px-3 py-1.5 rounded-md uppercase tracking-widest mt-2">
              <span className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse shadow-[0_0_0_rgba(59,130,246,0.4)]"></span>
              Volume Breakout
            </div>
          )}
        </div>
      </div>
    </Link>
  );
};

export default StockCard;
