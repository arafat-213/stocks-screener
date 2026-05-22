import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Zap, ChevronDown } from 'lucide-react';

const ChangeChip = ({ item }) => (
  <Link to={`/stocks/${item.symbol}`} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-sm bg-bg-elevated no-underline text-text border border-border transition-all duration-200 text-[13px] hover:border-primary hover:-translate-y-0.5 hover:shadow-sm">
    <span className="font-bold">{item.symbol.replace('.NS', '')}</span>
    <span className="text-text-muted tabular-nums">{item.curr_score?.toFixed(0)}</span>
    <span className={`font-semibold text-[12px] ${item.price_change_pct >= 0 ? 'text-bullish' : 'text-bearish'}`}>
      {item.price_change_pct >= 0 ? '+' : ''}{item.price_change_pct?.toFixed(1)}%
    </span>
  </Link>
);

const ChangeBanner = ({ changes = [], asOf, prevDate, loading }) => {
  const [isOpen, setIsOpen] = useState(() => {
    return localStorage.getItem('changeBannerOpen') === 'true';
  });

  const toggle = () => {
    const newState = !isOpen;
    setIsOpen(newState);
    localStorage.setItem('changeBannerOpen', newState);
  };

  if (loading) return null;
  if (!changes || changes.length === 0) return null;

  const newlyBullish = changes.filter(c => ['newly_bullish', 'confluence_improved'].includes(c.change_type));
  const turnedBearish = changes.filter(c => ['turned_bearish', 'confluence_dropped'].includes(c.change_type));

  return (
    <div className="mb-6 border-l-4 border-primary overflow-hidden bg-bg-secondary border border-border rounded-lg shadow-sm">
      <button 
        className="w-full flex justify-between items-center px-4 py-3 bg-transparent border-0 cursor-pointer font-semibold text-text transition-colors duration-200 hover:bg-bg-elevated focus:outline-none" 
        onClick={toggle}
      >
        <div className="flex items-center gap-2.5">
          <Zap size={16} className="text-primary" />
          <span>Signal Changes Since {prevDate}</span>
          <span className="bg-primary text-white text-[11px] px-2 py-0.5 rounded-full ml-1">{changes.length}</span>
        </div>
        <ChevronDown size={14} className={`transition-transform duration-200 text-text-muted ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      
      {isOpen && (
        <div className="px-4 pb-4 flex flex-col gap-4 border-t border-border pt-4">
          {newlyBullish.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-[12px] font-bold uppercase tracking-wider text-bullish">↑ Turned Bullish / Improved</span>
              <div className="flex flex-wrap gap-2">
                {newlyBullish.map(c => <ChangeChip key={c.symbol} item={c} />)}
              </div>
            </div>
          )}
          
          {turnedBearish.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-[12px] font-bold uppercase tracking-wider text-bearish">↓ Turned Bearish / Dropped</span>
              <div className="flex flex-wrap gap-2">
                {turnedBearish.map(c => <ChangeChip key={c.symbol} item={c} />)}
              </div>
            </div>
          )}

          {changes.length === 0 && (
            <div className="text-text-muted text-[14px] italic">No signal changes since last run.</div>
          )}
        </div>
      )}
    </div>
  );
};

export default ChangeBanner;
