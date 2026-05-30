import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Zap, ChevronDown } from 'lucide-react';
import { map, filter, size } from 'lodash/fp';

const ChangeChip = ({ item }) => (
  <Link
    to={`/stocks/${item.symbol}`}
    className='inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 dark:bg-slate-900 border-2 border-border no-underline text-text transition-all duration-200 hover:border-blue-500 hover:-translate-y-0.5 hover:shadow-md group'
  >
    <span className='font-black text-xs tracking-tighter group-hover:text-blue-500'>
      {item.symbol.replace('.NS', '')}
    </span>
    <span
      className={`font-black text-[10px] px-1.5 py-0.5 rounded shadow-sm ${item.price_change_pct >= 0 ? 'bg-green-500 text-white' : 'bg-red-500 text-white'}`}
    >
      {item.price_change_pct >= 0 ? '+' : ''}
      {item.price_change_pct?.toFixed(1)}%
    </span>
  </Link>
);

const ChangeBanner = ({ changes = [], prevDate, loading }) => {
  const [isOpen, setIsOpen] = useState(() => {
    return localStorage.getItem('changeBannerOpen') === 'true';
  });

  const toggle = () => {
    const newState = !isOpen;
    setIsOpen(newState);
    localStorage.setItem('changeBannerOpen', newState);
  };

  if (loading) return null;
  if (!changes || size(changes) === 0) return null;

  const newlyBullish = filter(
    (c) => ['newly_bullish', 'confluence_improved'].includes(c.change_type),
    changes
  );
  const turnedBearish = filter(
    (c) => ['turned_bearish', 'confluence_dropped'].includes(c.change_type),
    changes
  );

  return (
    <div className='mb-6 overflow-hidden bg-bg-secondary border-2 border-border rounded-2xl shadow-sm'>
      <button
        className='w-full flex justify-between items-center px-4 py-3 sm:px-6 sm:py-4 bg-transparent border-0 cursor-pointer font-black text-text transition-colors duration-200 hover:bg-slate-50 dark:hover:bg-slate-900 focus:outline-none'
        onClick={toggle}
      >
        <div className='flex items-center gap-2 sm:gap-3'>
          <Zap size={18} className='text-amber-500 fill-amber-500 sm:size-5' />
          <span className='uppercase tracking-[0.1em] text-xs sm:text-sm'>
            Signal Changes Since {prevDate}
          </span>
          <span className='bg-blue-600 text-white text-[9px] sm:text-[10px] px-2 py-0.5 rounded-full font-black shadow-lg shadow-blue-500/20'>
            {size(changes)}
          </span>
        </div>
        <ChevronDown
          size={18}
          className={`transition-transform duration-300 text-slate-400 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <div className='px-4 pb-4 sm:px-6 sm:pb-6 flex flex-col gap-5 sm:gap-6 border-t-2 border-border/50 pt-4 sm:pt-6 animate-fade-in'>
          {size(newlyBullish) > 0 && (
            <div className='flex flex-col gap-2.5 sm:gap-3'>
              <span className='text-[10px] sm:text-[11px] font-black uppercase tracking-[0.2em] text-green-600 dark:text-green-400 flex items-center gap-2'>
                <span className='w-1.5 h-1.5 sm:w-2 sm:h-2 bg-green-500 rounded-full animate-pulse'></span>
                Turned Bullish
              </span>
              <div className='flex flex-wrap gap-2 sm:gap-2.5'>
                {map(
                  (c) => (
                    <ChangeChip key={c.symbol} item={c} />
                  ),
                  newlyBullish
                )}
              </div>
            </div>
          )}

          {size(turnedBearish) > 0 && (
            <div className='flex flex-col gap-2.5 sm:gap-3'>
              <span className='text-[10px] sm:text-[11px] font-black uppercase tracking-[0.2em] text-red-600 dark:text-red-400 flex items-center gap-2'>
                <span className='w-1.5 h-1.5 sm:w-2 sm:h-2 bg-red-500 rounded-full animate-pulse'></span>
                Turned Bearish
              </span>
              <div className='flex flex-wrap gap-2 sm:gap-2.5'>
                {map(
                  (c) => (
                    <ChangeChip key={c.symbol} item={c} />
                  ),
                  turnedBearish
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ChangeBanner;
