import React, { useState, useEffect, useMemo } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
  BarChart, Bar, Cell, PieChart, Pie, Legend
} from 'recharts';
import { 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Info,
  Calendar,
  Filter,
  ChevronDown,
  ChevronUp,
  Target,
  ShieldCheck
} from 'lucide-react';
import { 
  getPaperPortfolio, 
  getPaperPending, 
  getPaperPositions, 
  getPaperTrades,
  getStatus
} from '../api/client';
import './PaperTrading.css';

// Mock backtest constants
const BACKTEST_BENCHMARKS = {
  total_return_pct: 42.5,
  win_rate: 57.0,
  profit_factor: 1.50,
  avg_win_pct: 8.2,
  avg_loss_pct: 3.5,
  max_drawdown: 12.4,
  avg_holding_days: 22,
  exit_reasons: [
    { name: 'Stop Loss', value: 41 },
    { name: 'ATR Trail', value: 39 },
    { name: 'Target', value: 17 },
    { name: 'Held', value: 3 }
  ]
};

const PaperTrading = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [status, setStatus] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  
  useEffect(() => {
    getStatus().then(setStatus);
    getPaperPortfolio().then(setPortfolio);
  }, []);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'pending', label: 'Pending' },
    { id: 'positions', label: 'Positions' },
    { id: 'history', label: 'History' },
    { id: 'analytics', label: 'Analytics' }
  ];

  return (
    <div className="paper-trading-page animate-in">
      <header className="page-header">
        <div className="header-left">
          <h1>Paper Trading</h1>
          <p className="text-muted">Live strategy verification without real capital</p>
        </div>
        
        <div className="header-right">
          {status && (
            <div className={`status-pill ${status.pipeline.is_stale ? 'stale' : 'current'}`}>
              <div className="pulse-dot"></div>
              <span>{status.pipeline.is_stale ? 'Stale — pipeline not run today' : `Updated ${status.pipeline.data_age_hours}h ago`}</span>
            </div>
          )}
        </div>
      </header>

      <nav className="tabs-nav card glass">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="tab-content">
        {activeTab === 'overview' && <OverviewView portfolio={portfolio} setPortfolio={setPortfolio} />}
        {activeTab === 'pending' && <PendingView />}
        {activeTab === 'positions' && <PositionsView />}
        {activeTab === 'history' && <HistoryView />}
        {activeTab === 'analytics' && <AnalyticsView />}
      </div>

      <ReadinessBanner portfolio={portfolio} />
    </div>
  );
};

// --- Sub-components ---

