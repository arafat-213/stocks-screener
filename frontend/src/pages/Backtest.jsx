import { useState, useCallback, useMemo, useDeferredValue, memo } from 'react';
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
  Briefcase
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend
} from 'recharts';
import { Link } from 'react-router-dom';

import { 
  runBacktest, 
  getBacktestRun, 
  getBacktestRuns, 
  getBacktestTrades 
} from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { useTheme } from '../hooks/useTheme';
import { DataTable } from '../components/ui/DataTable';
import Slider from '../components/ui/Slider';
import Toggle from '../components/ui/Toggle';
import { ErrorBanner } from '../components/ui/ErrorBanner';

import './Backtest.css';

// rerender-memo: Memoize expensive result components to isolate them from config changes
const BacktestResults = memo(({ activeRun, tradesData, tradesPage, totalTradesCount, tradeColumns, loadingTrades, isDark, pageSize, onPageChange }) => {
  if (!activeRun) return null;

  const metrics = activeRun?.metrics;

  if (activeRun.status === 'running' || activeRun.status === 'pending') {
    return (
      <div className="progress-container">
        <div className="progress-header">
          <h3>Backtest in Progress...</h3>
          <span className="font-bold">{activeRun.progress.pct}%</span>
        </div>
        <div className="progress-bar-bg">
          <div className="progress-bar-fill" style={{ width: `${activeRun.progress.pct}%` }}></div>
        </div>
        <p className="progress-stats">
          Processing symbols: {activeRun.progress.symbols_done} / {activeRun.progress.symbols_total}
        </p>
      </div>
    );
  }

  if (activeRun.status === 'failed') {
    return (
      <div className="error-card p-6 border border-bearish bg-bearish/10 rounded-xl">
        <h3 className="text-bearish flex items-center gap-2 mb-2">
          <AlertTriangle size={20} /> Backtest Failed
        </h3>
        <p>{activeRun.error_message || 'An unknown error occurred during execution.'}</p>
      </div>
    );
  }

  if (activeRun.status === 'complete' && metrics) {
    return (
      <>
        {/* Metrics Grid */}
        <div className="metrics-grid">
          {[
            { label: "Total Trades", value: metrics.total_trades },
            { label: "Win Rate", value: `${metrics.win_rate?.toFixed(1)}%`, className: metrics.win_rate >= 50 ? 'positive' : 'negative' },
            { label: "Avg Return", value: `${metrics.avg_return_pct?.toFixed(2)}%`, className: metrics.avg_return_pct >= 0 ? 'positive' : 'negative' },
            { label: "Median Return", value: `${metrics.median_return_pct?.toFixed(2)}%`, className: metrics.median_return_pct >= 0 ? 'positive' : 'negative' },
            { label: "Best Trade", value: `${metrics.best_trade_pct?.toFixed(2)}%`, className: "positive" },
            { label: "Worst Trade", value: `${metrics.worst_trade_pct?.toFixed(2)}%`, className: "negative" },
            { label: "Sharpe Ratio", value: metrics.sharpe_ratio?.toFixed(2) },
            { label: "vs Nifty 50", value: `${(metrics.total_return_pct - metrics.benchmark_return_pct).toFixed(1)}%`, className: metrics.total_return_pct >= metrics.benchmark_return_pct ? 'positive' : 'negative' },
            { label: "Max Drawdown", value: `${metrics.max_drawdown_pct?.toFixed(1)}%`, className: "negative" }
          ].map((m, idx) => (
            <div key={m.label} className="metric-card animate-fade-in" style={{ "--delay": `${idx * 0.05}s` }}>
              <span className="metric-label">{m.label}</span>
              <span className={`metric-value ${m.className || ''}`}>{m.value}</span>
            </div>
          ))}
        </div>

        {/* Equity Chart */}
        <div className="chart-card animate-fade-in" style={{ "--delay": "0.5s" }}>
          <h3><TrendingUp size={18} /> Equity Curve</h3>
          <div className="equity-chart-wrapper">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={activeRun.equity_curve} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#2B2B43" : "#E5E7EB"} />
                <XAxis 
                  dataKey="date" 
                  stroke="var(--color-text-muted)" 
                  fontSize={11}
                  tickFormatter={(str) => new Date(str).toLocaleDateString([], { month: 'short', year: '2-digit' })}
                />
                <YAxis 
                  stroke="var(--color-text-muted)" 
                  fontSize={11}
                  tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--color-bg-elevated)', borderColor: 'var(--color-border)' }}
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
        <div className="trades-card animate-fade-in" style={{ "--delay": "0.6s" }}>
          <div className="trades-table-header">
            <h3><Layers size={18} /> Detailed Trades</h3>
            <div className="pagination-controls">
              <span className="text-muted text-sm">
                Showing {(tradesPage - 1) * pageSize + 1} - {Math.min(tradesPage * pageSize, totalTradesCount)} of {totalTradesCount}
              </span>
              <button 
                className="page-btn" 
                onClick={() => onPageChange(p => Math.max(1, p - 1))}
                disabled={tradesPage === 1}
              >
                <ChevronLeft size={16} />
              </button>
              <span className="font-mono">{tradesPage}</span>
              <button 
                className="page-btn" 
                onClick={() => onPageChange(p => p + 1)}
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
});

const Backtest = () => {
  const { isDark } = useTheme();

  // rerender-lazy-state-init: Initialize state once
  const [config, setConfig] = useState(() => ({
    score_threshold: 60,
    holding_days: 20,
    stop_loss_pct: 7.0,
    target_pct: 20.0,
    trailing_stop_pct: 0.0,
    use_atr_stops: false,
    atr_multiplier: 2.0,
    risk_reward_ratio: 2.0,
    use_regime_filter: true,
    require_volume_breakout: false,
    include_fundamentals: false,
    symbol_limit: 100,
    date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0],
    date_to: new Date().toISOString().split('T')[0]
  }));

  const [activeRunId, setActiveRunId] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [tradesPage, setTradesPage] = useState(1);
  const pageSize = 50;

  // Fetch Recent Runs
  const { data: recentRuns, refetch: refetchRecentRuns } = useFetch(getBacktestRuns);

  // Fetch Active Run (with polling)
  const fetchActiveRun = useCallback(() => {
    if (!activeRunId) return Promise.resolve(null);
    return getBacktestRun(activeRunId);
  }, [activeRunId]);

  const { 
    data: activeRun, 
    loading: loadingActiveRun, 
    error: activeRunError
  } = useFetch(fetchActiveRun, {
    deps: [activeRunId],
    refreshInterval: (data) => (data?.status === 'running' || data?.status === 'pending') ? 3000 : null
  });

  // Fetch Trades for Active Run
  const fetchTrades = useCallback(() => {
    if (!activeRunId || activeRun?.status !== 'complete') return Promise.resolve({ trades: [], total: 0 });
    return getBacktestTrades(activeRunId, { page: tradesPage, page_size: pageSize });
  }, [activeRunId, activeRun?.status, tradesPage]);

  const { data: tradesData, loading: loadingTrades } = useFetch(fetchTrades, {
    deps: [activeRunId, activeRun?.status, tradesPage]
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
      alert('Failed to start backtest: ' + (err.response?.data?.detail || err.message));
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
      score_threshold: 60,
      holding_days: 20,
      stop_loss_pct: 7.0,
      target_pct: 20.0,
      trailing_stop_pct: 0.0,
      use_atr_stops: false,
      atr_multiplier: 2.0,
      risk_reward_ratio: 2.0,
      use_regime_filter: true,
      require_volume_breakout: false,
      include_fundamentals: false,
      symbol_limit: 100,
      date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0],
      date_to: new Date().toISOString().split('T')[0]
    });
  }, []);

  // rerender-functional-setstate: Stable handler for all config changes
  const handleConfigChange = useCallback((key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  }, []);

  const totalTradesCount = tradesData?.total || 0;

  // rerender-memo: Column definitions are static or have stable dependencies
  const tradeColumns = useMemo(() => [
    { 
      key: 'symbol', 
      label: 'Symbol', 
      render: (val) => (
        <Link to={`/stocks/${val}`} className="symbol-link">
          {val.replace('.NS', '')} <ExternalLink size={12} />
        </Link>
      )
    },
    { 
      key: 'signal_date', 
      label: 'Signal Date',
      render: (val) => val ? new Date(val).toLocaleDateString() : '-'
    },
    { 
      key: 'entry_price', 
      label: 'Entry',
      render: (val) => `₹${val?.toFixed(2)}`
    },
    { 
      key: 'exit_price', 
      label: 'Exit',
      render: (val) => `₹${val?.toFixed(2)}`
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
      }
    },
    { 
      key: 'signal_score', 
      label: 'Score',
      render: (val) => val?.toFixed(1)
    },
    { 
      key: 'return_pct', 
      label: 'Return %',
      render: (val) => (
        <span className={val >= 0 ? 'positive' : 'negative'}>
          {val >= 0 ? '+' : ''}{val?.toFixed(2)}%
        </span>
      )
    },
    { 
      key: 'exit_reason', 
      label: 'Reason',
      render: (val) => (
        <span className={`reason-tag ${val}`}>
          {val?.replace('_', ' ')}
        </span>
      )
    }
  ], []);

  return (
    <div className="backtest-page">
      <header className="page-header" style={{ marginBottom: '24px' }}>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <History className="text-primary" /> Backtest Engine
        </h1>
        <p className="text-muted">Simulate strategies against historical NSE data.</p>
      </header>

      <div className="backtest-grid">
        {/* Sidebar Configuration */}
        <aside className="sidebar-panel">
          <section className="config-card">
            <div className="flex justify-between items-center mb-5">
              <h2 className="m-0 flex items-center gap-2"><Settings size={18} /> Configuration</h2>
              <button 
                className="text-muted hover:text-primary transition-colors p-1" 
                onClick={handleResetConfig}
                title="Reset to defaults"
              >
                <RotateCcw size={16} />
              </button>
            </div>
            
            <div className="config-form">
              <div className="form-group">
                <Slider 
                  label={<span className="flex items-center gap-2"><Target size={13} /> Score Threshold</span>}
                  value={config.score_threshold} 
                  onChange={(val) => handleConfigChange('score_threshold', val)} 
                  min={0} max={100}
                />
              </div>
              <div className="form-group">
                <Slider 
                  label={<span className="flex items-center gap-2"><Clock size={13} /> Holding Days</span>}
                  value={config.holding_days} 
                  onChange={(val) => handleConfigChange('holding_days', val)} 
                  min={1} max={252}
                />
              </div>

              <div className="risk-management-card">
                <h3 className="risk-management-title">
                  <ShieldCheck size={16} /> Risk Management
                </h3>
                
                <div className="risk-management-toggle">
                  <Toggle 
                    label="Use ATR-based Stops & Targets"
                    checked={config.use_atr_stops}
                    onChange={(val) => handleConfigChange('use_atr_stops', val)}
                  />
                </div>
                
                <div className="risk-management-controls">
                  {config.use_atr_stops ? (
                    <>
                      <Slider 
                        label="ATR Multiplier (Stop Loss)"
                        min={1.0}
                        max={5.0}
                        step={0.1}
                        value={config.atr_multiplier}
                        onChange={(val) => handleConfigChange('atr_multiplier', val)}
                      />
                      <Slider 
                        label="Risk/Reward Ratio (Targets)"
                        min={1.0}
                        max={10.0}
                        step={0.5}
                        value={config.risk_reward_ratio}
                        onChange={(val) => handleConfigChange('risk_reward_ratio', val)}
                      />
                    </>
                  ) : (
                    <>
                      <Slider 
                        label="Stop Loss %"
                        min={1}
                        max={25}
                        value={config.stop_loss_pct}
                        onChange={(val) => handleConfigChange('stop_loss_pct', val)}
                      />
                      <Slider 
                        label="Profit Target %"
                        min={0}
                        max={100}
                        value={config.target_pct}
                        onChange={(val) => handleConfigChange('target_pct', val)}
                      />
                    </>
                  )}
                </div>
              </div>

              <div className="form-group">
                <Slider 
                  label={<span className="flex items-center gap-2"><TrendingDown size={13} /> Trailing Stop %</span>}
                  value={config.trailing_stop_pct} 
                  onChange={(val) => handleConfigChange('trailing_stop_pct', val)} 
                  min={0} max={20}
                  step={0.5}
                />
              </div>

              <div className="strategy-rules-section">
                <h3 className="section-subtitle">Strategy Filters</h3>
                <div className="flex flex-col gap-3">
                  <Toggle 
                    label="Market Regime"
                    checked={config.use_regime_filter}
                    onChange={(val) => handleConfigChange('use_regime_filter', val)}
                    icon={ShieldCheck}
                  />
                  <Toggle 
                    label="Volume Breakout"
                    checked={config.require_volume_breakout}
                    onChange={(val) => handleConfigChange('require_volume_breakout', val)}
                    icon={Zap}
                  />
                  <Toggle 
                    label="Fundamentals"
                    checked={config.include_fundamentals}
                    onChange={(val) => handleConfigChange('include_fundamentals', val)}
                    icon={Briefcase}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="flex items-center gap-2 mb-1"><Briefcase size={13} /> Symbol Limit</label>
                <input 
                  type="number" 
                  className="input-styled w-full" 
                  value={config.symbol_limit} 
                  onChange={(e) => handleConfigChange('symbol_limit', parseInt(e.target.value) || 0)}
                />
              </div>

              <div className="form-group">
                <label className="flex items-center gap-2 mb-1"><Calendar size={13} /> Date Range</label>
                <div className="date-range-grid">
                  <div className="date-input-wrapper">
                    <span className="date-input-label">From</span>
                    <input 
                      type="date" 
                      className="input-styled" 
                      value={config.date_from} 
                      onChange={(e) => handleConfigChange('date_from', e.target.value)}
                    />
                  </div>
                  <div className="date-input-wrapper">
                    <span className="date-input-label">To</span>
                    <input 
                      type="date" 
                      className="input-styled" 
                      value={config.date_to} 
                      onChange={(e) => handleConfigChange('date_to', e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <button 
                className="run-button" 
                onClick={handleRunBacktest}
                disabled={isSubmitting || activeRun?.status === 'running'}
              >
                {isSubmitting ? <Loader2 className="animate-spin" size={18} /> : <Play size={18} />}
                Run Backtest
              </button>
            </div>
          </section>

          <section className="recent-runs-card">
            <h2><History size={18} /> Recent Runs</h2>
            <div className="recent-runs-list">
              {recentRuns?.map(run => (
                <div 
                  key={run.run_id} 
                  className={`run-item ${activeRunId === run.run_id ? 'active' : ''}`}
                  onClick={() => handleSelectRun(run.run_id)}
                >
                  <div className="run-item-header">
                    <span className="run-date">{new Date(run.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                    <span className={`run-status-badge ${run.status}`}>{run.status}</span>
                  </div>
                  <div className="run-config-summary">
                    T:{run.config.score_threshold} | H:{run.config.holding_days} | SL:{run.config.stop_loss_pct}%
                  </div>
                </div>
              ))}
              {recentRuns?.length === 0 && <p className="text-center text-muted py-4">No recent runs</p>}
            </div>
          </section>
        </aside>

        {/* Results Panel */}
        <main className="results-panel">
          <div className="disclaimer-banner">
            <AlertTriangle size={20} className="shrink-0" />
            <div>
              <strong>Educational Disclaimer:</strong> Backtest results are simulated and based on historical data. 
              Past performance is not indicative of future results. No strategy can guarantee profits or prevent losses in real market conditions.
            </div>
          </div>

          <div className={`disclaimer-banner info-variant ${config.include_fundamentals ? 'fundamental' : 'technical'}`}>
            <Info size={20} className="shrink-0" />
            <div>
              {config.include_fundamentals ? (
                <>
                  <strong>Fundamental Bias Warning:</strong> Current fundamental data applied to all historical dates. 
                  This overstates quality of older signals (look-ahead bias) because historical fundamentals are not available.
                </>
              ) : (
                <>
                  <strong>Technical Signals Only:</strong> Fundamental score excluded. Strategy uses technical criteria 
                  (EMA, RSI, MACD, Volume) for entry. Scores are on a 0–70 scale.
                </>
              )}
            </div>
          </div>

          {(!activeRunId && !loadingActiveRun) && (
            <div className="empty-state">
              <BarChart3 size={48} className="empty-state-icon mx-auto" />
              <h3>No Run Selected</h3>
              <p>Configure and run a new backtest or select a recent one from the sidebar.</p>
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
