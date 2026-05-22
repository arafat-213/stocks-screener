import { Link } from 'react-router-dom';

const MarketTable = ({ stocks }) => {

  return (
    <div className="w-full overflow-x-auto bg-bg-secondary border border-border rounded-md mt-4">
      <div className="grid min-w-[800px] grid-cols-[140px_100px_80px_70px_70px_100px_70px_1fr]">
        <div className="contents">
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-[11] left-0">Symbol</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">Price</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">Change %</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">Score</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">RS</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">ADX</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">ROE %</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10">Sector</div>
        </div>
        <div className="contents">
          {stocks.map((stock) => {
            const daily = stock.timeframes?.D || {};
            const isPositive = stock.price_change_pct >= 0;
            
            return (
              <Link 
                key={stock.symbol} 
                to={`/stocks/${stock.symbol}`} 
                className="contents group no-underline text-inherit"
              >
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-bold text-text sticky left-0 z-[2] bg-inherit group-hover:bg-bg-elevated cursor-pointer">
                  {stock.symbol.replace('.NS', '')}
                </div>
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right group-hover:bg-bg-elevated cursor-pointer">
                  ₹{stock.close_price?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
                </div>
                <div className={`p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right group-hover:bg-bg-elevated cursor-pointer ${isPositive ? 'text-bullish' : 'text-bearish'}`}>
                  {isPositive ? '+' : ''}{stock.price_change_pct?.toFixed(2)}%
                </div>
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right font-bold group-hover:bg-bg-elevated cursor-pointer">
                  {daily.score || '-'}
                </div>
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right text-primary font-bold group-hover:bg-bg-elevated cursor-pointer">
                  {daily.rs_score?.toFixed(0) || '-'}
                </div>
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right group-hover:bg-bg-elevated cursor-pointer">
                  {daily.adx?.toFixed(1) || '-'}
                </div>
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right group-hover:bg-bg-elevated cursor-pointer">
                  {stock.fundamentals?.roe?.toFixed(1) || '-'}%
                </div>
                <div className="p-2.5 px-4 text-sm border-b border-border flex items-center overflow-hidden text-text-muted whitespace-nowrap truncate group-hover:bg-bg-elevated cursor-pointer">
                  {stock.sector}
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export const MarketTableSkeleton = ({ rows = 10 }) => {
  return (
    <div className="w-full overflow-x-auto bg-bg-secondary border border-border rounded-md mt-4">
      <div className="grid min-w-[800px] grid-cols-[140px_100px_80px_70px_70px_100px_70px_1fr]">
        <div className="contents">
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-[11] left-0">Symbol</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">Price</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">Change %</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">Score</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">RSI</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10">EMA</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10 text-right">P/E</div>
          <div className="bg-bg-elevated p-3 px-4 text-[12px] font-semibold uppercase tracking-wider text-text-muted border-b-2 border-border sticky top-0 z-10">Sector</div>
        </div>
        <div className="contents">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="contents">
              {Array.from({ length: 8 }).map((_, j) => (
                <div key={j} className={`p-2.5 px-4 border-b border-border flex items-center ${j === 0 ? 'sticky left-0 z-[2] bg-inherit' : ''}`}>
                  <div className="h-5 bg-gradient-to-r from-bg-elevated via-border to-bg-elevated bg-[length:200%_100%] animate-skeleton-loading rounded w-full"></div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default MarketTable;
