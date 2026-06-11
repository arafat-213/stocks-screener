import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Star,
  Zap,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Target,
  AlertTriangle,
  CheckCircle2,
  TrendingUp as MoveUp,
  XCircle,
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

  // Handle both old schema (`actionable`) and new DB schema (`new_signals`)
  const actionable = digestData?.new_signals || digestData?.actionable || [];
  const exits = digestData?.closed_positions || [];
  const entries = digestData?.opened_positions || [];
  const trails = digestData?.trail_moved || [];
  const warnings = digestData?.warnings || [];

  if (!digestData && !loadingDigest) return null;

  return (
    <section className='flex flex-col gap-6 animate-fade-in mb-12'>
      <div className='bg-bg-secondary border-2 border-border rounded-3xl overflow-hidden shadow-md transition-all hover:shadow-xl hover:border-blue-500/30'>
        {/* Header - Premium Redesign */}
        <div className='px-8 py-6 border-b-2 border-border flex flex-col md:flex-row md:justify-between md:items-center gap-4 bg-gradient-to-r from-blue-600 to-indigo-700 text-white relative overflow-hidden'>
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
                  Daily Digest
                </h2>
                <span className='bg-white/20 px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-widest border border-white/20'>
                  LATEST
                </span>
              </div>
              <p className='m-0 text-[10px] font-bold text-white/80 uppercase tracking-[0.2em] mt-1.5 flex items-center gap-2'>
                <span className='w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse'></span>
                Generated: {digestData?.date}
              </p>
            </div>
          </div>

          <div className='flex flex-wrap gap-3 relative z-10'>
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

        {/* 1. Exits & Stops Hit */}
        {exits.length > 0 && (
          <div className='p-6 border-b border-border'>
            <h3 className='text-sm font-black text-red-600 dark:text-red-500 uppercase tracking-tight mb-4 flex items-center gap-2'>
              <XCircle size={16} /> Exits & Stops Hit ({exits.length})
            </h3>
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
              {exits.map((p, idx) => (
                <div
                  key={idx}
                  className='bg-slate-50 dark:bg-slate-800/50 p-4 rounded-xl border border-red-100 dark:border-red-900/30'
                >
                  <div className='flex justify-between items-center mb-2'>
                    <span className='font-black text-sm'>
                      {p.symbol.replace('.NS', '')}
                    </span>
                    <span
                      className={`text-xs font-black px-2 py-0.5 rounded ${p.return_pct > 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}
                    >
                      {p.return_pct > 0 ? '+' : ''}
                      {p.return_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className='text-xs text-text-muted space-y-1'>
                    <div>
                      Reason:{' '}
                      <span className='font-bold text-text'>
                        {p.reason.replace('_', ' ')}
                      </span>
                    </div>
                    <div>Exit Price: ₹{p.exit_price?.toFixed(2)}</div>
                    <div>Days Held: {p.holding_days}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 2. Entries Triggered */}
        {entries.length > 0 && (
          <div className='p-6 border-b border-border'>
            <h3 className='text-sm font-black text-green-600 dark:text-green-500 uppercase tracking-tight mb-4 flex items-center gap-2'>
              <CheckCircle2 size={16} /> Entries Triggered ({entries.length})
            </h3>
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
              {entries.map((p, idx) => (
                <div
                  key={idx}
                  className='bg-slate-50 dark:bg-slate-800/50 p-4 rounded-xl border border-green-100 dark:border-green-900/30'
                >
                  <div className='flex justify-between items-center mb-2'>
                    <span className='font-black text-sm'>
                      {p.symbol?.replace('.NS', '')}
                    </span>
                    <span className='text-xs font-black text-green-600 bg-green-100 px-2 py-0.5 rounded uppercase'>
                      {p.entry_type?.replace('_', ' ')}
                    </span>
                  </div>
                  <div className='text-xs text-text-muted space-y-1'>
                    <div>
                      Filled:{' '}
                      <span className='font-bold text-text'>
                        ₹{p.entry_price?.toFixed(2)}
                      </span>
                    </div>
                    <div>Initial SL: ₹{p.stop_loss?.toFixed(2)}</div>
                    <div>Target: ₹{p.target?.toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 3. Trail Moved & Warnings */}
        {(trails.length > 0 || warnings.length > 0) && (
          <div className='p-6 border-b border-border'>
            <h3 className='text-sm font-black text-amber-600 dark:text-amber-500 uppercase tracking-tight mb-4 flex items-center gap-2'>
              <AlertTriangle size={16} /> Position Updates (
              {trails.length + warnings.length})
            </h3>
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
              {warnings.map((w, idx) => (
                <div
                  key={`w-${idx}`}
                  className='bg-slate-50 dark:bg-slate-800/50 p-4 rounded-xl border border-amber-100 dark:border-amber-900/30'
                >
                  <div className='flex justify-between items-center mb-2'>
                    <span className='font-black text-sm'>
                      {w.symbol.replace('.NS', '')}
                    </span>
                    <span
                      className={`text-[10px] font-black px-2 py-0.5 rounded uppercase ${w.alert_type.includes('target') ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}
                    >
                      {w.alert_type.includes('target')
                        ? 'Near Target'
                        : 'Near Stop'}
                    </span>
                  </div>
                  <div className='text-xs text-text-muted space-y-1'>
                    <div>
                      CMP:{' '}
                      <span className='font-bold text-text'>
                        ₹{w.current_price?.toFixed(2)}
                      </span>
                    </div>
                    <div>
                      Level: ₹
                      {(w.alert_type.includes('target')
                        ? w.target
                        : w.stop_loss
                      )?.toFixed(2)}
                    </div>
                  </div>
                </div>
              ))}
              {trails.map((t, idx) => (
                <div
                  key={`t-${idx}`}
                  className='bg-slate-50 dark:bg-slate-800/50 p-4 rounded-xl border border-blue-100 dark:border-blue-900/30'
                >
                  <div className='flex justify-between items-center mb-2'>
                    <span className='font-black text-sm'>
                      {t.symbol.replace('.NS', '')}
                    </span>
                    <span className='text-[10px] font-black px-2 py-0.5 rounded uppercase bg-blue-100 text-blue-700 flex items-center gap-1'>
                      <MoveUp size={10} /> Trail SL
                    </span>
                  </div>
                  <div className='text-xs text-text-muted space-y-1'>
                    <div>
                      CMP:{' '}
                      <span className='font-bold text-text'>
                        ₹{t.current_price?.toFixed(2)}
                      </span>
                    </div>
                    <div>New SL: ₹{t.new_trail_stop?.toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. New Signals */}
        <div className='p-6'>
          <h3 className='text-sm font-black text-blue-600 dark:text-blue-500 uppercase tracking-tight mb-4 flex items-center gap-2'>
            <Star size={16} /> New Pending Signals ({actionable.length})
          </h3>
          {actionable.length > 0 ? (
            <div className='p-0 -mx-6'>
              <DataTable
                columns={digestColumns}
                data={actionable}
                initialSort={{ key: 'score', direction: 'desc' }}
                loading={loadingDigest}
              />
            </div>
          ) : (
            <div className='text-sm text-text-muted italic py-4'>
              No actionable signals today.
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default HighConvictionDigest;
