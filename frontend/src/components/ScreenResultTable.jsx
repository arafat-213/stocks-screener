import React from 'react';
import { Link } from 'react-router-dom';

const SCREEN_COLUMNS = {
  'momentum-monsters':      ['symbol', 'name', 'rs_score', 'momentum_3m', 'adx', 'score'],
  'value-with-momentum':    ['symbol', 'name', 'peg_ratio', 'momentum_1m', 'ema_slope', 'score'],
  'near-breakout':          ['symbol', 'name', 'pct_from_resistance', 'volume_breakout', 'score'],
  '52w-high':               ['symbol', 'name', 'pct_from_52w_high', 'week52_high', 'score'],
  '52w-low':                ['symbol', 'name', 'pct_from_52w_low', 'week52_low', 'score'],
  'low-debt-midcap':        ['symbol', 'name', 'market_cap_category', 'de_ratio', 'fcf_positive', 'score'],
  'undervalued-fundamentals':['symbol', 'name', 'peg_ratio', 'ev_to_ebitda', 'dividend_yield', 'score'],
  'steady-compounders':     ['symbol', 'name', 'roce', 'dividend_consistency', 'above_200ema', 'score'],
  '_default':               ['symbol', 'name', 'score', 'rsi', 'confluence_count'],
};

const COLUMN_META = {
  symbol:               { label: 'Symbol',      fmt: v => v },
  name:                 { label: 'Name',         fmt: v => v },
  score:                { label: 'Score',        fmt: v => v?.toFixed(1) ?? '—' },
  rs_score:             { label: 'RS Score',     fmt: v => v?.toFixed(0) ?? '—' },
  momentum_1m:          { label: '1M Mom %',     fmt: v => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—' },
  momentum_3m:          { label: '3M Mom %',     fmt: v => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—' },
  adx:                  { label: 'ADX',          fmt: v => v?.toFixed(1) ?? '—' },
  peg_ratio:            { label: 'PEG',          fmt: v => v?.toFixed(2) ?? '—' },
  ev_to_ebitda:         { label: 'EV/EBITDA',   fmt: v => v?.toFixed(1) ?? '—' },
  dividend_yield:       { label: 'Div Yield',    fmt: v => v != null ? `${(v * 100).toFixed(2)}%` : '—' },
  roce:                 { label: 'ROCE %',       fmt: v => v != null ? `${(v * 100).toFixed(1)}%` : '—' },
  de_ratio:             { label: 'D/E',          fmt: v => v?.toFixed(2) ?? '—' },
  pct_from_52w_high:    { label: '% from High',  fmt: v => v != null ? `${v.toFixed(1)}%` : '—' },
  pct_from_52w_low:     { label: '% from Low',   fmt: v => v != null ? `${v.toFixed(1)}%` : '—' },
  week52_high:          { label: '52W High',     fmt: v => v != null ? `₹${v.toLocaleString('en-IN')}` : '—' },
  week52_low:           { label: '52W Low',      fmt: v => v != null ? `₹${v.toLocaleString('en-IN')}` : '—' },
  pct_from_resistance:  { label: '% to Break',   fmt: v => v != null ? `${v.toFixed(1)}%` : '—' },
  volume_breakout:      { label: 'Vol Break',    fmt: v => v ? '✓' : '—' },
  fcf_positive:         { label: 'FCF+',         fmt: v => v ? '✓' : '—' },
  dividend_consistency: { label: 'Div 3Y',       fmt: v => v ? '✓' : '—' },
  above_200ema:         { label: '>200 EMA',     fmt: v => v ? '✓' : '—' },
  market_cap_category:  { label: 'Cap',          fmt: v => v ?? '—' },
  ema_slope:            { label: 'EMA Trend',    fmt: v => v != null ? (v > 0 ? '↑' : '↓') : '—' },
  confluence_count:     { label: 'Conf.',        fmt: v => v != null ? `${v}/3` : '—' },
  rsi:                  { label: 'RSI',          fmt: v => v?.toFixed(1) ?? '—' },
};

const ScreenResultTable = ({ results, slug, loading }) => {
  const cols = SCREEN_COLUMNS[slug] || SCREEN_COLUMNS['_default'];

  if (loading && results.length === 0) {
    return (
      <div className="table-container">
        <table className="stocks-table">
          <thead>
            <tr>{cols.map(c => <th key={c}>{COLUMN_META[c].label}</th>)}</tr>
          </thead>
          <tbody>
            {[...Array(8)].map((_, i) => (
              <tr key={i}>
                {cols.map(c => (
                  <td key={c}><div style={{height: '20px', background: 'var(--color-bg-elevated)', borderRadius: '4px'}}></div></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-container" style={{ opacity: loading ? 0.5 : 1, transition: 'opacity 0.2s' }}>
      <table className="stocks-table">
        <thead>
          <tr>
            {cols.map(c => <th key={c}>{COLUMN_META[c].label}</th>)}
          </tr>
        </thead>
        <tbody>
          {results.map((row) => (
            <tr key={row.symbol}>
              {cols.map(c => (
                <td key={c}>
                  {c === 'symbol' ? (
                    <Link to={`/stocks/${row.symbol}`} style={{ fontWeight: 'bold', color: 'inherit', textDecoration: 'none' }}>
                      {COLUMN_META[c].fmt(row[c])}
                    </Link>
                  ) : (
                    COLUMN_META[c].fmt(row[c])
                  )}
                </td>
              ))}
            </tr>
          ))}
          {results.length === 0 && !loading && (
            <tr>
              <td colSpan={cols.length} style={{ textAlign: 'center', padding: '40px', color: 'var(--color-text-muted)' }}>
                No stocks match this screen right now. Results update after each pipeline run.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default ScreenResultTable;
