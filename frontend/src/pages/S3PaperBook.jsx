import { useState, useEffect } from 'react';
import { getOr, isEmpty, map } from 'lodash/fp';
import {
  Lock,
  Wallet,
  TrendingUp,
  Layers,
  CalendarClock,
  AlertCircle,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import { getPaperV2Book, getPaperV2Positions } from '../api/client';
import { formatDisplayDate } from '../utils/dateUtils';

// Read-only view of the frozen S3 forward paper book (specs/v3/11 §1).
// No add / close controls by design: the probation is a frozen experiment.
const S3PaperBook = () => {
  const [book, setBook] = useState(null);
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notArmed, setNotArmed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const [bookData, posData] = await Promise.all([
          getPaperV2Book().catch((err) => {
            if (err?.response?.status === 404) {
              setNotArmed(true);
              return null;
            }
            throw err;
          }),
          getPaperV2Positions(),
        ]);
        setBook(bookData);
        setPositions(posData || []);
      } catch (error) {
        console.error('Error loading S3 paper book:', error);
      } finally {
        setLoading(false);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  if (loading) {
    return (
      <div className='flex items-center justify-center min-h-[400px]'>
        <div className='flex flex-col items-center gap-4'>
          <div className='w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin'></div>
          <p className='text-text-muted font-bold uppercase tracking-widest text-xs'>
            Loading S3 Book...
          </p>
        </div>
      </div>
    );
  }

  if (notArmed || !book) {
    return (
      <div className='w-full flex flex-col gap-8 pb-24 animate-fade-in'>
        <PageHeader />
        <div className='flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center'>
          <AlertCircle size={48} className='text-text-muted mb-4 opacity-20' />
          <h3 className='text-lg font-bold text-text mb-2'>
            Probation Not Armed
          </h3>
          <p className='text-text-muted max-w-md'>
            There is no active S3 probation book yet. Once the{' '}
            <span className='font-mono'>11</span> forward run is armed, the book
            NAV and holdings will appear here.
          </p>
        </div>
      </div>
    );
  }

  const nav = getOr(0, 'nav')(book);
  const ret = getOr(0, 'total_return_pct')(book);

  return (
    <div className='w-full flex flex-col gap-8 pb-24 animate-fade-in'>
      <PageHeader />

      {/* Book header cards */}
      <div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6'>
        <StatCard
          label='Net Asset Value'
          value={`₹${nav.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          subValue={`from ₹${getOr(0, 'starting_capital')(book).toLocaleString(undefined, { maximumFractionDigits: 0 })} start`}
          icon={<TrendingUp className='text-primary' size={20} />}
          trend={ret >= 0 ? 'up' : 'down'}
          trendLabel={`${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`}
        />
        <StatCard
          label='Cash'
          value={`₹${getOr(0, 'cash')(book).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          subValue={`₹${getOr(0, 'holdings_value')(book).toLocaleString(undefined, { maximumFractionDigits: 0 })} in holdings`}
          icon={<Wallet className='text-blue-500' size={20} />}
        />
        <StatCard
          label='Holdings'
          value={`${getOr(0, 'n_positions')(book)}`}
          subValue='open positions'
          icon={<Layers className='text-bullish' size={20} />}
        />
        <StatCard
          label='Replay Clock'
          value={
            book.last_processed_date
              ? formatDisplayDate(book.last_processed_date)
              : '—'
          }
          subValue={
            book.go_live_date
              ? `go-live ${formatDisplayDate(book.go_live_date)}`
              : 'not armed'
          }
          icon={<CalendarClock className='text-amber-500' size={20} />}
        />
      </div>

      {/* Holdings */}
      <HoldingsTable positions={positions} />
    </div>
  );
};

// --- Sub-components ---

const PageHeader = () => (
  <header className='flex flex-col md:flex-row justify-between items-start gap-4'>
    <div className='flex flex-col'>
      <h1 className='text-3xl font-black tracking-tight text-text'>
        S3 Paper Book
      </h1>
      <p className='text-text-muted'>
        Frozen forward probation of the S3 momentum strategy
      </p>
    </div>
    <div className='flex items-center gap-2 px-4 py-2 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-500 h-[42px]'>
      <Lock size={16} />
      <span className='text-xs font-black uppercase tracking-widest'>
        Read-only · Frozen
      </span>
    </div>
  </header>
);

const StatCard = ({ label, value, subValue, icon, trend, trendLabel }) => (
  <div className='bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-4 relative overflow-hidden group'>
    <div className='flex justify-between items-start'>
      <div className='flex flex-col gap-1'>
        <span className='text-[10px] font-black uppercase tracking-widest text-text-muted'>
          {label}
        </span>
        <span className='text-2xl font-black text-text tracking-tight'>
          {value}
        </span>
      </div>
      <div className='p-2 bg-bg-elevated rounded-xl border border-border shadow-sm group-hover:scale-110 transition-transform'>
        {icon}
      </div>
    </div>
    <div className='flex items-center gap-2'>
      {trend && (
        <div
          className={`flex items-center gap-0.5 text-xs font-black ${trend === 'up' ? 'text-bullish' : 'text-bearish'}`}
        >
          {trend === 'up' ? (
            <ArrowUpRight size={14} />
          ) : (
            <ArrowDownRight size={14} />
          )}
          {trendLabel}
        </div>
      )}
      <span className='text-xs font-bold text-text-muted'>{subValue}</span>
    </div>
  </div>
);

const HoldingsTable = ({ positions }) => {
  if (isEmpty(positions)) {
    return (
      <div className='flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center'>
        <Layers size={48} className='text-text-muted mb-4 opacity-20' />
        <h3 className='text-lg font-bold text-text mb-2'>Fully in Cash</h3>
        <p className='text-text-muted max-w-xs'>
          The book holds no positions right now (a risk-off edge holds the book
          in cash). Holdings will appear after the next rebalance into risk-on.
        </p>
      </div>
    );
  }

  return (
    <div className='bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm'>
      <div className='overflow-x-auto'>
        <table className='w-full border-collapse'>
          <thead>
            <tr className='bg-bg-elevated border-b border-border text-[10px] uppercase tracking-widest text-text-muted font-black'>
              <th className='text-left p-4'>Symbol</th>
              <th className='text-right p-4'>Shares</th>
              <th className='text-right p-4'>Avg Cost</th>
              <th className='text-right p-4'>Last Price</th>
              <th className='text-right p-4'>Market Value</th>
              <th className='text-right p-4'>Unrealized %</th>
              <th className='text-right p-4'>Weight %</th>
              <th className='text-left p-4'>Entry Date</th>
            </tr>
          </thead>
          <tbody className='text-sm'>
            {map((pos) => {
              const pnlPct = getOr(0, 'unrealized_pct')(pos);
              const pnlColor = pnlPct >= 0 ? 'text-bullish' : 'text-bearish';
              return (
                <tr
                  key={pos.isin}
                  className='border-b border-border/50 hover:bg-bg-elevated/30 transition-colors group'
                >
                  <td className='p-4'>
                    <div className='font-black text-text tracking-tight group-hover:text-primary transition-colors'>
                      {pos.symbol}
                    </div>
                    <div className='text-[10px] font-bold text-text-muted uppercase tracking-tighter'>
                      Day {getOr(0, 'days_held')(pos)} · {pos.isin}
                    </div>
                  </td>
                  <td className='p-4 text-right font-mono text-text-muted'>
                    {getOr(
                      0,
                      'shares'
                    )(pos).toLocaleString(undefined, {
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className='p-4 text-right font-mono text-text-muted'>
                    ₹{getOr(0, 'cost_basis')(pos).toLocaleString()}
                  </td>
                  <td className='p-4 text-right font-mono font-bold text-text'>
                    ₹{getOr(0, 'last_price')(pos).toLocaleString()}
                  </td>
                  <td className='p-4 text-right font-mono font-black text-text'>
                    ₹
                    {getOr(
                      0,
                      'market_value'
                    )(pos).toLocaleString(undefined, {
                      maximumFractionDigits: 0,
                    })}
                  </td>
                  <td className={`p-4 text-right font-black ${pnlColor}`}>
                    {pnlPct >= 0 ? '+' : ''}
                    {pnlPct.toFixed(2)}%
                  </td>
                  <td className='p-4 text-right font-bold text-text-muted'>
                    {getOr(0, 'weight_pct')(pos).toFixed(1)}%
                  </td>
                  <td className='p-4 text-text-muted font-medium'>
                    {formatDisplayDate(pos.entry_date)}
                  </td>
                </tr>
              );
            })(positions)}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default S3PaperBook;
