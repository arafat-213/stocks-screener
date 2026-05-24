import { Link } from 'react-router-dom';
import { map } from 'lodash/fp';

const mapWithIndex = map.convert({ cap: false });

const MarketTable = ({ stocks }) => {

  return (
    <div className="w-full overflow-x-auto bg-bg-secondary border-2 border-border rounded-2xl mt-6 shadow-sm">
      <div className="grid min-w-[900px] grid-cols-[140px_110px_100px_90px_80px_90px_90px_1fr]">
        <div className="contents">
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-[11] left-0">Symbol</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">Price</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">Change %</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">Score</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">RS</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">ADX</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">ROE %</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10">Sector</div>
        </div>
        <div className="contents">
          {mapWithIndex((stock, idx) => {
            const daily = stock.timeframes?.D || {};
            const isPositive = stock.price_change_pct >= 0;
            
            return (
              <Link 
                key={`${stock.symbol}-${idx}`} 
                to={`/stocks/${stock.symbol}`} 
                className="contents group no-underline text-inherit"
              >
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-black text-blue-600 dark:text-blue-400 sticky left-0 z-[2] bg-bg-secondary group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors tracking-tighter">
                  {stock.symbol.replace('.NS', '')}
                </div>
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-mono font-bold justify-end text-right group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors">
                  ₹{stock.close_price?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
                </div>
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-mono font-black justify-end text-right group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors">
                  <span className={`px-2 py-0.5 rounded shadow-sm ${isPositive ? 'bg-green-500 text-white' : 'bg-red-500 text-white'}`}>
                    {isPositive ? '+' : ''}{stock.price_change_pct?.toFixed(2)}%
                  </span>
                </div>
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right font-black group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors">
                   <span className={`px-2 py-0.5 rounded ${daily.score >= 70 ? 'bg-green-500 text-white' : daily.score >= 50 ? 'bg-blue-500 text-white' : 'bg-slate-100 dark:bg-slate-800'}`}>
                      {daily.score || '-'}
                   </span>
                </div>
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right text-blue-600 dark:text-blue-400 font-black group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors">
                  {daily.rs_score?.toFixed(0) || '-'}
                </div>
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors font-bold">
                  {daily.adx?.toFixed(1) || '-'}
                </div>
                <div className="p-4 px-6 text-sm border-b border-border flex items-center overflow-hidden font-mono justify-end text-right group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors font-bold">
                  {stock.fundamentals?.roe ? `${(stock.fundamentals.roe * 100).toFixed(1)}%` : '-'}
                </div>
                <div className="p-4 px-6 text-[11px] border-b border-border flex items-center overflow-hidden text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider whitespace-nowrap truncate group-hover:bg-slate-50 dark:group-hover:bg-slate-900 transition-colors">
                  {stock.sector}
                </div>
              </Link>
            );
          }, stocks)}
        </div>
      </div>
    </div>
  );
};

export const MarketTableSkeleton = ({ rows = 10 }) => {
  return (
    <div className="w-full overflow-x-auto bg-bg-secondary border-2 border-border rounded-2xl mt-6 shadow-sm">
      <div className="grid min-w-[900px] grid-cols-[140px_110px_100px_90px_80px_90px_90px_1fr]">
        <div className="contents">
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-[11] left-0">Symbol</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">Price</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">Change %</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">Score</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">RSI</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10">EMA</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10 text-right">P/E</div>
          <div className="bg-slate-50 dark:bg-slate-900 p-4 px-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 border-b-2 border-border sticky top-0 z-10">Sector</div>
        </div>
        <div className="contents">
          {mapWithIndex((_, i) => (
            <div key={i} className="contents">
              {mapWithIndex((_, j) => (
                <div key={j} className={`p-4 px-6 border-b border-border flex items-center ${j === 0 ? 'sticky left-0 z-[2] bg-inherit' : ''}`}>
                  <div className="h-6 bg-slate-100 dark:bg-slate-800 rounded-lg animate-pulse w-full"></div>
                </div>
              ))}
            </div>
          ), Array.from({ length: rows }))}
        </div>
      </div>
    </div>
  );
};

export default MarketTable;
