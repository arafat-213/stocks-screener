import { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  Play, 
  History, 
  Settings, 
  BarChart3, 
  TrendingUp, 
  AlertTriangle, 
  ChevronLeft, 
  ChevronRight,
  Activity,
  Calendar,
  Layers,
  Info,
  Loader2,
  ExternalLink
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
import { ErrorBanner } from '../components/ui/ErrorBanner';

import './Backtest.css';

const Backtest = () => {
  const { isDark } = useTheme();

  // Configuration State
  const [config, setConfig] = useState({
    score_threshold: 60,
    holding_days: 20,
    stop_loss_pct: 7.0,
    target_pct: 20.0,
    include_fundamentals: false,
    symbol_limit: 100,
    date_from: new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0],
    date_to: new Date().toISOString().split('T')[0]
  });

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
    error: activeRunError, 
    setData: setActiveRun 
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

  // Handle Run Start
  const handleRunBacktest = async () => {
    try {
      setIsSubmitting(true);
      const res = await runBacktest(config);
      setActiveRunId(res.data.run_id);
      refetchRecentRuns();
    } catch (err) {
      console.error('Failed to start backtest:', err);
      alert('Failed to start backtest: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSelectRun = (runId) => {
    setActiveRunId(runId);
    setTradesPage(1);
  };

  const trades = tradesData?.trades || [];
  const totalTradesCount = tradesData?.total || 0;

  const tradeColumns = [
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
  ];

  const metrics = activeRun?.metrics;

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
            <h2><Settings size={18} /> Configuration</h2>
            <div className="config-form">
              <div className="form-group">
                <Slider 
                  label="Score Threshold" 
                  value={config.score_threshold} 
                  onChange={(val) => setConfig({...config, score_threshold: val})} 
                  min={0} max={100}
                />
              </div>
              <div className="form-group">
                <Slider 
                  label="Holding Days" 
                  value={config.holding_days} 
                  onChange={(val) => setConfig({...config, holding_days: val})} 
                  min={1} max={252}
                />
              </div>
              <div className="form-group">
                <Slider 
                  label="Stop Loss %" 
                  value={config.stop_loss_pct} 
                  onChange={(val) => setConfig({...config, stop_loss_pct: val})} 
                  min={0} max={50}
                  step={0.5}
                />
              </div>
              <div className="form-group">
                <Slider 
                  label="Target %" 
                  value={config.target_pct} 
                  onChange={(val) => setConfig({...config, target_pct: val})} 
                  min={0} max={200}
                  step={1}
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Symbol Limit</label>
                  <input 
                    type="number" 
                    className="input-styled" 
                    value={config.symbol_limit} 
                    onChange={(e) => setConfig({...config, symbol_limit: parseInt(e.target.value) || 0})}
                  />
                </div>
                <div className="form-group checkbox-group" onClick={() => setConfig({...config, include_fundamentals: !config.include_fundamentals})}>
                  <input 
                    type="checkbox" 
                    checked={config.include_fundamentals} 
                    onChange={() => {}} // Handled by group click
                  />
                  <label>Fundamentals</label>
                </div>
              </div>
              <div className="form-group">
                <label>Date Range</label>
                <div className="form-row">
                  <input 
                    type="date" 
                    className="input-styled" 
                    value={config.date_from} 
                    onChange={(e) => setConfig({...config, date_from: e.target.value})}
                  />
                  <input 
                    type="date" 
                    className="input-styled" 
                    value={config.date_to} 
                    onChange={(e) => setConfig({...config, date_to: e.target.value})}
                  />
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

          {!activeRunId && !loadingActiveRun && (
            <div className="empty-state">
              <BarChart3 size={48} className="empty-state-icon mx-auto" />
              <h3>No Run Selected</h3>
              <p>Configure and run a new backtest or select a recent one from the sidebar.</p>
            </div>
          )}

          {activeRunError && <ErrorBanner message={activeRunError} />}

          {(activeRun?.status === 'running' || activeRun?.status === 'pending') && (
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
          )}

          {activeRun?.status === 'failed' && (
            <div className="error-card p-6 border border-bearish bg-bearish/10 rounded-xl">
              <h3 className="text-bearish flex items-center gap-2 mb-2">
                <AlertTriangle size={20} /> Backtest Failed
              </h3>
              <p>{activeRun.error_message || 'An unknown error occurred during execution.'}</p>
            </div>
          )}

          {activeRun?.status === 'complete' && (
            <>
              {/* Metrics Grid */}
              <div className="metrics-grid">
                <div className="metric-card">
                  <span className="metric-label">Total Trades</span>
                  <span className="metric-value">{metrics.total_trades}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Win Rate</span>
                  <span className={`metric-value ${metrics.win_rate >= 50 ? 'positive' : 'negative'}`}>
                    {metrics.win_rate?.toFixed(1)}%
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Avg Return</span>
                  <span className={`metric-value ${metrics.avg_return_pct >= 0 ? 'positive' : 'negative'}`}>
                    {metrics.avg_return_pct?.toFixed(2)}%
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Median Return</span>
                  <span className={`metric-value ${metrics.median_return_pct >= 0 ? 'positive' : 'negative'}`}>
                    {metrics.median_return_pct?.toFixed(2)}%
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Best Trade</span>
                  <span className="metric-value positive">{metrics.best_trade_pct?.toFixed(2)}%</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Worst Trade</span>
                  <span className="metric-value negative">{metrics.worst_trade_pct?.toFixed(2)}%</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Sharpe Ratio</span>
                  <span className="metric-value">{metrics.sharpe_ratio?.toFixed(2)}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">vs Nifty 50</span>
                  <span className={`metric-value ${metrics.total_return_pct >= metrics.benchmark_return_pct ? 'positive' : 'negative'}`}>
                    {(metrics.total_return_pct - metrics.benchmark_return_pct).toFixed(1)}%
                  </span>
                </div>
                <div className="metric-card">
                  <span className="metric-label">Max Drawdown</span>
                  <span className="metric-value negative">
                    {metrics.max_drawdown_pct?.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Equity Chart */}
              <div className="chart-card">
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
              <div className="trades-card">
                <div className="trades-table-header">
                  <h3><Layers size={18} /> Detailed Trades</h3>
                  <div className="pagination-controls">
                    <span className="text-muted text-sm">
                      Showing {(tradesPage - 1) * pageSize + 1} - {Math.min(tradesPage * pageSize, totalTradesCount)} of {totalTradesCount}
                    </span>
                    <button 
                      className="page-btn" 
                      onClick={() => setTradesPage(p => Math.max(1, p - 1))}
                      disabled={tradesPage === 1}
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <span className="font-mono">{tradesPage}</span>
                    <button 
                      className="page-btn" 
                      onClick={() => setTradesPage(p => p + 1)}
                      disabled={tradesPage * pageSize >= totalTradesCount}
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
                <DataTable 
                  columns={tradeColumns} 
                  data={trades} 
                  loading={loadingTrades}
                  skeletonRows={10}
                />
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
};

export default Backtest;
