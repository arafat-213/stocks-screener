import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Zap, ChevronDown } from 'lucide-react';
import './ChangeBanner.css';

const ChangeChip = ({ item }) => (
  <Link to={`/stocks/${item.symbol}`} className="change-chip">
    <span className="chip-symbol">{item.symbol.replace('.NS', '')}</span>
    <span className="chip-score">{item.curr_score?.toFixed(0)}</span>
    <span className={`chip-change ${item.price_change_pct >= 0 ? 'positive' : 'negative'}`}>
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
    <div className="change-banner card">
      <button className="change-banner-toggle" onClick={toggle}>
        <div className="toggle-left">
          <Zap size={16} className="zap-icon" />
          <span>Signal Changes Since {prevDate}</span>
          <span className="change-count-pill">{changes.length}</span>
        </div>
        <ChevronDown size={14} className={`chevron ${isOpen ? 'rotated' : ''}`} />
      </button>
      
      {isOpen && (
        <div className="change-banner-body">
          {newlyBullish.length > 0 && (
            <div className="change-group">
              <span className="change-group-label bullish">↑ Turned Bullish / Improved</span>
              <div className="chip-container">
                {newlyBullish.map(c => <ChangeChip key={c.symbol} item={c} />)}
              </div>
            </div>
          )}
          
          {turnedBearish.length > 0 && (
            <div className="change-group">
              <span className="change-group-label bearish">↓ Turned Bearish / Dropped</span>
              <div className="chip-container">
                {turnedBearish.map(c => <ChangeChip key={c.symbol} item={c} />)}
              </div>
            </div>
          )}

          {changes.length === 0 && (
            <div className="no-changes">No signal changes since last run.</div>
          )}
        </div>
      )}
    </div>
  );
};

export default ChangeBanner;
