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
        <div className="bg-bg-elevated border border-border rounded-xl p-6 text-center">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-lg font-bold text-text">Backtest in Progress...</h3>
            <span className="font-bold text-text">{activeRun.progress.pct}%</span>
          </div>
          <div className="h-2 bg-bg-secondary rounded-full overflow-hidden mb-2">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${activeRun.progress.pct}%` }}
            ></div>
          </div>
          <p className="text-[0.85rem] text-text-muted">
            Processing symbols: {activeRun.progress.symbols_done} /{' '}
            {activeRun.progress.symbols_total}
          </p>
        </div>
      );
    }

    if (activeRun.status === 'failed') {
      return (
        <div className="bg-bearish/10 border border-bearish rounded-xl p-6">
          <h3 className="text-bearish flex items-center gap-2 mb-2 font-semibold">
            <AlertTriangle size={20} /> Backtest Failed
          </h3>
          <p className="text-sm text-text">
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
            <div
              className="bg-warning/10 border border-warning/30 rounded-lg p-3 px-4 flex gap-3 text-amber-600 text-sm leading-relaxed mb-4"
            >
              <AlertTriangle
                size={20}
                className="shrink-0 text-warning"
              />
              <div>
                <strong>Low sample size — metrics unreliable.</strong> Only{' '}
                {metrics.total_trades} trades recorded. Statistical confidence
                requires at least 100 trades. To increase trade count: lower{' '}
                <em>Score Threshold</em> (try 40–45 for technical-only), disable{' '}
                <em>Weekly Confirmation</em> and <em>Volume Breakout</em>, or
                extend the date range.
              </div>
            </div>
          )}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-4">
            {[
              { label: 'Total Trades', value: metrics.total_trades },
              {
                label: 'Win Rate',
                value: `${metrics.win_rate?.toFixed(1)}%`,
                className: metrics.win_rate >= 50 ? 'text-bullish' : 'text-bearish',
              },
              {
                label: 'Expectancy',
                value: `${metrics.expectancy?.toFixed(2)}%`,
                className: metrics.expectancy >= 0 ? 'text-bullish' : 'text-bearish',
              },
              {
                label: 'Profit Factor',
                value: metrics.profit_factor?.toFixed(2),
                className: metrics.profit_factor >= 1 ? 'text-bullish' : 'text-bearish',
              },
              {
                label: 'Avg Win',
                value: `+${metrics.avg_win_pct?.toFixed(2)}%`,
                className: 'text-bullish',
              },
              {
                label: 'Avg Loss',
                value: `${metrics.avg_loss_pct?.toFixed(2)}%`,
                className: 'text-bearish',
              },
              {
                label: 'Avg Return',
                value: `${metrics.avg_return_pct?.toFixed(2)}%`,
                className:
                  metrics.avg_return_pct >= 0 ? 'text-bullish' : 'text-bearish',
              },
              {
                label: 'Sharpe Ratio',
                value: metrics.sharpe_ratio?.toFixed(2),
              },
              {
                label: 'vs Nifty 50',
                value: `${(metrics.total_return_pct - metrics.benchmark_return_pct).toFixed(1)}%`,
                className:
                  metrics.total_return_pct >= metrics.benchmark_return_pct
                    ? 'text-bullish'
                    : 'text-bearish',
              },
              {
                label: 'Max Drawdown',
                value: `${metrics.max_drawdown_pct?.toFixed(1)}%`,
                className: 'text-bearish',
              },
            ].map((m, idx) => (
              <div
                key={m.label}
                className="bg-bg-elevated border border-border rounded-xl p-4 flex flex-col gap-1 animate-fade-in"
                style={{ '--delay': `${idx * 0.05}s` }}
              >
                <span className="text-[0.75rem] text-text-muted font-medium uppercase tracking-wider">{m.label}</span>
                <span className={`text-xl font-bold font-mono ${m.className || 'text-text'}`}>
                  {m.value}
                </span>
              </div>
            ))}
          </div>

          {metrics.exit_breakdown && (
            <div
              className="bg-bg-elevated border border-border rounded-xl p-5 animate-fade-in"
              style={{ '--delay': '0.55s' }}
            >
              <h3 className="text-base font-bold flex items-center gap-2 mb-5 text-text">
                <Target size={18} /> Exit Analysis
              </h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4">
                {[
                  { key: 'target', label: 'Hit Target', color: 'bg-bullish' },
                  {
                    key: 'target_partial',
                    label: 'Partial Target',
                    color: 'bg-bullish',
                  },
                  { key: 'stop_loss', label: 'Stop Loss', color: 'bg-bearish' },
                  {
                    key: 'trailing_stop',
                    label: 'Trailing Stop',
                    color: 'bg-bearish',
                  },
                  {
                    key: 'atr_trailing_stop',
                    label: 'ATR Trail Stop',
                    color: 'bg-bullish',
                  },
                  {
                    key: 'signal_invalidated',
                    label: 'Signal Invalid',
                    color: 'bg-bearish',
                  },
                  {
                    key: 'holding_period',
                    label: 'Held to End',
                    color: 'bg-text-muted',
                  },
                ].map(({ key, label, color }) => {
                  const count = metrics.exit_breakdown[key] || 0;
                  const pct =
                    metrics.total_trades > 0
                      ? ((count / metrics.total_trades) * 100).toFixed(0)
                      : 0;
                  return (
                    <div key={key} className="bg-bg-secondary p-3 rounded-lg border border-border flex flex-col gap-2.5 transition-transform hover:-translate-y-0.5 hover:border-primary">
                      <div className="flex justify-between items-center">
                        <span className="text-[0.85rem] text-text-muted">{label}</span>
                        <span className="flex items-center gap-1">
                          <span className="text-[0.9rem] font-semibold text-text">{count}</span>
                          <span className="text-[0.75rem] text-text-muted">({pct}%)</span>
                        </span>
                      </div>
                      <div className="h-1.5 bg-bg-secondary rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${color}`}
                          style={{ width: `${pct}%` }}
                        ></div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Equity Chart */}
          <div
            className="bg-bg-elevated border border-border rounded-xl p-5 animate-fade-in"
            style={{ '--delay': '0.5s' }}
          >
            <h3 className="text-base font-bold flex items-center gap-2 mb-5 text-text">
              <TrendingUp size={18} /> Equity Curve
            </h3>
            <div className="w-full h-[400px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={activeRun.equity_curve}
                  margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke={isDark ? '#2B2B43' : '#E5E7EB'}
                  />
                  <XAxis
                    dataKey="date"
                    stroke="var(--color-text-muted)"
                    fontSize={11}
                    tickFormatter={(str) =>
                      new Date(str).toLocaleDateString([], {
                        month: 'short',
                        year: '2-digit',
                      })
                    }
                  />
                  <YAxis
                    stroke="var(--color-text-muted)"
                    fontSize={11}
                    tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-bg-elevated)',
                      borderColor: 'var(--color-border)',
                      borderRadius: '8px',
                    }}
                    itemStyle={{ fontSize: '12px' }}
                    labelStyle={{ marginBottom: '4px', fontWeight: 'bold' }}
                  />
                  <Legend verticalAlign="top" height={36} iconType="circle" />
                  <Line
                    name="Strategy Equity"
                    type="monotone"
                    dataKey="equity"
                    stroke="var(--color-primary)"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                  <Line
                    name="Benchmark (Nifty 50)"
                    type="monotone"
                    dataKey="benchmark_equity"
                    stroke="var(--color-text-muted)"
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Trades Table */}
          <div
            className="bg-bg-elevated border border-border rounded-xl p-5 animate-fade-in"
            style={{ '--delay': '0.6s' }}
          >
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-base font-bold flex items-center gap-2 text-text">
                <Layers size={18} /> Detailed Trades
              </h3>
              <div className="flex items-center gap-3 text-[0.9rem]">
                <span className="text-text-muted text-sm">
                  Showing {(tradesPage - 1) * pageSize + 1} -{' '}
                  {Math.min(tradesPage * pageSize, totalTradesCount)} of{' '}
                  {totalTradesCount}
                </span>
                <button
                  className="bg-bg-secondary border border-border rounded p-1 cursor-pointer flex items-center disabled:opacity-50 disabled:cursor-not-allowed text-text"
                  onClick={() => onPageChange((p) => Math.max(1, p - 1))}
                  disabled={tradesPage === 1}
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="font-mono text-text">{tradesPage}</span>
                <button
                  className="bg-bg-secondary border border-border rounded p-1 cursor-pointer flex items-center disabled:opacity-50 disabled:cursor-not-allowed text-text"
                  onClick={() => onPageChange((p) => p + 1)}
                  disabled={tradesPage * pageSize >= totalTradesCount}
                >
                  <ChevronRight size={16} />
                </button>
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
  },
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
          (err.response?.data?.detail || err.message),
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
          <Link to={`/stocks/${val}`} className="text-primary hover:underline flex items-center gap-1 font-semibold">
            {val.replace('.NS', '')} <ExternalLink size={12} />
          </Link>
        ),
      },
      {
        key: 'signal_date',
        label: 'Signal Date',
        render: (val) => (val ? new Date(val).toLocaleDateString() : '-'),
      },
      {
        key: 'entry_price',
        label: 'Entry',
        render: (val) => `₹${val?.toFixed(2)}`,
      },
      {
        key: 'exit_price',
        label: 'Exit',
        render: (val) => `₹${val?.toFixed(2)}`,
      },
      {
        key: 'days_held',
        label: 'Days',
        render: (_, row) => {
          if (!row.entry_date || !row.exit_date) return '-';
          const start = new Date(row.entry_date);
          const end = new Date(row.exit_date);
          const diff = Math.ceil(Math.abs(end - start) / (1000 * 60 * 60 * 24));
          return diff;
        },
      },
      {
        key: 'signal_score',
        label: 'Score',
        render: (val) => val?.toFixed(1),
      },
      {
        key: 'return_pct',
        label: 'Return %',
        render: (val) => (
          <span className={val >= 0 ? 'text-bullish' : 'text-bearish font-medium'}>
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
            stop_loss: 'bg-bearish/10 text-bearish',
            trailing_stop: 'bg-warning/10 text-amber-600',
            target: 'bg-bullish/10 text-bullish',
            holding_period: 'bg-primary/10 text-primary',
          };
          const reasonClass = reasonClasses[val] || 'bg-bg-secondary text-text-muted';
          return (
            <span className={`text-[0.75rem] px-1.5 py-0.5 rounded-[4px] font-medium ${reasonClass}`}>
              {val?.replace('_', ' ')}
            </span>
          );
        },
      },
    ],
    [],
  );

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2 text-text">
          <History className="text-primary" /> Backtest Engine
        </h1>
        <p className="text-text-muted">
          Simulate strategies against historical NSE data.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 items-start">
        {/* Sidebar Configuration */}
        <aside className="flex flex-col gap-6">
          <section className="bg-bg-elevated border border-border rounded-xl p-5">
            <h2 className="text-lg font-bold flex items-center gap-2 mb-5 text-text">
              <History size={18} /> Recent Runs
            </h2>
            <div className="flex flex-col gap-2 max-h-[400px] overflow-y-auto pr-1">
              {recentRuns?.map((run) => (
                <div
                  key={run.run_id}
                  className={`p-2.5 px-3 rounded-lg border cursor-pointer transition-all duration-200 hover:bg-bg-secondary ${activeRunId === run.run_id ? 'bg-bg-secondary border-primary' : 'border-transparent'}`}
                  onClick={() => handleSelectRun(run.run_id)}
                >
                  <div className="flex justify-between mb-1">
                    <span className="text-[0.8rem] font-semibold text-text">
                      {new Date(run.created_at).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                    <span className={`text-[0.7rem] px-1.5 py-0.5 rounded-[4px] uppercase font-bold 
                      ${run.status === 'complete' ? 'bg-bullish/10 text-bullish' : 
                        run.status === 'running' ? 'bg-primary/10 text-primary' :
                        run.status === 'failed' ? 'bg-bearish/10 text-bearish' :
                        'bg-text-muted/10 text-text-muted'}`}>
                      {run.status}
                    </span>
                  </div>
                  <div className="text-[0.75rem] text-text-muted">
                    T:{run.config.score_threshold} | H:{run.config.holding_days}{' '}
                    | SL:{run.config.stop_loss_pct}% | W:
                    {run.config.require_weekly_confirmation !== false
                      ? '✓'
                      : '✗'}
                  </div>
                </div>
              ))}
              {recentRuns?.length === 0 && (
                <p className="text-center text-text-muted py-4">No recent runs</p>
              )}
            </div>
          </section>

          <section className="bg-bg-elevated border border-border rounded-xl p-5">
            <div className="flex justify-between items-center mb-5">
              <h2 className="text-lg font-bold flex items-center gap-2 text-text">
                <Settings size={18} /> Configuration
              </h2>
              <button
                className="text-text-muted p-1 rounded-sm transition-all duration-200 hover:text-primary hover:bg-bg-secondary"
                onClick={handleResetConfig}
                title="Reset to defaults"
              >
                <RotateCcw size={16} />
              </button>
            </div>

            <div className="flex gap-0.5 bg-bg-secondary p-1 rounded-lg mb-4 border border-border">
              {[
                { id: 'strategy', label: 'Strategy', icon: Zap },
                { id: 'risk', label: 'Risk', icon: ShieldCheck },
                { id: 'account', label: 'Account', icon: Briefcase },
              ].map((tab) => (
                <button
                  key={tab.id}
                  className={`flex-1 flex items-center justify-center gap-1.5 p-1.5 py-1 text-[0.75rem] font-semibold rounded-md transition-all duration-200 cursor-pointer border-none outline-none ${activeTab === tab.id ? 'bg-bg-elevated text-primary shadow-sm' : 'text-text-muted hover:text-text hover:bg-white/5'}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <tab.icon size={14} />
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            <div className="flex flex-col gap-4">
              {activeTab === 'strategy' && (
                <div className="flex flex-col gap-3 animate-fade-in">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[0.85rem] text-text-muted font-medium flex items-center gap-2 mb-1">
                      <Layers size={13} /> Starting Universe
                    </label>
                    <select
                      className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary"
                      value={config.screen_slug}
                      onChange={(e) =>
                        handleConfigChange('screen_slug', e.target.value)
                      }
                    >
                      <option value="all">All Symbols (Default)</option>
                      {screens?.map((screen) => (
                        <option key={screen.slug} value={screen.slug}>
                          {screen.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Slider
                      label={
                        <span className="flex items-center gap-2">
                          <Target size={13} /> Score Threshold
                        </span>
                      }
                      value={config.score_threshold}
                      onChange={(val) =>
                        handleConfigChange('score_threshold', val)
                      }
                      min={0}
                      max={100}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Slider
                      label={
                        <span className="flex items-center gap-2">
                          <Clock size={13} /> Max Holding Days
                        </span>
                      }
                      value={config.holding_days}
                      onChange={(val) =>
                        handleConfigChange('holding_days', val)
                      }
                      min={1}
                      max={252}
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Slider
                      label={
                        <span className="flex items-center gap-2">
                          <Briefcase size={13} /> Symbol Limit
                        </span>
                      }
                      value={config.symbol_limit}
                      onChange={(val) =>
                        handleConfigChange('symbol_limit', val)
                      }
                      min={10}
                      max={500}
                    />
                  </div>

                  <div
                    className="flex flex-col gap-3 pt-3 border-t border-border mt-2"
                  >
                    <h3 className="text-[0.7rem] text-text-muted uppercase tracking-[0.08em] font-bold mb-1">Strategy Filters</h3>
                    <div className="flex flex-col gap-3">
                      <Toggle
                        label="Include Fundamentals"
                        checked={config.include_fundamentals}
                        onChange={(val) =>
                          handleConfigChange('include_fundamentals', val)
                        }
                        icon={Briefcase}
                      />
                      <Toggle
                        label="Market Regime"
                        checked={config.use_regime_filter}
                        onChange={(val) =>
                          handleConfigChange('use_regime_filter', val)
                        }
                        icon={ShieldCheck}
                      />
                      <Toggle
                        label="Volume Breakout"
                        checked={config.require_volume_breakout}
                        onChange={(val) =>
                          handleConfigChange('require_volume_breakout', val)
                        }
                        icon={Zap}
                      />
                      <Toggle
                        label="Weekly Conf"
                        checked={config.require_weekly_confirmation}
                        onChange={(val) =>
                          handleConfigChange('require_weekly_confirmation', val)
                        }
                        icon={TrendingUp}
                      />
                      <Toggle
                        label="Monthly Conf"
                        checked={config.require_monthly_confirmation}
                        onChange={(val) =>
                          handleConfigChange(
                            'require_monthly_confirmation',
                            val,
                          )
                        }
                        icon={BarChart3}
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'risk' && (
                <div className="flex flex-col gap-3 animate-fade-in">
                  <div className="mb-2">
                    <Toggle
                      label="Use ATR-based Stops"
                      checked={config.use_atr_stops}
                      onChange={(val) =>
                        handleConfigChange('use_atr_stops', val)
                      }
                    />
                  </div>

                  {config.use_atr_stops ? (
                    <>
                      <Slider
                        label="ATR SL Multiplier"
                        min={1.0}
                        max={5.0}
                        step={0.1}
                        value={config.atr_multiplier}
                        onChange={(val) =>
                          handleConfigChange('atr_multiplier', val)
                        }
                      />
                      <Slider
                        label="Risk/Reward Ratio"
                        min={1.0}
                        max={10.0}
                        step={0.5}
                        value={config.risk_reward_ratio}
                        onChange={(val) =>
                          handleConfigChange('risk_reward_ratio', val)
                        }
                      />
                    </>
                  ) : (
                    <>
                      <Slider
                        label="Stop Loss %"
                        min={1}
                        max={25}
                        value={config.stop_loss_pct}
                        onChange={(val) =>
                          handleConfigChange('stop_loss_pct', val)
                        }
                      />
                      <Slider
                        label="Profit Target %"
                        min={0}
                        max={100}
                        value={config.target_pct}
                        onChange={(val) =>
                          handleConfigChange('target_pct', val)
                        }
                      />
                    </>
                  )}

                  <div className="flex flex-col gap-1.5 mt-2">
                    <Slider
                      label="Manual Trailing Stop %"
                      min={0}
                      max={20}
                      step={0.5}
                      value={config.trailing_stop_pct}
                      onChange={(val) =>
                        handleConfigChange('trailing_stop_pct', val)
                      }
                    />
                  </div>

                  <div
                    className="flex flex-col gap-3 pt-3 border-t border-border mt-4"
                  >
                    <h3 className="text-[0.7rem] text-text-muted uppercase tracking-[0.08em] font-bold mb-1">Advanced Exit Rules</h3>
                    <div className="flex flex-col gap-3">
                      <Toggle
                        label="ATR Trailing Stop"
                        checked={config.use_atr_trailing_stop}
                        onChange={(val) =>
                          handleConfigChange('use_atr_trailing_stop', val)
                        }
                        icon={TrendingDown}
                      />
                      <Toggle
                        label="Partial Exits (T1/T2)"
                        checked={config.use_partial_exits}
                        onChange={(val) =>
                          handleConfigChange('use_partial_exits', val)
                        }
                        icon={Target}
                      />
                      <Toggle
                        label="Signal Invalidation"
                        checked={config.use_signal_invalidation_exit}
                        onChange={(val) =>
                          handleConfigChange(
                            'use_signal_invalidation_exit',
                            val,
                          )
                        }
                        icon={ShieldCheck}
                      />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'account' && (
                <div className="flex flex-col gap-3 animate-fade-in">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[0.85rem] text-text-muted font-medium flex items-center gap-2 mb-1 text-text">Starting Capital (₹)</label>
                    <input
                      type="number"
                      className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary"
                      value={config.starting_capital}
                      onChange={(e) =>
                        handleConfigChange(
                          'starting_capital',
                          parseFloat(e.target.value) || 1000000,
                        )
                      }
                      min={100000}
                      step={100000}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[0.85rem] text-text-muted font-medium flex items-center gap-2 mb-1 text-text">Pos Size per Trade (₹)</label>
                    <input
                      type="number"
                      className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary"
                      value={config.position_size}
                      onChange={(e) =>
                        handleConfigChange(
                          'position_size',
                          parseFloat(e.target.value) || 10000,
                        )
                      }
                      min={1000}
                      step={1000}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Toggle
                      label="Volatility Sizing"
                      checked={config.use_volatility_sizing}
                      onChange={(val) =>
                        handleConfigChange('use_volatility_sizing', val)
                      }
                    />
                  </div>
                  <div className="flex gap-3 mb-3">
                    <div className="flex flex-col gap-1.5 flex-1">
                      <label className="text-[0.85rem] text-text-muted font-medium mb-1 text-xs">
                        Max Concurrent
                      </label>
                      <input
                        type="number"
                        className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary"
                        value={config.max_concurrent_positions}
                        onChange={(e) =>
                          handleConfigChange(
                            'max_concurrent_positions',
                            parseInt(e.target.value) || 0,
                          )
                        }
                        min={1}
                        max={50}
                      />
                    </div>
                    <div className="flex flex-col gap-1.5 flex-1">
                      <label className="text-[0.85rem] text-text-muted font-medium mb-1 text-xs">Sector Cap</label>
                      <input
                        type="number"
                        className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary"
                        value={config.max_sector_positions}
                        onChange={(e) =>
                          handleConfigChange(
                            'max_sector_positions',
                            parseInt(e.target.value) || 0,
                          )
                        }
                        min={1}
                        max={10}
                      />
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-[0.85rem] text-text-muted font-medium flex items-center gap-2 mb-1">
                      <Calendar size={13} /> Date Range
                    </label>
                    <div className="flex gap-2 w-full">
                      <input
                        type="date"
                        className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary px-2"
                        value={config.date_from}
                        onChange={(e) =>
                          handleConfigChange('date_from', e.target.value)
                        }
                      />
                      <input
                        type="date"
                        className="bg-bg-secondary border border-border rounded-md px-3 py-2 text-text text-[0.9rem] outline-none transition-colors duration-200 w-full focus:border-primary px-2"
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
                className="bg-primary text-white border-none rounded-lg p-3 font-semibold cursor-pointer flex items-center justify-center gap-2 transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
                onClick={handleRunBacktest}
                disabled={isSubmitting || activeRun?.status === 'running'}
              >
                {isSubmitting ? (
                  <Loader2 className="animate-spin" size={18} />
                ) : (
                  <Play size={18} />
                )}
                Run Backtest
              </button>
            </div>
          </section>
        </aside>

        {/* Results Panel */}
        <main className="flex flex-col gap-6">
          <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 px-4 flex gap-3 text-amber-600 text-[0.85rem] leading-relaxed">
            <AlertTriangle size={20} className="shrink-0 text-warning" />
            <div>
              <strong>Educational Disclaimer:</strong> Backtest results are
              simulated and based on historical data. Past performance is not
              indicative of future results. No strategy can guarantee profits or
              prevent losses in real market conditions.
            </div>
          </div>

          <div
            className={`rounded-lg p-3 px-4 flex gap-3 text-[0.85rem] leading-relaxed border ${config.include_fundamentals ? 'bg-violet-500/10 border-violet-500/30 text-violet-600' : 'bg-cyan-500/10 border-cyan-500/30 text-cyan-600'}`}
          >
            <Info size={20} className="shrink-0" />
            <div>
              {config.include_fundamentals ? (
                <>
                  <strong>Fundamental Bias Warning:</strong> Current fundamental
                  data applied to all historical dates. This overstates quality
                  of older signals (look-ahead bias) because historical
                  fundamentals are not available.
                </>
              ) : (
                <>
                  <strong>Technical Signals Only:</strong> Fundamental score
                  excluded. Strategy uses technical criteria (EMA, RSI, MACD,
                  Volume) for entry. Scores are on a 0–70 scale.
                </>
              )}
            </div>
          </div>

          {!activeRunId && !loadingActiveRun && (
            <div className="p-[60px_20px] text-center bg-bg-elevated border border-border rounded-xl text-text-muted">
              <BarChart3 size={48} className="mb-4 opacity-50 mx-auto" />
              <h3 className="text-lg font-bold text-text">No Run Selected</h3>
              <p>
                Configure and run a new backtest or select a recent one from the
                sidebar.
              </p>
            </div>
          )}

          {activeRunError && <ErrorBanner message={activeRunError} />}

          {/* rerender-use-deferred-value: The results section will only re-render when the UI is idle, keeping inputs smooth */}
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
