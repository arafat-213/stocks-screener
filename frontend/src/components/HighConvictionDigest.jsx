import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Star,
  ShieldCheck,
  Zap,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Target,
} from 'lucide-react';
import { getLatestDigest } from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { DataTable } from './ui/DataTable';
import { ErrorBanner } from './ui/ErrorBanner';

const HighConvictionDigest = () => {
  const {
    data: digestData,
    loading: loadingDigest,
    error: digestError,
  } = useFetch(getLatestDigest);

  const digestColumns = useMemo(
    () => [
      {
        key: 'symbol',
        label: 'Symbol',
        sortable: true,
        render: (val) => (
          <Link
            to={`/stocks/${val}`}
            className='text-blue-600 dark:text-blue-400 font-black no-underline hover:underline transition-all tracking-tighter flex items-center gap-2'
          >
            {val.replace('.NS', '')}
            <ArrowRight
              size={12}
              className='opacity-0 group-hover:opacity-100 transition-opacity'
            />
          </Link>
        ),
      },
      {
        key: 'tier',
        label: 'Tier',
        sortable: true,
        render: (val) => (
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${val === 1 ? 'bg-green-500 text-white shadow-sm shadow-green-500/20' : 'bg-blue-500 text-white shadow-sm shadow-blue-500/20'}`}
          >
            T{val}
          </span>
        ),
      },
      {
        key: 'score',
        label: 'Score',
        sortable: true,
        render: (val) => (
          <span className='font-black font-mono text-sm text-text'>
            {val?.toFixed(1)}
          </span>
        ),
      },
      {
        key: 'pullback_entry_zone',
        label: 'Entry Zone',
        render: (val) =>
          val ? (
            <div className='flex flex-col gap-0.5'>
              <div className='flex items-center gap-1.5'>
                <Target size={10} className='text-blue-500' />
                <span className='text-[10px] font-black text-text'>
                  ₹{val.target?.toLocaleString('en-IN')}
                </span>
              </div>
              <span className='text-[9px] text-text-muted font-bold ml-3.5'>
                Limit: ₹{val.tolerance_high?.toLocaleString('en-IN')}
              </span>
            </div>
          ) : (
            <div className='flex items-center gap-1.5'>
              <Zap size={10} className='text-amber-500 fill-amber-500' />
              <span className='text-[10px] font-black text-amber-600 dark:text-amber-400 uppercase tracking-tighter'>
                Momentum
              </span>
            </div>
          ),
      },
      {
        key: 'stop_reference',
        label: 'Stop Loss',
        render: (val) => (
          <span className='text-[10px] font-black text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-2 py-0.5 rounded border border-red-100 dark:border-red-900/50'>
            ₹{val?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
          </span>
        ),
      },
      {
        key: 'sector',
        label: 'Sector',
        sortable: true,
        render: (val) => (
          <span className='text-[10px] font-bold text-text-muted uppercase tracking-tight truncate max-w-[120px] block'>
            {val}
          </span>
        ),
      },
    ],
    []
  );

  if (digestError)
    return <ErrorBanner message={`Failed to load digest: ${digestError}`} />;
  if (loadingDigest && !digestData) {
    return (
      <div className='bg-bg-secondary border-2 border-border rounded-3xl overflow-hidden shadow-sm mb-10'>
        <div className='h-24 bg-slate-100 dark:bg-slate-900 animate-pulse border-b-2 border-border'></div>
        <div className='p-8 space-y-4'>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className='h-12 bg-slate-50 dark:bg-slate-800/50 rounded-xl animate-pulse'
            ></div>
          ))}
        </div>
      </div>
    );
  }

  const actionable = digestData?.actionable || [];
  if (actionable.length === 0 && !loadingDigest) return null;

  return (
    <section className='flex flex-col gap-6 animate-fade-in mb-12'>
      <div className='bg-bg-secondary border-2 border-border rounded-3xl overflow-hidden shadow-md transition-all hover:shadow-xl hover:border-blue-500/30'>
        {/* Header - Premium Redesign */}
        <div className='px-8 py-6 border-b-2 border-border flex flex-col md:flex-row md:justify-between md:items-center gap-4 bg-gradient-to-r from-blue-600 to-indigo-700 text-white relative overflow-hidden'>
          {/* Decorative Background Elements */}
          <div className='absolute -right-10 -top-10 w-40 h-40 bg-white/10 rounded-full blur-3xl'></div>
          <div className='absolute -left-10 -bottom-10 w-40 h-40 bg-blue-400/20 rounded-full blur-3xl'></div>

          <div className='flex items-center gap-4 relative z-10'>
            <div className='bg-white/20 p-3 rounded-2xl backdrop-blur-xl border border-white/30 shadow-inner group'>
              <Star
                size={28}
                className='fill-white text-white group-hover:scale-110 transition-transform duration-300'
              />
            </div>
            <div>
              <div className='flex items-center gap-2'>
                <h2 className='m-0 text-xl md:text-2xl font-black uppercase tracking-tight'>
                  High Conviction Digest
                </h2>
                <span className='bg-white/20 px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-widest border border-white/20'>
                  LATEST
                </span>
              </div>
              <p className='m-0 text-[10px] font-bold text-white/80 uppercase tracking-[0.2em] mt-1.5 flex items-center gap-2'>
                <span className='w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse'></span>
                Surgical entry zones: {digestData?.date}
              </p>
            </div>
          </div>

          <div className='flex flex-wrap gap-3 relative z-10'>
            <div className='flex flex-col items-end gap-1.5'>
              <span className='text-[9px] font-black text-white/60 uppercase tracking-widest'>
                STATUS
              </span>
              <span className='text-[10px] font-black py-1.5 px-4 bg-white/20 rounded-xl uppercase tracking-[0.15em] backdrop-blur-md border border-white/20 shadow-sm'>
                {actionable.length} ACTIONABLE
              </span>
            </div>
            <div className='flex flex-col items-end gap-1.5'>
              <span className='text-[9px] font-black text-white/60 uppercase tracking-widest'>
                MARKET REGIME
              </span>
              <span
                className={`text-[10px] font-black py-1.5 px-4 rounded-xl uppercase tracking-[0.15em] border shadow-sm flex items-center gap-2 ${digestData?.regime_bullish ? 'bg-green-500 border-green-400' : 'bg-red-500 border-red-400'}`}
              >
                {digestData?.regime_bullish ? (
                  <>
                    <TrendingUp size={14} /> BULL REGIME
                  </>
                ) : (
                  <>
                    <TrendingDown size={14} /> BEAR REGIME
                  </>
                )}
              </span>
            </div>
          </div>
        </div>

        {/* Actionable Content */}
        <div className='p-0'>
          <DataTable
            columns={digestColumns}
            data={actionable}
            initialSort={{ key: 'score', direction: 'desc' }}
            loading={loadingDigest}
          />
        </div>

        {/* Footer/Summary */}
        <div className='px-8 py-4 bg-slate-50 dark:bg-slate-900/50 flex justify-between items-center border-t border-border'>
          <span className='text-[10px] font-black text-text-muted uppercase tracking-widest'>
            Top {actionable.length} picks for today's session
          </span>
          <Link
            to='/intel'
            className='text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-widest flex items-center gap-2 no-underline hover:gap-3 transition-all'
          >
            View Historical Reports <ArrowRight size={14} />
          </Link>
        </div>
      </div>

      {/* Secondary Watchlist - Optional/Collapsible or simplified */}
      {digestData?.watchlist?.length > 0 && (
        <div className='bg-bg-secondary border-2 border-border rounded-3xl p-6 shadow-sm border-dashed'>
          <div className='flex items-center justify-between mb-4'>
            <div className='flex items-center gap-3'>
              <div className='bg-amber-500/10 p-2 rounded-xl border border-amber-500/20'>
                <ShieldCheck size={18} className='text-amber-500' />
              </div>
              <h2 className='text-sm font-black uppercase tracking-tight text-text'>
                Secondary Watchlist
              </h2>
            </div>
            <span className='text-[10px] font-black text-text-muted bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full border border-border'>
              {digestData.watchlist.length} STOCKS
            </span>
          </div>

          <div className='grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3'>
            {digestData.watchlist.map((stock) => (
              <Link
                key={stock.symbol}
                to={`/stocks/${stock.symbol}`}
                className='bg-white dark:bg-slate-900 border border-border p-3 rounded-xl hover:border-blue-500 transition-all no-underline group'
              >
                <div className='font-black text-xs text-text group-hover:text-blue-500 transition-colors'>
                  {stock.symbol.replace('.NS', '')}
                </div>
                <div className='text-[9px] font-bold text-text-muted truncate mt-1'>
                  Score: {stock.score?.toFixed(1)}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

export default HighConvictionDigest;
