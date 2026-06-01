import { Link } from 'react-router-dom';
import { map, size } from 'lodash/fp';

const mapWithIdx = map.convert({ cap: false });

const SCREEN_COLUMNS = {
  'actionable-entries': [
    'symbol',
    'name',
    'price',
    'change_pct',
    'rsi',
    'volume_breakout',
    'shares',
    'position_value',
    'score',
  ],
  'momentum-monsters': [
    'symbol',
    'name',
    'rs_score',
    'momentum_3m',
    'adx',
    'score',
  ],
  'near-breakout': [
    'symbol',
    'name',
    'pct_from_resistance',
    'volume_breakout',
    'score',
  ],
  '52w-high': ['symbol', 'name', 'pct_from_52w_high', 'week52_high', 'score'],
  '52w-low': ['symbol', 'name', 'pct_from_52w_low', 'week52_low', 'score'],
  _default: ['symbol', 'name', 'score', 'rsi', 'confluence_count'],
};

const COLUMN_META = {
  symbol: {
    label: 'Symbol',
    fmt: (v) => (
      <span className='text-blue-600 dark:text-blue-400 font-black tracking-tighter'>
        {v.replace('.NS', '')}
      </span>
    ),
  },
  name: {
    label: 'Name',
    fmt: (v) => (
      <span className='text-slate-500 dark:text-slate-400 font-bold text-xs truncate max-w-[120px] inline-block'>
        {v}
      </span>
    ),
  },
  score: {
    label: 'Score',
    fmt: (v) => (
      <span
        className={`font-black text-sm px-2 py-1 rounded ${v >= 70 ? 'bg-green-500 text-white' : v >= 50 ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-700 dark:bg-slate-800'}`}
      >
        {v?.toFixed(1) ?? '—'}
      </span>
    ),
  },
  rs_score: {
    label: 'RS Score',
    fmt: (v) => (
      <span className='text-blue-600 dark:text-blue-400 font-black'>
        {v?.toFixed(0) ?? '—'}
      </span>
    ),
  },
  momentum_1m: {
    label: '1M Mom %',
    fmt: (v) => (
      <span
        className={`font-black text-[11px] px-2 py-0.5 rounded shadow-sm ${v > 0 ? 'bg-green-500 text-white' : v < 0 ? 'bg-red-500 text-white' : 'bg-slate-100'}`}
      >
        {v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—'}
      </span>
    ),
  },
  momentum_3m: {
    label: '3M Mom %',
    fmt: (v) => (
      <span
        className={`font-black text-[11px] px-2 py-0.5 rounded shadow-sm ${v > 0 ? 'bg-green-500 text-white' : v < 0 ? 'bg-red-500 text-white' : 'bg-slate-100'}`}
      >
        {v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—'}
      </span>
    ),
  },
  adx: {
    label: 'ADX',
    fmt: (v) => <span className='font-bold'>{v?.toFixed(1) ?? '—'}</span>,
  },
  pct_from_52w_high: {
    label: '% from High',
    fmt: (v) => (
      <span className={`font-bold ${Math.abs(v) < 5 ? 'text-green-500' : ''}`}>
        {v != null ? `${v.toFixed(1)}%` : '—'}
      </span>
    ),
  },
  pct_from_52w_low: {
    label: '% from Low',
    fmt: (v) => (
      <span className={`font-bold ${Math.abs(v) < 10 ? 'text-red-500' : ''}`}>
        {v != null ? `${v.toFixed(1)}%` : '—'}
      </span>
    ),
  },
  week52_high: {
    label: '52W High',
    fmt: (v) => (
      <span className='font-mono text-xs'>₹{v?.toLocaleString('en-IN')}</span>
    ),
  },
  week52_low: {
    label: '52W Low',
    fmt: (v) => (
      <span className='font-mono text-xs'>₹{v?.toLocaleString('en-IN')}</span>
    ),
  },
  pct_from_resistance: {
    label: '% to Break',
    fmt: (v) => (
      <span className={`font-bold ${v < 3 ? 'text-green-500' : ''}`}>
        {v != null ? `${v.toFixed(1)}%` : '—'}
      </span>
    ),
  },
  volume_breakout: {
    label: 'Vol Break',
    fmt: (v) =>
      v ? (
        <span className='bg-blue-600 text-white px-2 py-0.5 rounded-md text-[10px] font-black uppercase'>
          DETECTED
        </span>
      ) : (
        '—'
      ),
  },
  above_200ema: {
    label: '>200 EMA',
    fmt: (v) =>
      v ? (
        <span className='text-green-500 font-black'>✓</span>
      ) : (
        <span className='text-red-500 font-black'>✗</span>
      ),
  },
  market_cap_category: {
    label: 'Cap',
    fmt: (v) => (
      <span className='bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-[10px] font-black uppercase text-slate-500'>
        {v ?? '—'}
      </span>
    ),
  },
  ema_slope: {
    label: 'EMA Trend',
    fmt: (v) =>
      v != null ? (
        v > 0 ? (
          <span className='text-green-500 font-black'>↑</span>
        ) : (
          <span className='text-red-500 font-black'>↓</span>
        )
      ) : (
        '—'
      ),
  },
  confluence_count: {
    label: 'Conf.',
    fmt: (v) => (
      <span
        className={`px-2 py-0.5 rounded-md font-black text-xs ${v === 3 ? 'bg-green-500 text-white' : v === 2 ? 'bg-amber-500 text-white' : 'bg-slate-100 text-slate-500'}`}
      >
        {v}/3
      </span>
    ),
  },
  rsi: {
    label: 'RSI',
    fmt: (v) => (
      <span
        className={`font-bold ${v <= 30 ? 'text-green-500' : v >= 70 ? 'text-red-500' : ''}`}
      >
        {v?.toFixed(1) ?? '—'}
      </span>
    ),
  },
  price: {
    label: 'Price',
    fmt: (v) => (
      <span className='font-mono font-bold text-xs'>
        ₹{v?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
      </span>
    ),
  },
  change_pct: {
    label: 'Change %',
    fmt: (v) => (
      <span
        className={`px-2 py-1 rounded-md font-mono font-bold text-[10px] ${v >= 0 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}
      >
        {v >= 0 ? '+' : ''}
        {v?.toFixed(2)}%
      </span>
    ),
  },
  shares: {
    label: 'Shares',
    fmt: (v, row) => (
      <span className='font-black text-blue-600 dark:text-blue-400'>
        {row.setup?.position_sizing?.shares ?? '—'}
      </span>
    ),
  },
  position_value: {
    label: 'Pos. Value',
    fmt: (v, row) => (
      <span className='font-mono text-xs font-bold text-slate-600 dark:text-slate-400'>
        {row.setup?.position_sizing?.position_value
          ? `₹${row.setup.position_sizing.position_value.toLocaleString('en-IN')}`
          : '—'}
      </span>
    ),
  },
};

const ScreenResultTable = ({ results, slug, loading }) => {
  const cols = SCREEN_COLUMNS[slug] || SCREEN_COLUMNS['_default'];

  if (loading && size(results) === 0) {
    return (
      <div className='w-full overflow-x-auto bg-bg-secondary border-2 border-border rounded-2xl shadow-sm'>
        <table className='w-full border-collapse'>
          <thead>
            <tr className='bg-slate-50 dark:bg-slate-900 border-b-2 border-border'>
              {map(
                (c) => (
                  <th
                    key={c}
                    className='px-6 py-4 text-left text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em]'
                  >
                    {COLUMN_META[c].label}
                  </th>
                ),
                cols
              )}
            </tr>
          </thead>
          <tbody>
            {mapWithIdx(
              (_, i) => (
                <tr key={i} className='border-b border-border'>
                  {map(
                    (c) => (
                      <td key={c} className='px-6 py-4'>
                        <div className='h-6 bg-slate-100 dark:bg-slate-800 rounded-lg animate-pulse w-full'></div>
                      </td>
                    ),
                    cols
                  )}
                </tr>
              ),
              [...Array(8)]
            )}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div
      className={`w-full overflow-x-auto bg-bg-secondary border-2 border-border rounded-2xl shadow-sm transition-all duration-300 ${loading ? 'opacity-50' : 'opacity-100'}`}
    >
      <table className='w-full border-collapse'>
        <thead>
          <tr className='bg-slate-50 dark:bg-slate-900 border-b-2 border-border'>
            {map(
              (c) => (
                <th
                  key={c}
                  className='px-6 py-4 text-left text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em]'
                >
                  {COLUMN_META[c].label}
                </th>
              ),
              cols
            )}
          </tr>
        </thead>
        <tbody>
          {mapWithIdx(
            (row, idx) => (
              <tr
                key={`${row.symbol}-${idx}`}
                className='border-b border-border hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors group'
              >
                {map(
                  (c) => (
                    <td key={c} className='px-6 py-4 text-sm font-medium'>
                      {c === 'symbol' ? (
                        <Link
                          to={`/stocks/${row.symbol}`}
                          className='no-underline group-hover:translate-x-1 transition-transform inline-block'
                        >
                          {COLUMN_META[c].fmt(row[c], row)}
                        </Link>
                      ) : (
                        COLUMN_META[c].fmt(row[c], row)
                      )}
                    </td>
                  ),
                  cols
                )}
              </tr>
            ),
            results
          )}
          {size(results) === 0 && !loading && (
            <tr>
              <td colSpan={size(cols)} className='text-center py-20'>
                <div className='text-slate-400 font-black uppercase tracking-[0.2em] text-[10px]'>
                  No matches found for this screen
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};

export default ScreenResultTable;