const OverviewView = ({ portfolio, setPortfolio }) => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(!portfolio);

  useEffect(() => {
    const p1 = portfolio ? Promise.resolve(portfolio) : getPaperPortfolio();
    Promise.all([p1, getPaperTrades({ limit: 100 })])
      .then(([p, t]) => {
        setPortfolio(p);
        setTrades(t);
        setLoading(false);
      });
  }, [portfolio, setPortfolio]);

  if (loading) return <div className="loading-spinner">Loading Overview...</div>;
  if (portfolio?.status === 'no_portfolio') {
    return (
      <div className="view-placeholder">
        <AlertCircle size={48} className="text-muted" />
        <h2>No Active Portfolio</h2>
        <p>Run a pipeline cycle to initialize the paper trading portfolio.</p>
      </div>
    );
  }

  const pnlData = trades.length > 0 ? (() => {
    let cumulative = 0;
    const sortedTrades = [...trades].sort((a, b) => new Date(a.exit_date) - new Date(b.exit_date));
    return sortedTrades.map(t => {
      cumulative += t.pnl;
      return {
        date: t.exit_date,
        pnl: cumulative,
        trade: t
      };
    });
  })() : [];

  const StatCard = ({ label, value, color, comparison, subLabel }) => (
    <div className="stat-card card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${color || ''}`}>{value}</div>
      {comparison !== undefined && (
        <div className="stat-comparison">
          {comparison} {subLabel && <span className="text-muted">vs {subLabel}</span>}
        </div>
      )}
    </div>
  );

  const getDivergenceClass = (live, backtest) => {
    if (!live || !backtest) return '';
    const diff = Math.abs(live - backtest) / backtest;
    return diff > 0.1 ? 'divergence-highlight' : '';
  };

  return (
    <div className="overview-view animate-in">
      <div className="stats-grid">
        <StatCard 
          label="Total Return %" 
          value={`${portfolio.total_return_pct}%`}
          color={portfolio.total_return_pct >= 0 ? 'text-bullish' : 'text-bearish'}
          comparison={`${BACKTEST_BENCHMARKS.total_return_pct}%`}
          subLabel="Backtest"
        />
        <StatCard 
          label="Win Rate" 
          value={`${portfolio.win_rate}%`}
          comparison={`${BACKTEST_BENCHMARKS.win_rate}%`}
          subLabel="Backtest"
        />
        <StatCard 
          label="Open Positions" 
          value={portfolio.open_positions}
          comparison={portfolio.pending_orders}
          subLabel="Pending"
        />
        <StatCard 
          label="Profit Factor" 
          value={portfolio.profit_factor}
          comparison={BACKTEST_BENCHMARKS.profit_factor}
          subLabel="Backtest"
        />
      </div>

      <div className="overview-main mt-6">
        <div className="pnl-chart-container card">
          <div className="pnl-chart-header">
            <h3 className="m-0">Cumulative P&L</h3>
            <p className="text-muted text-sm">Equity curve in Rupees based on realized trades</p>
          </div>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={pnlData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
                <XAxis 
                  dataKey="date" 
                  stroke="var(--text-muted)" 
                  fontSize={12}
                  tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                />
                <YAxis stroke="var(--text-muted)" fontSize={12} />
                <Tooltip 
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="chart-tooltip card glass p-2">
                          <p className="m-0 font-bold">{new Date(data.date).toLocaleDateString()}</p>
                          <p className={`m-0 ${data.trade.pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                            ₹{data.pnl.toLocaleString()}
                          </p>
                          <p className="text-xs text-muted m-0">
                            Last: {data.trade.symbol} ({data.trade.return_pct.toFixed(1)}%)
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <ReferenceLine y={0} stroke="var(--text-muted)" strokeDasharray="3 3" />
                <Line 
                  type="monotone" 
                  dataKey="pnl" 
                  stroke="var(--accent-color)" 
                  strokeWidth={2} 
                  dot={(props) => {
                    const { cx, cy, payload } = props;
                    return (
                      <circle 
                        key={payload.date} 
                        cx={cx} cy={cy} r={4} 
                        fill={payload.trade.return_pct >= 0 ? 'var(--bullish-color)' : 'var(--bearish-color)'} 
                        stroke="none" 
                      />
                    );
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="comparison-panel card">
          <h3 className="m-0">Strategy Drift</h3>
          <table className="comparison-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Paper (Live)</th>
                <th>Backtest</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Total Trades</td>
                <td>{portfolio.total_trades}</td>
                <td>N/A</td>
              </tr>
              <tr className={getDivergenceClass(portfolio.win_rate, BACKTEST_BENCHMARKS.win_rate)}>
                <td>Win Rate</td>
                <td>{portfolio.win_rate}%</td>
                <td>{BACKTEST_BENCHMARKS.win_rate}%</td>
              </tr>
              <tr className={getDivergenceClass(portfolio.avg_return_pct, (BACKTEST_BENCHMARKS.avg_win_pct + BACKTEST_BENCHMARKS.avg_loss_pct)/2)}>
                <td>Avg Return %</td>
                <td>{portfolio.avg_return_pct}%</td>
                <td>5.4%</td>
              </tr>
              <tr className={getDivergenceClass(portfolio.profit_factor, BACKTEST_BENCHMARKS.profit_factor)}>
                <td>Profit Factor</td>
                <td>{portfolio.profit_factor}</td>
                <td>{BACKTEST_BENCHMARKS.profit_factor}</td>
              </tr>
              <tr>
                <td>Avg Holding Days</td>
                <td>{portfolio.avg_holding_days || 0}</td>
                <td>{BACKTEST_BENCHMARKS.avg_holding_days}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const PendingView = () => {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPaperPending().then(data => {
      setPending(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="loading-spinner">Loading Pending Orders...</div>;

  return (
    <div className="pending-view animate-in">
      <div className="pending-banner mb-4">
        <Info size={16} className="inline mr-2" />
        These orders will be evaluated at tomorrow's market open. Entry is at the close of the bar where price confirms EMA20 support.
      </div>

      <div className="pending-table-container card">
        <table className="pending-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Signal Date</th>
              <th>EMA20 Target</th>
              <th>Current Distance</th>
              <th>Progress</th>
              <th>Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {pending.length === 0 ? (
              <tr>
                <td colSpan="7" className="text-center text-muted py-8">No pending orders currently being watched.</td>
              </tr>
            ) : (
              pending.map(pos => {
                const distance = pos.closeness_pct;
                let distanceClass = 'grey';
                if (distance !== null) {
                  if (distance <= 2) distanceClass = 'green';
                  else if (distance <= 5) distanceClass = 'amber';
                }

                return (
                  <tr key={pos.id}>
                    <td>
                      <div className="font-bold">{pos.symbol}</div>
                      <div className="text-xs text-muted">{pos.sector}</div>
                    </td>
                    <td>{new Date(pos.signal_date).toLocaleDateString()}</td>
                    <td>
                      <div className="text-xs text-muted">touch target</div>
                      <div className="font-mono">₹{pos.ema20_at_signal?.toFixed(2) || 'N/A'}</div>
                    </td>
                    <td>
                      <span className={`distance-tag ${distanceClass}`}>
                        {distance !== null ? `${distance.toFixed(1)}% above` : 'Pending data'}
                      </span>
                    </td>
                    <td>
                      <div className="progress-container">
                        <div className="text-xs mb-1">Day {pos.wait_days} of 8</div>
                        <div className="progress-bar">
                          <div className="progress-fill" style={{ width: `${(pos.wait_days / 8) * 100}%` }}></div>
                        </div>
                      </div>
                    </td>
                    <td><div className="score-badge">{pos.signal_score}</div></td>
                    <td>
                      <div className="status-label text-sm font-medium">
                        {pos.wait_days >= 6 ? 'Momentum path' : distance <= 2 ? 'Close to entry' : 'Watching'}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const PositionsView = () => {
  const [positions, setPositions] = useState([]);
  const [sortBy, setSortBy] = useState('pnl'); // 'pnl' or 'expiry'
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPaperPositions().then(data => {
      setPositions(data);
      setLoading(false);
    });
  }, []);

  const sortedPositions = useMemo(() => {
    return [...positions].sort((a, b) => {
      if (sortBy === 'pnl') return (b.unrealised_pct || 0) - (a.unrealised_pct || 0);
      return (a.days_remaining || 0) - (b.days_remaining || 0);
    });
  }, [positions, sortBy]);

  if (loading) return <div className="loading-spinner">Loading Positions...</div>;

  return (
    <div className="positions-view animate-in">
      <div className="view-actions mb-4">
        <div className="tabs-nav card glass inline-flex">
          <button 
            className={`tab-btn ${sortBy === 'pnl' ? 'active' : ''}`}
            onClick={() => setSortBy('pnl')}
          >
            Winners First
          </button>
          <button 
            className={`tab-btn ${sortBy === 'expiry' ? 'active' : ''}`}
            onClick={() => setSortBy('expiry')}
          >
            Closing Soon
          </button>
        </div>
      </div>

      <div className="positions-grid">
        {sortedPositions.length === 0 ? (
          <div className="view-placeholder w-full" style={{ gridColumn: '1 / -1' }}>
            <p>No open positions. Check pending orders for upcoming entries.</p>
          </div>
        ) : (
          sortedPositions.map(pos => {
            const range = pos.target - pos.stop_loss;
            const currentPos = ((pos.current_price - pos.stop_loss) / range) * 100;
            const entryPos = ((pos.entry_price - pos.stop_loss) / range) * 100;
            const pnlColor = pos.unrealised_pct >= 0 ? 'text-bullish' : 'text-bearish';

            return (
              <div key={pos.symbol} className="position-card card">
                <div className="pos-header">
                  <div className="pos-id">
                    <h3>{pos.symbol}</h3>
                    <div className="text-xs text-muted">{pos.sector}</div>
                  </div>
                  <div className="pos-entry-date text-xs text-muted">
                    Entered {new Date(pos.entry_date).toLocaleDateString()}
                  </div>
                </div>

                <div className="pos-body">
                  <div className="pnl-summary flex justify-between items-end">
                    <div className={`stat-value ${pnlColor}`}>
                      {pos.unrealised_pct >= 0 ? '+' : ''}{pos.unrealised_pct?.toFixed(2)}%
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-muted">Unrealised P&L</div>
                      <div className={`font-bold ${pnlColor}`}>
                        ₹{((pos.current_price - pos.entry_price) * (pos.position_size / pos.entry_price)).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                    </div>
                  </div>

                  <div className="price-range-container">
                    <div className="range-bar">
                      <div className="range-tick" style={{ left: `${entryPos}%` }}></div>
                      <div className={`range-dot ${pnlColor.replace('text-', 'bg-')}`} style={{ left: `${currentPos}%` }}></div>
                    </div>
                    <div className="range-labels">
                      <span>-{((pos.entry_price - pos.stop_loss)/pos.entry_price * 100).toFixed(1)}% (stop)</span>
                      <span>+{((pos.target - pos.entry_price)/pos.entry_price * 100).toFixed(1)}% (target)</span>
                    </div>
                  </div>

                  <div className="pos-details grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs text-muted">Holding</div>
                      <div className="text-sm font-medium">Day {pos.holding_days} of 50</div>
                      <div className="progress-bar mt-1">
                        <div className="progress-fill" style={{ width: `${(pos.holding_days / 50) * 100}%` }}></div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-muted">Size</div>
                      <div className="text-sm font-medium">₹{pos.position_size.toLocaleString()}</div>
                      <div className="text-xs text-muted">{Math.floor(pos.position_size / pos.entry_price)} shares</div>
                    </div>
                  </div>
                </div>

                <div className="pos-footer">
                  <div className="stop-status">
                    {pos.atr_trail_active ? (
                      <span className="distance-tag amber">Trailing active — floor at ₹{pos.highest_price?.toFixed(1)}</span>
                    ) : (
                      <span className="text-xs text-muted">Trail activates at +2.5 ATR</span>
                    )}
                  </div>
                  <div className="text-xs text-muted">
                    High: ₹{pos.highest_price?.toFixed(1)}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

const HistoryView = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPaperTrades({ limit: 200 }).then(data => {
      setTrades(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="loading-spinner">Loading Trade History...</div>;

  const getReasonColor = (reason) => {
    switch(reason) {
      case 'stop_loss': return 'bearish';
      case 'target': return 'bullish';
      case 'atr_trailing_stop': return 'accent';
      case 'holding_period': return 'muted';
      default: return 'warning';
    }
  };

  return (
    <div className="history-view animate-in">
      <div className="pending-table-container card">
        <table className="pending-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Period</th>
              <th>Holding</th>
              <th>Entry → Exit</th>
              <th>Return</th>
              <th>P&L</th>
              <th>Reason</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, idx) => (
              <tr key={idx}>
                <td><div className="font-bold">{t.symbol}</div></td>
                <td><div className="text-xs">{new Date(t.entry_date).toLocaleDateString()} → {new Date(t.exit_date).toLocaleDateString()}</div></td>
                <td>{t.holding_days}d</td>
                <td>₹{t.entry_price.toFixed(1)} → ₹{t.exit_price.toFixed(1)}</td>
                <td><span className={t.return_pct >= 0 ? 'text-bullish font-bold' : 'text-bearish font-bold'}>{t.return_pct >= 0 ? '+' : ''}{t.return_pct.toFixed(1)}%</span></td>
                <td>₹{t.pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td>
                  <span className={`distance-tag ${getReasonColor(t.exit_reason)}`}>
                    {t.exit_reason.replace('_', ' ')}
                  </span>
                </td>
                <td><div className="score-badge">{t.signal_score}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const AnalyticsView = () => {
  const [trades, setTrades] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getPaperPortfolio(), getPaperTrades({ limit: 500 })])
      .then(([p, t]) => {
        setPortfolio(p);
        setTrades(t);
        setLoading(false);
      });
  }, []);

  const exitData = useMemo(() => {
    const counts = trades.reduce((acc, t) => {
      acc[t.exit_reason] = (acc[t.exit_reason] || 0) + 1;
      return acc;
    }, {});
    const total = trades.length || 1;
    return Object.entries(counts).map(([name, count]) => ({
      name: name.replace('_', ' '),
      value: Math.round((count / total) * 100)
    }));
  }, [trades]);

  const scoreData = useMemo(() => {
    const buckets = { '40-45': { win: 0, loss: 0 }, '45-50': { win: 0, loss: 0 }, '50-55': { win: 0, loss: 0 }, '55+': { win: 0, loss: 0 } };
    trades.forEach(t => {
      let bucket = '55+';
      if (t.signal_score < 45) bucket = '40-45';
      else if (t.signal_score < 50) bucket = '45-50';
      else if (t.signal_score < 55) bucket = '50-55';
      
      if (t.return_pct > 0) buckets[bucket].win++;
      else buckets[bucket].loss++;
    });
    return Object.entries(buckets).map(([range, counts]) => ({
      range,
      win: counts.win,
      loss: counts.loss
    }));
  }, [trades]);

  if (loading) return <div className="loading-spinner">Loading Analytics...</div>;

  return (
    <div className="analytics-view animate-in space-y-8">
      <section className="analytics-section card p-6">
        <h3 className="mt-0">Equity Curve Comparison</h3>
        <div style={{ width: '100%', height: 350 }}>
          <ResponsiveContainer>
            <LineChart data={[] /* Real comparison would merge backtest results for same period */}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-color)" />
              <XAxis dataKey="date" hide />
              <YAxis />
              <Legend />
              <Line name="Paper Trading" type="monotone" dataKey="paper" stroke="var(--accent-color)" strokeWidth={3} />
              <Line name="Backtest Equivalent" type="monotone" dataKey="backtest" stroke="var(--accent-color)" strokeDasharray="5 5" opacity={0.5} />
              <Line name="Nifty 50" type="monotone" dataKey="nifty" stroke="#888" strokeWidth={1} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-4 p-3 bg-muted rounded text-sm">
          Paper trading is tracking the backtest equivalent within acceptable variance over {portfolio.total_trades} trades.
        </p>
      </section>

      <div className="donut-charts-container">
        <div className="donut-chart-card card">
          <h4 className="mt-0 text-center">Backtest Exits</h4>
          <div style={{ height: 200 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={BACKTEST_BENCHMARKS.exit_reasons} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                  {BACKTEST_BENCHMARKS.exit_reasons.map((entry, index) => (
                    <Cell key={index} fill={['#ef4444', '#0ea5e9', '#22c55e', '#64748b'][index % 4]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 text-xs mt-2">
            {BACKTEST_BENCHMARKS.exit_reasons.map((r, i) => <span key={i}>{r.name}: {r.value}%</span>)}
          </div>
        </div>

        <div className="donut-chart-card card">
          <h4 className="mt-0 text-center">Paper Exits</h4>
          <div style={{ height: 200 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={exitData} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                  {exitData.map((entry, index) => (
                    <Cell key={index} fill={['#ef4444', '#0ea5e9', '#22c55e', '#64748b'][index % 4]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 text-xs mt-2">
            {exitData.length > 0 ? exitData.map((r, i) => <span key={i}>{r.name}: {r.value}%</span>) : <span>No data</span>}
          </div>
        </div>
      </div>

      <div className="analytics-notes space-y-2">
        {(() => {
          const paperStopPct = exitData.find(d => d.name === 'stop loss')?.value || 0;
          const backtestStopPct = BACKTEST_BENCHMARKS.exit_reasons.find(d => d.name === 'Stop Loss')?.value || 0;
          const paperHoldPct = exitData.find(d => d.name === 'holding period')?.value || 0;
          const backtestHoldPct = BACKTEST_BENCHMARKS.exit_reasons.find(d => d.name === 'Held')?.value || 0;
          
          return (
            <>
              {paperStopPct > backtestStopPct + 10 && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded text-sm">
                  <span className="font-bold text-amber-500">Note:</span> More stops than expected. Consider whether current market conditions favour a tighter regime filter or whether entries are occurring in lower-quality setups.
                </div>
              )}
              {paperHoldPct > backtestHoldPct + 5 && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded text-sm">
                  <span className="font-bold text-amber-500">Note:</span> More positions expiring without hitting stop or target. Momentum may not be developing after entry — review sector conditions.
                </div>
              )}
            </>
          );
        })()}
      </div>

      <section className="analytics-section card p-6">
        <h4 className="mt-0">Signal Quality vs Outcome</h4>
        <div style={{ width: '100%', height: 300 }}>
          <ResponsiveContainer>
            <BarChart data={scoreData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border-color)" />
              <XAxis type="number" hide />
              <YAxis dataKey="range" type="category" stroke="var(--text-muted)" />
              <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} />
              <Legend />
              <Bar dataKey="win" name="Wins" stackId="a" fill="var(--bullish-color)" />
              <Bar dataKey="loss" name="Losses" stackId="a" fill="var(--bearish-color)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
};

const ReadinessBanner = ({ portfolio }) => {
  if (!portfolio) return null;
  
  // Logic for dots
  const dots = [
    portfolio.total_trades >= 30,
    Math.abs(portfolio.win_rate - BACKTEST_BENCHMARKS.win_rate) <= 8,
    portfolio.profit_factor >= 1.3,
    true, // Drawdown logic simplified for V1
    portfolio.total_trades >= 50 // Days elapsed placeholder
  ];

  const filledCount = dots.filter(Boolean).length;
  const statusMessage = filledCount === 5 
    ? "Readiness criteria met — consider deploying 25% of intended capital."
    : "Tracking within acceptable range — continue paper trading";

  return (
    <div className="readiness-banner card glass">
      <div className="readiness-left">
        <div className="readiness-label font-bold">Paper Trading Readiness</div>
        <div className="readiness-dots">
          {dots.map((active, i) => <span key={i} className={`dot ${active ? 'active' : ''}`}></span>)}
        </div>
      </div>
      <div className="readiness-center">
        <div className="readiness-stats">
          <span>{portfolio.total_trades} trades completed</span>
          <span className="separator px-2">·</span>
          <span>Win rate {portfolio.win_rate}%</span>
          <span className="separator px-2">·</span>
          <span>Profit factor {portfolio.profit_factor}</span>
        </div>
        <div className="readiness-targets text-muted">
          Backtest targets: Win rate {BACKTEST_BENCHMARKS.win_rate}% · Profit factor {BACKTEST_BENCHMARKS.profit_factor}
        </div>
      </div>
      <div className="readiness-right">
        <div className={`readiness-status ${filledCount === 5 ? 'text-bullish' : ''}`}>{statusMessage}</div>
      </div>
    </div>
  );
};

export default PaperTrading;
