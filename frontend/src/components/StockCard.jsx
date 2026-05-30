import { ShieldCheck, ShieldX, CircleAlert } from 'lucide-react';
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
    setup,
    fundamental_quality,
  } = stock;

  const daily = timeframes?.D || {};
  const isPositive = price_change_pct >= 0;

  const renderQualityBadges = () => {
    if (!fundamental_quality) return null;
    const { profitability_ok, debt_ok, has_fundamentals } = fundamental_quality;

    if (!has_fundamentals) {
      return (
        <div className='flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 text-slate-500 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider border border-slate-200 dark:border-slate-700'>
          <CircleAlert size={12} /> No Data
        </div>
      );
    }

    return (
      <div className='flex gap-1.5'>
        <div
          className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider border ${
            profitability_ok
              ? 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 border-green-200 dark:border-green-800/50'
              : 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800/50'
          }`}
        >
          {profitability_ok ? <ShieldCheck size={12} /> : <ShieldX size={12} />}
          Profits
        </div>
        <div
          className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider border ${
            debt_ok
              ? 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 border-green-200 dark:border-green-800/50'
              : 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800/50'
          }`}
        >
          {debt_ok ? <ShieldCheck size={12} /> : <ShieldX size={12} />}
          Debt
        </div>
      </div>
    );
  };

  const renderTimeframe = (tf, label) => {
    const data = timeframes?.[tf];
    const isBullish = data?.is_bullish;
    return (
      <div
        className={`flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold shadow-sm ${
          isBullish
            ? 'bg-green-500 text-white dark:bg-green-600/90'
            : 'bg-red-500 text-white dark:bg-red-600/90'
        }`}
      >
        <span className='opacity-90'>{label}</span>
        <span className='text-[10px] leading-none'>
          {isBullish ? '▲' : '▼'}
        </span>
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
        return 'bg-green-600 text-white border-green-700 shadow-md';
      case 2:
        return 'bg-amber-500 text-white border-amber-600 shadow-sm';
      case 1:
        return 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700';
      default:
        return 'bg-slate-50 text-slate-400 border-slate-100 opacity-50 dark:bg-slate-900/50 dark:text-slate-600 dark:border-slate-800';
    }
  };

  return (
    <Link
      to={`/stocks/${symbol}`}
      className='no-underline text-inherit block group'
    >
      <div className='bg-bg-secondary border-2 border-border rounded-xl p-5 flex flex-col gap-5 transition-all duration-300 shadow-sm group-hover:-translate-y-1.5 group-hover:border-blue-500/50 group-hover:shadow-xl dark:group-hover:border-blue-400/30'>
        <div className='flex justify-between items-start gap-4'>
          <div className='flex flex-col gap-1.5 min-w-0 flex-1'>
            <div className='flex items-center gap-2 flex-wrap'>
              <span className='font-black text-xl tracking-tight text-text group-hover:text-blue-500 transition-colors truncate'>
                {symbol.replace('.NS', '')}
              </span>
              <div className='flex items-center gap-2'>
                <SetupBadge setup={setup} />
                <WatchlistStar
                  symbol={symbol}
                  isWatched={isWatched}
                  onToggle={onToggleWatch}
                />
              </div>
            </div>
            <div className='flex items-center gap-2 flex-wrap'>
              <span className='text-[10px] font-bold uppercase bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2 py-0.5 rounded tracking-wider border border-slate-200 dark:border-slate-700 whitespace-nowrap'>
                {sector}
              </span>
              <div className='text-[11px] text-text-muted truncate font-medium'>
                {name}
              </div>
              {renderQualityBadges()}
            </div>
          </div>
          <div className='text-right flex flex-col gap-1 shrink-0'>
            <div className='font-black text-lg font-mono text-text'>
              ₹{close_price?.toLocaleString('en-IN') || '-'}
            </div>
            <div
              className={`text-xs font-bold px-2 py-0.5 rounded-full inline-block ${isPositive ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}
            >
              {isPositive ? '+' : ''}
              {price_change_pct?.toFixed(2)}%
            </div>
          </div>
        </div>

        <div className='flex justify-between items-center bg-slate-50 dark:bg-slate-900/50 p-3 rounded-xl border border-border/60'>
          <div
            className={`text-[11px] font-black px-3 py-1.5 rounded-lg border transition-all ${getConfluenceStyles(confluence_count)}`}
          >
            {confluence_count}/3 CONFLUENCE
          </div>
          <div className='flex gap-1.5'>
            {renderTimeframe('D', 'D')}
            {renderTimeframe('W', 'W')}
            {renderTimeframe('M', 'M')}
          </div>
        </div>

        <div className='flex flex-col gap-4'>
          <div className='grid grid-cols-3 gap-3 border-b border-border/50 pb-4'>
            <div className='flex flex-col gap-1'>
              <span className='text-[10px] font-bold text-text-muted uppercase tracking-widest'>
                Score
              </span>
              <span
                className={`text-base font-mono font-black ${daily.score >= 70 ? 'text-green-500' : daily.score >= 50 ? 'text-blue-500' : 'text-text'}`}
              >
                {daily.score || '-'}
              </span>
            </div>
            <div className='flex flex-col gap-1'>
              <span className='text-[10px] font-bold text-text-muted uppercase tracking-widest'>
                RSI
              </span>
              <span
                className={`text-base font-mono font-bold ${daily.rsi <= 30 ? 'text-green-500' : daily.rsi >= 70 ? 'text-red-500' : 'text-text'}`}
              >
                {daily.rsi?.toFixed(1) || '-'}
              </span>
            </div>
            <div className='flex flex-col gap-1'>
              <span className='text-[10px] font-bold text-text-muted uppercase tracking-widest'>
                EMA
              </span>
              <span
                className={`text-[11px] font-bold uppercase tracking-tight ${daily.ema_signal?.toLowerCase() === 'bullish' ? 'text-green-500' : 'text-red-500'}`}
              >
                {daily.ema_signal || '-'}
              </span>
            </div>
          </div>

          <div className='grid grid-cols-3 gap-3'>
            <div className='flex flex-col gap-0.5'>
              <span className='text-[10px] font-semibold text-text-muted uppercase tracking-wider'>
                P/E
              </span>
              <span className='text-sm font-mono font-bold text-text'>
                {fundamentals.pe?.toFixed(1) || '-'}
              </span>
            </div>
            <div className='flex flex-col gap-0.5'>
              <span className='text-[10px] font-semibold text-text-muted uppercase tracking-wider'>
                ROE
              </span>
              <span
                className={`text-sm font-mono font-bold ${fundamentals.roe > 0.15 ? 'text-green-500' : 'text-text'}`}
              >
                {fundamentals.roe
                  ? `${(fundamentals.roe * 100).toFixed(1)}%`
                  : '-'}
              </span>
            </div>
            <div className='flex flex-col gap-0.5'>
              <span className='text-[10px] font-semibold text-text-muted uppercase tracking-wider'>
                MCap
              </span>
              <span className='text-sm font-mono font-bold text-text'>
                {formatMCap(fundamentals.market_cap)}
              </span>
            </div>
          </div>

          <div className='grid grid-cols-3 gap-3'>
            <div className='flex flex-col gap-0.5'>
              <span className='text-[10px] font-bold text-text-muted uppercase tracking-widest'>
                RS Score
              </span>
              <span className='text-base font-mono font-black text-blue-600 dark:text-blue-400'>
                {daily.rs_score?.toFixed(0) || '-'}
              </span>
            </div>
            <div className='flex flex-col gap-0.5'>
              <span className='text-[10px] font-semibold text-text-muted uppercase tracking-wider'>
                ADX
              </span>
              <span
                className={`text-sm font-mono font-bold ${daily.adx > 25 ? 'text-blue-500' : 'text-text'}`}
              >
                {daily.adx?.toFixed(1) || '-'}
              </span>
            </div>
            <div className='flex flex-col gap-0.5'>
              <span className='text-[10px] font-semibold text-text-muted uppercase tracking-wider'>
                52W High
              </span>
              <span
                className={`text-sm font-mono font-bold ${Math.abs(daily.pct_from_52wh) < 5 ? 'text-green-500' : 'text-text'}`}
              >
                {daily.pct_from_52wh != null
                  ? `${daily.pct_from_52wh.toFixed(1)}%`
                  : '-'}
              </span>
            </div>
          </div>

          {daily.volume_breakout && (
            <div className='flex items-center gap-2 bg-blue-600 text-white text-[10px] font-black px-3 py-2 rounded-lg uppercase tracking-[0.15em] mt-2 shadow-lg shadow-blue-500/20'>
              <span className='w-2 h-2 bg-white rounded-full animate-ping'></span>
              Volume Breakout
            </div>
          )}
        </div>
      </div>
    </Link>
  );
};

export default StockCard;
