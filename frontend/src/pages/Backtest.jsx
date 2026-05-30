import { useState, useCallback, useMemo, memo } from 'react';
import {
  Play,
  History,
  Settings,
  BarChart3,
  TrendingUp,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Layers,
  Info,
  Calendar,
  Loader2,
  ExternalLink,
  ShieldCheck,
  Zap,
  TrendingDown,
  RotateCcw,
  Target,
  Clock,
  Briefcase,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Link } from 'react-router-dom';

import {
  runBacktest,
  getBacktestRun,
  getBacktestRuns,
  getBacktestTrades,
  getScreensList,
} from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { useTheme } from '../hooks/useTheme';
import { DataTable } from '../components/ui/DataTable';
import Slider from '../components/ui/Slider';
import Toggle from '../components/ui/Toggle';
import { ErrorBanner } from '../components/ui/ErrorBanner';

// rerender-memo: Memoize expensive result components to isolate them from config changes
const BacktestResults = memo(
  ({
    activeRun,
    tradesData,
    tradesPage,
    totalTradesCount,
    tradeColumns,
    loadingTrades,
    isDark,
    pageSize,
    onPageChange,
  }) => {
    if (!activeRun) return null;

    const metrics = activeRun?.metrics;

    if (activeRun.status === 'running' || activeRun.status === 'pending') {
      return (
        <div className='bg-bg-secondary border-2 border-border rounded-2xl p-8 text-center shadow-sm'>
          <div className='flex justify-between items-center mb-4'>
            <h3 className='text-xl font-black text-text uppercase tracking-tight'>
              Backtest in Progress...
            </h3>
            <span className='font-black text-blue-500 text-2xl'>
              {activeRun.progress.pct}%
            </span>
          </div>
          <div className='h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden mb-4 border border-border'>
            <div
              className='h-full bg-blue-600 shadow-[0_0_12px_rgba(37,99,235,0.4)] transition-all duration-300'
              style={{ width: `${activeRun.progress.pct}%` }}
            ></div>
          </div>
          <p className='text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest'>
            Processing symbols: {activeRun.progress.symbols_done} /{' '}
            {activeRun.progress.symbols_total}
          </p>
        </div>
      );
    }

    if (activeRun.status === 'failed') {
      return (
        <div className='bg-red-500/10 border-2 border-red-500/30 rounded-2xl p-6 shadow-sm'>
          <h3 className='text-red-600 dark:text-red-400 flex items-center gap-2 mb-3 font-black uppercase tracking-tight text-lg'>
            <AlertTriangle size={24} /> Backtest Failed
          </h3>
          <p className='text-sm font-bold text-text'>
            {activeRun.error_message ||
              'An unknown error occurred during execution.'}
          </p>
        </div>
      );
    }

    if (activeRun.status === 'complete' && metrics) {
      return (
        <>
          {/* Metrics Grid */}
          {metrics.total_trades < 100 && (
            <div className='bg-amber-500/10 border-2 border-amber-500/20 rounded-xl p-4 flex gap-4 text-amber-700 dark:text-amber-400 text-sm leading-relaxed mb-6 shadow-sm'>
              <AlertTriangle size={24} className='shrink-0 text-amber-500' />
              <div className='font-bold'>
                <strong className='uppercase tracking-wide text-xs block mb-1'>
                  Low sample size warning
                </strong>
                Only {metrics.total_trades} trades recorded. Statistical
                confidence requires at least 100 trades.
              </div>
            </div>
          )}
          <div className='grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] sm:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3 sm:gap-4'>
            {[
              // 1. Headline Returns & Risk
              {
                label: 'Total Return',
                value: `${metrics.total_return_pct?.toFixed(2)}%`,
                className:
                  metrics.total_return_pct >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400',
              },
              {
                label: 'vs Nifty 50',
                value: `${(metrics.total_return_pct - metrics.benchmark_return_pct).toFixed(1)}%`,
                className:
                  metrics.total_return_pct >= metrics.benchmark_return_pct
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
                isBadge: true,
              },
              {
                label: 'Max Drawdown',
                value: `${metrics.max_drawdown_pct?.toFixed(1)}%`,
                className:
                  'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
                isBadge: true,
              },
              {
                label: 'Sharpe Ratio',
                value: metrics.sharpe_ratio?.toFixed(2),
                className: 'text-blue-600 dark:text-blue-400',
              },

              // 2. High-Level Strategy Stats
              { label: 'Total Trades', value: metrics.total_trades },
              {
                label: 'Win Rate',
                value: `${metrics.win_rate?.toFixed(1)}%`,
                className:
                  metrics.win_rate >= 50
                    ? 'bg-green-500 text-white shadow-green-500/20'
                    : 'bg-red-500 text-white shadow-red-500/20',
                isBadge: true,
              },
              {
                label: 'Profit Factor',
                value: metrics.profit_factor?.toFixed(2),
                className:
                  metrics.profit_factor >= 1
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400',
              },
              {
                label: 'Expectancy',
                value: `${metrics.expectancy?.toFixed(2)}%`,
                className:
                  metrics.expectancy >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400',
              },

              // 3. Trade Averages & Medians
              {
                label: 'Avg Return',
                value: `${metrics.avg_return_pct?.toFixed(2)}%`,
                className:
                  metrics.avg_return_pct >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400',
              },
              {
                label: 'Median Return',
                value: `${metrics.median_return_pct?.toFixed(2)}%`,
                className:
                  metrics.median_return_pct >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400',
              },
              {
                label: 'Avg Win',
                value: `+${metrics.avg_win_pct?.toFixed(2)}%`,
                className: 'text-green-600 dark:text-green-400',
              },
              {
                label: 'Avg Loss',
                value: `${metrics.avg_loss_pct?.toFixed(2)}%`,
                className: 'text-red-600 dark:text-red-400',
              },

              // 4. Extremes & Costs
              {
                label: 'Best Trade',
                value: `+${metrics.best_trade_pct?.toFixed(2)}%`,
                className: 'text-green-600 dark:text-green-400',
              },
              {
                label: 'Worst Trade',
                value: `${metrics.worst_trade_pct?.toFixed(2)}%`,
                className: 'text-red-600 dark:text-red-400',
              },
              {
                label: 'Gross Return',
                value: `${metrics.gross_return_pct?.toFixed(2)}%`,
                className:
                  metrics.gross_return_pct >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400',
              },
              {
                label: 'Cost Drag',
                value: `-${metrics.total_cost_drag_pct?.toFixed(2)}%`,
                className: 'text-red-600 dark:text-red-400',
              },
            ].map((m, idx) => (
              <div
                key={m.label}
                className='bg-bg-secondary border-2 border-border rounded-2xl p-5 flex flex-col gap-2 transition-all hover:border-blue-500/30 shadow-sm animate-fade-in'
                style={{ '--delay': `${idx * 0.05}s` }}
              >
                <span className='text-[10px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-[0.15em]'>
                  {m.label}
                </span>
                {m.isBadge ? (
                  <span
                    className={`text-lg font-black font-mono w-fit px-2 py-0.5 rounded-lg shadow-sm ${m.className}`}
                  >
                    {m.value}
                  </span>
                ) : (
                  <span
                    className={`text-2xl font-black font-mono tracking-tighter ${m.className || 'text-text'}`}
                  >
                    {m.value}
                  </span>
                )}
              </div>
            ))}
          </div>

          <div
            className='bg-bg-secondary border-2 border-border rounded-2xl p-6 shadow-sm animate-fade-in'
            style={{ '--delay': '0.55s' }}
          >
            <h3 className='text-lg font-black flex items-center gap-3 mb-6 text-text uppercase tracking-tight'>
              <Target size={20} className='text-blue-500' /> Exit Distribution
            </h3>
            <div className='grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4'>
              {[
                { key: 'target', label: 'Hit Target', color: 'bg-green-500' },
                {
                  key: 'target_partial',
                  label: 'Partial Target',
                  color: 'bg-green-400',
                },
                { key: 'stop_loss', label: 'Stop Loss', color: 'bg-red-500' },
                {
                  key: 'trailing_stop',
                  label: 'Trailing Stop',
                  color: 'bg-amber-500',
                },
                {
                  key: 'atr_trailing_stop',
                  label: 'ATR Trail Stop',
                  color: 'bg-blue-500',
                },
                {
                  key: 'signal_invalidated',
                  label: 'Signal Invalid',
                  color: 'bg-slate-400',
                },
                {
                  key: 'holding_period',
                  label: 'Held to End',
                  color: 'bg-slate-500',
                },
              ].map(({ key, label, color }) => {
                const count = metrics.exit_breakdown[key] || 0;
                const pct =
                  metrics.total_trades > 0
                    ? (count / metrics.total_trades) * 100
                    : 0;
                if (count === 0) return null;
                return (
                  <div
                    key={key}
                    className='flex flex-col gap-1.5 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-border'
                  >
                    <div className='flex justify-between items-center text-[11px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400'>
                      <span>{label}</span>
                      <span>{count}</span>
                    </div>
                    <div className='h-1.5 bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden'>
                      <div
                        className={`h-full ${color} rounded-full`}
                        style={{ width: `${pct}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Equity Curve Chart */}
          <div
            className='bg-bg-secondary border-2 border-border rounded-2xl p-6 shadow-sm animate-fade-in'
            style={{ '--delay': '0.5s' }}
          >
            <h3 className='text-lg font-black flex items-center gap-3 mb-8 text-text uppercase tracking-tight'>
              <TrendingUp size={20} className='text-blue-500' /> Equity Curve
              Performance
            </h3>
            <div className='w-full h-[400px]'>
              <ResponsiveContainer>
                <LineChart data={activeRun.equity_curve}>
                  <CartesianGrid
                    strokeDasharray='3 3'
                    stroke={isDark ? '#1E293B' : '#E2E8F0'}
                    vertical={false}
                  />
                  <XAxis
                    dataKey='date'
                    stroke='#64748B'
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    dy={10}
                    tickFormatter={(str) => {
                      const date = new Date(str);
                      return date.toLocaleDateString([], {
                        month: 'short',
                        year: '2-digit',
                      });
                    }}
                  />
                  <YAxis
                    stroke='#64748B'
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    dx={-10}
                    tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: isDark ? '#0F172A' : '#FFFFFF',
                      borderColor: isDark ? '#1E293B' : '#E2E8F0',
                      borderRadius: '12px',
                      boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
                      border: '2px solid',
                      fontFamily: 'monospace',
                    }}
                    itemStyle={{ fontWeight: '900', fontSize: '12px' }}
                  />
                  <Legend
                    verticalAlign='top'
                    align='right'
                    iconType='circle'
                    wrapperStyle={{
                      paddingBottom: '20px',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      textTransform: 'uppercase',
                    }}
                  />
                  <Line
                    name='Strategy Equity'
                    type='monotone'
                    dataKey='equity'
                    stroke='#3B82F6'
                    strokeWidth={4}
                    dot={false}
                    activeDot={{ r: 6, strokeWidth: 0, fill: '#3B82F6' }}
                  />
                  <Line
                    name='Benchmark (Nifty 50)'
                    type='monotone'
                    dataKey='benchmark_equity'
                    stroke='#94A3B8'
                    strokeWidth={2}
                    strokeDasharray='6 4'
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Trades Table */}
          <div
            className='bg-bg-secondary border-2 border-border rounded-2xl p-6 shadow-sm animate-fade-in overflow-hidden'
            style={{ '--delay': '0.6s' }}
          >
            <div className='flex justify-between items-center mb-6'>
              <h3 className='text-lg font-black flex items-center gap-3 text-text uppercase tracking-tight'>
                <Layers size={20} className='text-blue-500' /> Performance
                Journal
              </h3>
              <div className='flex items-center gap-4'>
                <span className='text-[11px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full'>
                  {totalTradesCount} TOTAL TRADES
                </span>
                <div className='flex items-center gap-2'>
                  <button
                    className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-lg p-2 cursor-pointer transition-all hover:border-blue-500 disabled:opacity-30'
                    onClick={() => onPageChange((p) => Math.max(1, p - 1))}
                    disabled={tradesPage === 1}
                  >
                    <ChevronLeft size={16} className='text-text' />
                  </button>
                  <span className='font-black font-mono text-sm min-w-[20px] text-center'>
                    {tradesPage}
                  </span>
                  <button
                    className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-lg p-2 cursor-pointer transition-all hover:border-blue-500 disabled:opacity-30'
                    onClick={() => onPageChange((p) => p + 1)}
                    disabled={tradesPage * pageSize >= totalTradesCount}
                  >
                    <ChevronRight size={16} className='text-text' />
                  </button>
                </div>
              </div>
            </div>
            <DataTable
              columns={tradeColumns}
              data={tradesData?.trades || []}
              loading={loadingTrades}
              skeletonRows={10}
            />
          </div>
        </>
      );
    }

    return null;
  }
);

const Backtest = () => {
  const { isDark } = useTheme();

  // rerender-lazy-state-init: Initialize state once
  const [config, setConfig] = useState(() => ({
    screen_slug: 'all',
    score_threshold: 55,
    holding_days: 20,
    stop_loss_pct: 7.0,
    target_pct: 0.0,
    trailing_stop_pct: 0.0,
    use_atr_stops: true,
    atr_multiplier: 2.0,
    risk_reward_ratio: 2.5,
    use_atr_trailing_stop: true,
    atr_trailing_multiplier: 2.0,
    atr_trailing_activation: 2.0,
    use_partial_exits: false,
    use_signal_invalidation_exit: false,
    invalidation_threshold_pct: 3.0,
    use_regime_filter: true,
    require_volume_breakout: false,
    require_weekly_confirmation: true,
    require_monthly_confirmation: false,
    starting_capital: 1000000,
    position_size: 10000,
    use_volatility_sizing: true,
    max_concurrent_positions: 0,
    max_sector_positions: 0,
    include_fundamentals: false,
    symbol_limit: 350,
    date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
      .toISOString()
      .split('T')[0],
    date_to: new Date().toISOString().split('T')[0],
  }));

  const [activeRunId, setActiveRunId] = useState(null);
  const [activeTab, setActiveTab] = useState('strategy');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [tradesPage, setTradesPage] = useState(1);
  const pageSize = 50;

  // Fetch Available Screens
  const { data: screens } = useFetch(getScreensList);

  // Fetch Recent Runs
  const { data: recentRuns, refetch: refetchRecentRuns } =
    useFetch(getBacktestRuns);

  // Fetch Active Run (with polling)
  const fetchActiveRun = useCallback(() => {
    if (!activeRunId) return Promise.resolve(null);
    return getBacktestRun(activeRunId);
  }, [activeRunId]);

  const {
    data: activeRun,
    loading: loadingActiveRun,
    error: activeRunError,
  } = useFetch(fetchActiveRun, {
    deps: [activeRunId],
    refreshInterval: (data) =>
      data?.status === 'running' || data?.status === 'pending' ? 3000 : null,
  });

  // Fetch Trades for Active Run
  const fetchTrades = useCallback(() => {
    if (!activeRunId || activeRun?.status !== 'complete')
      return Promise.resolve({ trades: [], total: 0 });
    return getBacktestTrades(activeRunId, {
      page: tradesPage,
      page_size: pageSize,
    });
  }, [activeRunId, activeRun?.status, tradesPage]);

  const { data: tradesData, loading: loadingTrades } = useFetch(fetchTrades, {
    deps: [activeRunId, activeRun?.status, tradesPage],
  });

  // rerender-move-effect-to-event: Logic belongs in the event handler
  const handleRunBacktest = useCallback(async () => {
    try {
      setIsSubmitting(true);
      // Use the live config for starting the backtest
      const res = await runBacktest(config);
      setActiveRunId(res.data.run_id);
      refetchRecentRuns();
    } catch (err) {
      console.error('Failed to start backtest:', err);
      alert(
        'Failed to start backtest: ' +
          (err.response?.data?.detail || err.message)
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [config, refetchRecentRuns]);

  const handleSelectRun = useCallback((runId) => {
    setActiveRunId(runId);
    setTradesPage(1);
  }, []);

  const handleResetConfig = useCallback(() => {
    setConfig({
      screen_slug: 'all',
      score_threshold: 60,
      holding_days: 20,
      stop_loss_pct: 7.0,
      target_pct: 0.0,
      trailing_stop_pct: 0.0,
      use_atr_stops: true,
      atr_multiplier: 2.0,
      risk_reward_ratio: 2.5,
      use_atr_trailing_stop: true,
      atr_trailing_multiplier: 2.0,
      atr_trailing_activation: 2.0,
      use_partial_exits: false,
      use_signal_invalidation_exit: false,
      invalidation_threshold_pct: 3.0,
      use_regime_filter: true,
      require_volume_breakout: true,
      require_weekly_confirmation: true,
      require_monthly_confirmation: false,
      include_fundamentals: false,
      symbol_limit: 350,
      date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
        .toISOString()
        .split('T')[0],
      date_to: new Date().toISOString().split('T')[0],
      starting_capital: 1000000,
      position_size: 10000,
      use_volatility_sizing: true,
      max_concurrent_positions: 0,
      max_sector_positions: 0,
    });
  }, []);

  // rerender-functional-setstate: Stable handler for all config changes
  const handleConfigChange = useCallback((key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }, []);

  const totalTradesCount = tradesData?.total || 0;

  // rerender-memo: Column definitions are static or have stable dependencies
  const tradeColumns = useMemo(
    () => [
      {
        key: 'symbol',
        label: 'Symbol',
        render: (val) => (
          <Link
            to={`/stocks/${val}`}
            className='text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 font-black tracking-tighter'
          >
            {val.replace('.NS', '')} <ExternalLink size={12} />
          </Link>
        ),
      },
      {
        key: 'signal_date',
        label: 'Signal Date',
        render: (val) =>
          val ? (
            <span className='font-bold text-slate-500 dark:text-slate-400'>
              {new Date(val).toLocaleDateString()}
            </span>
          ) : (
            '-'
          ),
      },
      {
        key: 'entry_price',
        label: 'Entry',
        render: (val) => (
          <span className='font-mono font-bold'>₹{val?.toFixed(2)}</span>
        ),
      },
      {
        key: 'exit_price',
        label: 'Exit',
        render: (val) => (
          <span className='font-mono font-bold'>₹{val?.toFixed(2)}</span>
        ),
      },
      {
        key: 'days_held',
        label: 'Days',
        render: (_, row) => {
          if (!row.entry_date || !row.exit_date) return '-';
          const start = new Date(row.entry_date);
          const end = new Date(row.exit_date);
          const diff = Math.ceil(Math.abs(end - start) / (1000 * 60 * 60 * 24));
          return (
            <span className='font-mono font-black text-slate-600 dark:text-slate-300'>
              {diff}d
            </span>
          );
        },
      },
      {
        key: 'signal_score',
        label: 'Score',
        render: (val) => (
          <span
            className={`font-black font-mono ${val >= 70 ? 'text-green-500' : val >= 50 ? 'text-blue-500' : 'text-text'}`}
          >
            {val?.toFixed(1)}
          </span>
        ),
      },
      {
        key: 'return_pct',
        label: 'Return %',
        render: (val) => (
          <span
            className={`font-black font-mono px-2 py-0.5 rounded shadow-sm ${val >= 0 ? 'bg-green-500 text-white' : 'bg-red-500 text-white'}`}
          >
            {val >= 0 ? '+' : ''}
            {val?.toFixed(2)}%
          </span>
        ),
      },
      {
        key: 'exit_reason',
        label: 'Reason',
        render: (val) => {
          const reasonClasses = {
            stop_loss: 'bg-red-500 text-white',
            trailing_stop: 'bg-amber-500 text-white',
            target: 'bg-green-500 text-white',
            holding_period: 'bg-blue-600 text-white',
          };
          const reasonClass =
            reasonClasses[val] ||
            'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
          return (
            <span
              className={`text-[10px] px-2 py-1 rounded-md font-black uppercase tracking-widest shadow-sm ${reasonClass}`}
            >
              {val?.replace('_', ' ')}
            </span>
          );
        },
      },
    ],
    []
  );

  return (
    <div className='w-full animate-fade-in'>
      <header className='mb-10'>
        <h1 className='text-3xl sm:text-4xl font-black flex items-center gap-4 text-text tracking-tighter'>
          <History className='text-blue-500' size={40} /> Backtest Engine
        </h1>
        <p className='text-slate-500 dark:text-slate-400 mt-2 font-medium uppercase tracking-[0.1em] text-xs'>
          Simulate screening strategies against historical NSE daily data.
        </p>
      </header>

      <div className='grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 lg:gap-8 items-start'>
        {/* Sidebar Configuration */}
        <aside className='flex flex-col gap-6 lg:gap-8 lg:sticky lg:top-6'>
          <section className='bg-bg-secondary border-2 border-border rounded-2xl p-5 sm:p-6 shadow-sm'>
            <h2 className='text-[11px] font-black flex items-center gap-2 mb-6 text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em]'>
              <History size={16} /> Recent Runs
            </h2>
            <div className='flex flex-col gap-3 max-h-[400px] overflow-y-auto pr-2'>
              {recentRuns?.map((run) => (
                <div
                  key={run.run_id}
                  className={`p-4 rounded-xl border-2 transition-all duration-300 cursor-pointer group ${activeRunId === run.run_id ? 'bg-slate-50 dark:bg-slate-900 border-blue-500 shadow-lg shadow-blue-500/10' : 'bg-transparent border-transparent hover:border-slate-200 dark:hover:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-900/50'}`}
                  onClick={() => handleSelectRun(run.run_id)}
                >
                  <div className='flex justify-between items-start mb-2'>
                    <span
                      className={`text-[13px] font-black tracking-tight ${activeRunId === run.run_id ? 'text-blue-600 dark:text-blue-400' : 'text-text'}`}
                    >
                      {new Date(run.created_at).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    <span
                      className={`text-[9px] px-2 py-0.5 rounded-lg uppercase font-black tracking-widest shadow-sm
                      ${
                        run.status === 'complete'
                          ? 'bg-green-500 text-white'
                          : run.status === 'running'
                            ? 'bg-blue-600 text-white animate-pulse'
                            : run.status === 'failed'
                              ? 'bg-red-500 text-white'
                              : 'bg-slate-200 text-slate-500 dark:bg-slate-800'
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className='text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider flex flex-wrap gap-x-2 gap-y-1'>
                    <span>T:{run.config.score_threshold}</span>{' '}
                    <span>H:{run.config.holding_days}d</span>
                    <span>SL:{run.config.stop_loss_pct}%</span>
                    <span>
                      W:
                      {run.config.require_weekly_confirmation !== false
                        ? 'YES'
                        : 'NO'}
                    </span>
                  </div>
                </div>
              ))}
              {recentRuns?.length === 0 && (
                <p className='text-center text-slate-400 py-8 italic text-sm'>
                  No recent runs available
                </p>
              )}
            </div>
          </section>

          <section className='bg-bg-secondary border-2 border-border rounded-2xl p-6 shadow-sm'>
            <div className='flex justify-between items-center mb-6'>
              <h2 className='text-[11px] font-black flex items-center gap-2 text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em]'>
                <Settings size={16} /> Strategy Config
              </h2>
              <button
                className='text-slate-400 p-2 rounded-lg transition-all duration-300 hover:text-blue-500 hover:bg-slate-100 dark:hover:bg-slate-800'
                onClick={handleResetConfig}
                title='Reset to defaults'
              >
                <RotateCcw size={18} />
              </button>
            </div>

            <div className='flex gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl mb-6 border border-border/50'>
              {[
                { id: 'strategy', label: 'Engine', icon: Zap },
                { id: 'risk', label: 'Risk', icon: ShieldCheck },
                { id: 'account', label: 'Trade', icon: Briefcase },
              ].map((tab) => (
                <button
                  key={tab.id}
                  className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-[10px] font-black uppercase tracking-widest rounded-lg transition-all duration-300 cursor-pointer border-none ${activeTab === tab.id ? 'bg-bg-secondary text-blue-600 dark:text-blue-400 shadow-md border border-border/50' : 'text-slate-500 hover:text-text'}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <tab.icon size={14} />
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            <div className='flex flex-col gap-6'>
              {activeTab === 'strategy' && (
                <div className='flex flex-col gap-4 animate-fade-in'>
                  <div className='flex flex-col gap-2'>
                    <label className='text-[10px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-[0.2em] flex items-center gap-2'>
                      <Layers size={12} /> Starting Universe
                    </label>
                    <select
                      className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-4 py-3 text-text text-sm font-bold outline-none transition-all focus:border-blue-500'
                      value={config.screen_slug}
                      onChange={(e) =>
                        handleConfigChange('screen_slug', e.target.value)
                      }
                    >
                      <option value='all'>ALL NSE SYMBOLS</option>
                      {screens?.map((screen) => (
                        <option key={screen.slug} value={screen.slug}>
                          {screen.label.toUpperCase()}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Slider
                    label='Score Threshold'
                    value={config.score_threshold}
                    onChange={(val) =>
                      handleConfigChange('score_threshold', val)
                    }
                    min={0}
                    max={100}
                  />
                  <Slider
                    label='Max Holding (Days)'
                    value={config.holding_days}
                    onChange={(val) => handleConfigChange('holding_days', val)}
                    min={1}
                    max={252}
                  />
                  <Slider
                    label='Symbol Depth'
                    value={config.symbol_limit}
                    onChange={(val) => handleConfigChange('symbol_limit', val)}
                    min={10}
                    max={500}
                  />

                  <div className='flex flex-col gap-4 pt-6 border-t-2 border-border/50'>
                    <h3 className='text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-[0.3em] font-black mb-1'>
                      Strategy Filters
                    </h3>
                    <div className='space-y-4'>
                      <Toggle
                        label='Fundamental Filter'
                        checked={config.include_fundamentals}
                        onChange={(v) =>
                          handleConfigChange('include_fundamentals', v)
                        }
                      />
                      <Toggle
                        label='Market Regime'
                        checked={config.use_regime_filter}
                        onChange={(v) =>
                          handleConfigChange('use_regime_filter', v)
                        }
                      />
                      <Toggle
                        label='Volume Breakout'
                        checked={config.require_volume_breakout}
                        onChange={(v) =>
                          handleConfigChange('require_volume_breakout', v)
                        }
                      />
                      <Toggle
                        label='Weekly Confirmation'
                        checked={config.require_weekly_confirmation}
                        onChange={(v) =>
                          handleConfigChange('require_weekly_confirmation', v)
                        }
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'risk' && (
                <div className='flex flex-col gap-4 animate-fade-in'>
                  <Toggle
                    label='ATR Dynamic Stops'
                    checked={config.use_atr_stops}
                    onChange={(v) => handleConfigChange('use_atr_stops', v)}
                  />

                  {config.use_atr_stops ? (
                    <>
                      <Slider
                        label='ATR Multiplier'
                        min={1.0}
                        max={5.0}
                        step={0.1}
                        value={config.atr_multiplier}
                        onChange={(v) =>
                          handleConfigChange('atr_multiplier', v)
                        }
                      />
                      <Slider
                        label='Target RR Ratio'
                        min={1.0}
                        max={10.0}
                        step={0.5}
                        value={config.risk_reward_ratio}
                        onChange={(v) =>
                          handleConfigChange('risk_reward_ratio', v)
                        }
                      />
                    </>
                  ) : (
                    <>
                      <Slider
                        label='Fixed SL %'
                        min={1}
                        max={25}
                        value={config.stop_loss_pct}
                        onChange={(v) => handleConfigChange('stop_loss_pct', v)}
                      />
                      <Slider
                        label='Fixed TP %'
                        min={0}
                        max={100}
                        value={config.target_pct}
                        onChange={(v) => handleConfigChange('target_pct', v)}
                      />
                    </>
                  )}

                  <Slider
                    label='Manual Trail %'
                    min={0}
                    max={20}
                    step={0.5}
                    value={config.trailing_stop_pct}
                    onChange={(v) => handleConfigChange('trailing_stop_pct', v)}
                  />

                  <div className='flex flex-col gap-4 pt-6 border-t-2 border-border/50 mt-2'>
                    <h3 className='text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-[0.3em] font-black mb-1'>
                      Advanced Exits
                    </h3>
                    <div className='space-y-4'>
                      <Toggle
                        label='ATR Trailing Stop'
                        checked={config.use_atr_trailing_stop}
                        onChange={(v) =>
                          handleConfigChange('use_atr_trailing_stop', v)
                        }
                      />
                      {config.use_atr_trailing_stop && (
                        <>
                          <Slider
                            label='ATR Trail Multiplier'
                            min={0.5}
                            max={5.0}
                            step={0.1}
                            value={config.atr_trailing_multiplier}
                            onChange={(v) =>
                              handleConfigChange('atr_trailing_multiplier', v)
                            }
                          />
                          <Slider
                            label='ATR Trail Activation (×ATR profit)'
                            min={0.5}
                            max={5.0}
                            step={0.1}
                            value={config.atr_trailing_activation}
                            onChange={(v) =>
                              handleConfigChange('atr_trailing_activation', v)
                            }
                          />
                        </>
                      )}
                      <Toggle
                        label='Partial Take-Profit'
                        checked={config.use_partial_exits}
                        onChange={(v) =>
                          handleConfigChange('use_partial_exits', v)
                        }
                      />
                      <Toggle
                        label='Signal Invalidation'
                        checked={config.use_signal_invalidation_exit}
                        onChange={(v) =>
                          handleConfigChange('use_signal_invalidation_exit', v)
                        }
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'account' && (
                <div className='flex flex-col gap-5 animate-fade-in'>
                  <div className='flex flex-col gap-2'>
                    <label className='text-[10px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-[0.2em]'>
                      Starting Capital (₹)
                    </label>
                    <input
                      type='number'
                      className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-4 py-3 text-text font-mono font-bold text-sm focus:border-blue-500 outline-none'
                      value={config.starting_capital}
                      onChange={(e) =>
                        handleConfigChange(
                          'starting_capital',
                          parseFloat(e.target.value) || 1000000
                        )
                      }
                      step={100000}
                    />
                  </div>
                  <div className='flex flex-col gap-2'>
                    <label className='text-[10px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-[0.2em]'>
                      Trade Size (₹)
                    </label>
                    <input
                      type='number'
                      className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-4 py-3 text-text font-mono font-bold text-sm focus:border-blue-500 outline-none'
                      value={config.position_size}
                      onChange={(e) =>
                        handleConfigChange(
                          'position_size',
                          parseFloat(e.target.value) || 10000
                        )
                      }
                      step={1000}
                    />
                  </div>

                  <Toggle
                    label='Volatility-based Sizing'
                    checked={config.use_volatility_sizing}
                    onChange={(v) =>
                      handleConfigChange('use_volatility_sizing', v)
                    }
                  />

                  <div className='grid grid-cols-2 gap-4'>
                    <div className='flex flex-col gap-2'>
                      <label className='text-[9px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-widest'>
                        Max Conc.
                      </label>
                      <input
                        type='number'
                        className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-3 py-2 text-text font-mono font-bold text-sm focus:border-blue-500 outline-none'
                        value={config.max_concurrent_positions}
                        onChange={(e) =>
                          handleConfigChange(
                            'max_concurrent_positions',
                            parseInt(e.target.value) || 0
                          )
                        }
                      />
                    </div>
                    <div className='flex flex-col gap-2'>
                      <label className='text-[9px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-widest'>
                        Sector Cap
                      </label>
                      <input
                        type='number'
                        className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-3 py-2 text-text font-mono font-bold text-sm focus:border-blue-500 outline-none'
                        value={config.max_sector_positions}
                        onChange={(e) =>
                          handleConfigChange(
                            'max_sector_positions',
                            parseInt(e.target.value) || 0
                          )
                        }
                      />
                    </div>
                  </div>

                  <div className='flex flex-col gap-3 pt-4'>
                    <label className='text-[10px] text-slate-500 dark:text-slate-400 font-black uppercase tracking-[0.2em]'>
                      Simulation Range
                    </label>
                    <div className='flex flex-col gap-2'>
                      <input
                        type='date'
                        className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-4 py-2.5 text-text font-mono text-xs font-bold outline-none'
                        value={config.date_from}
                        onChange={(e) =>
                          handleConfigChange('date_from', e.target.value)
                        }
                      />
                      <input
                        type='date'
                        className='bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-xl px-4 py-2.5 text-text font-mono text-xs font-bold outline-none'
                        value={config.date_to}
                        onChange={(e) =>
                          handleConfigChange('date_to', e.target.value)
                        }
                      />
                    </div>
                  </div>
                </div>
              )}

              <button
                className='bg-blue-600 text-white border-none rounded-xl py-4 font-black uppercase tracking-[0.2em] text-xs cursor-pointer flex items-center justify-center gap-3 transition-all hover:bg-blue-700 hover:shadow-xl hover:shadow-blue-500/30 active:scale-[0.98] disabled:opacity-50 mt-4 shadow-lg shadow-blue-500/20'
                onClick={handleRunBacktest}
                disabled={isSubmitting || activeRun?.status === 'running'}
              >
                {isSubmitting ? (
                  <Loader2 className='animate-spin' size={18} />
                ) : (
                  <Play size={18} fill='currentColor' />
                )}
                Run Simulation
              </button>
            </div>
          </section>
        </aside>

        {/* Results Panel */}
        <main className='flex flex-col gap-8'>
          <div className='bg-slate-100 dark:bg-slate-900 border-2 border-border/50 rounded-2xl p-5 flex gap-4 text-slate-600 dark:text-slate-400 text-sm leading-relaxed shadow-sm'>
            <Info size={24} className='shrink-0 text-blue-500' />
            <div className='font-medium'>
              <strong className='text-text font-black uppercase tracking-widest text-[10px] block mb-1'>
                Market Simulation Intelligence
              </strong>
              Past performance does not guarantee future results. This tool
              provides statistical simulations based on daily closing prices and
              pre-defined technical criteria. Use results to validate strategy
              logic, not as direct financial advice.
            </div>
          </div>

          {!activeRunId && !loadingActiveRun && (
            <div className='py-24 text-center bg-bg-secondary border-2 border-border border-dashed rounded-3xl text-slate-400 shadow-sm'>
              <div className='bg-slate-100 dark:bg-slate-900 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6'>
                <BarChart3 size={40} className='opacity-40' />
              </div>
              <h3 className='text-xl font-black text-text uppercase tracking-tight'>
                No Simulation Active
              </h3>
              <p className='max-w-[300px] mx-auto mt-2 font-bold uppercase tracking-widest text-[10px]'>
                Configure parameters in the sidebar to start a new historical
                backtest.
              </p>
            </div>
          )}

          {activeRunError && <ErrorBanner message={activeRunError} />}

          <BacktestResults
            activeRun={activeRun}
            tradesData={tradesData}
            tradesPage={tradesPage}
            totalTradesCount={totalTradesCount}
            tradeColumns={tradeColumns}
            loadingTrades={loadingTrades}
            isDark={isDark}
            pageSize={pageSize}
            onPageChange={setTradesPage}
          />
        </main>
      </div>
    </div>
  );
};

export default Backtest;
