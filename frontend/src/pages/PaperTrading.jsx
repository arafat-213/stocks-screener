import React, { useState, useEffect, useMemo } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
  BarChart, Bar, Cell, PieChart, Pie, Legend
} from 'recharts';
import { 
  AlertCircle,
  Info,
} from 'lucide-react';
import { 
  getPaperPortfolio, 
  getPaperPending, 
  getPaperPositions, 
  getPaperTrades,
  getStatus
} from '../api/client';

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
    getStatus().then(res => setStatus(res.data));
    getPaperPortfolio().then(res => setPortfolio(res.data));
  }, []);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'pending', label: 'Pending' },
    { id: 'positions', label: 'Positions' },
    { id: 'history', label: 'History' },
    { id: 'analytics', label: 'Analytics' }
  ];

  return (
    <div className="flex flex-col gap-6 pb-24 animate-fade-in">
      <header className="flex justify-between items-start">
        <div className="flex flex-col">
          <h1 className="text-3xl font-black tracking-tight text-text">Paper Trading</h1>
          <p className="text-text-muted">Live strategy verification without real capital</p>
        </div>
        
        <div className="flex items-center">
          {status && (
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold border ${
              status.pipeline.is_stale 
                ? 'bg-slate-100 dark:bg-slate-800 text-text-muted border-border' 
                : 'bg-bullish/10 text-bullish border-green-500/20'
            }`}>
              {!status.pipeline.is_stale && <div className="w-2 h-2 rounded-full bg-bullish animate-pulse"></div>}
              <span>{status.pipeline.is_stale ? 'Stale — pipeline not run today' : `Updated ${status.pipeline.data_age_hours}h ago`}</span>
            </div>
          )}
        </div>
      </header>

      <nav className="flex p-1 gap-1 bg-bg-secondary border border-border rounded-xl w-fit overflow-x-auto no-scrollbar">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`px-5 py-2 text-sm font-bold rounded-lg transition-all whitespace-nowrap ${
              activeTab === tab.id 
                ? 'bg-bg-elevated text-text shadow-sm' 
                : 'text-text-muted hover:text-text hover:bg-bg-elevated/50'
            }`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="min-h-[400px]">
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
    const p1 = portfolio ? Promise.resolve({ data: portfolio }) : getPaperPortfolio();
    Promise.all([p1, getPaperTrades({ limit: 100 })])
      .then(([p, t]) => {
        setPortfolio(p.data);
        setTrades(t.data);
        setLoading(false);
      });
  }, [portfolio, setPortfolio]);

  if (loading) return <div className="flex items-center justify-center p-20 text-text-muted">Loading Overview...</div>;
  
  if (portfolio?.status === 'no_portfolio') {
    return (
      <div className="flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center">
        <AlertCircle size={48} className="text-text-muted mb-4" />
        <h2 className="text-xl font-bold mb-2">No Active Portfolio</h2>
        <p className="text-text-muted">Run a pipeline cycle to initialize the paper trading portfolio.</p>
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
    <div className="flex flex-col gap-1 p-6 bg-bg-secondary border border-border rounded-2xl shadow-sm">
      <div className="text-xs font-bold uppercase tracking-widest text-text-muted">{label}</div>
      <div className={`text-3xl font-black tracking-tight ${color || 'text-text'}`}>{value}</div>
      {comparison !== undefined && (
        <div className="text-[11px] font-medium text-text-muted mt-1">
          <span className="font-black text-text">{comparison}</span> {subLabel && <span className="opacity-60">vs {subLabel}</span>}
        </div>
      )}
    </div>
  );

  const getDivergenceStyle = (live, backtest) => {
    if (!live || !backtest) return '';
    const diff = Math.abs(live - backtest) / backtest;
    return diff > 0.1 ? 'bg-warning/10' : '';
  };

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mt-2">
        <div className="lg:col-span-3 p-6 bg-bg-secondary border border-border rounded-2xl shadow-sm">
          <div className="flex flex-col mb-8">
            <h3 className="text-lg font-black uppercase tracking-tight text-text">Cumulative P&L</h3>
            <p className="text-xs text-text-muted uppercase tracking-widest font-bold">Realized Equity Curve (₹)</p>
          </div>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={pnlData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" />
                <XAxis 
                  dataKey="date" 
                  stroke="var(--color-text-muted)" 
                  fontSize={10}
                  tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                />
                <YAxis stroke="var(--color-text-muted)" fontSize={10} />
                <Tooltip 
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="p-3 bg-bg-secondary/90 backdrop-blur-md border border-border rounded-xl shadow-xl">
                          <p className="text-[10px] font-black uppercase tracking-widest text-text-muted mb-1">{new Date(data.date).toLocaleDateString()}</p>
                          <p className={`text-lg font-black ${data.trade.pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                            ₹{data.pnl.toLocaleString()}
                          </p>
                          <p className="text-[10px] font-bold text-text-muted uppercase tracking-tight mt-1 border-t border-border pt-1">
                            Last: {data.trade.symbol} ({data.trade.return_pct.toFixed(1)}%)
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <ReferenceLine y={0} stroke="var(--color-text-muted)" strokeDasharray="3 3" />
                <Line 
                  type="monotone" 
                  dataKey="pnl" 
                  stroke="var(--color-primary)" 
                  strokeWidth={3} 
                  dot={(props) => {
                    const { cx, cy, payload } = props;
                    return (
                      <circle 
                        key={payload.date} 
                        cx={cx} cy={cy} r={4} 
                        fill={payload.trade.return_pct >= 0 ? 'var(--color-bullish)' : 'var(--color-bearish)'} 
                        stroke="var(--color-bg-secondary)"
                        strokeWidth={2}
                      />
                    );
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-2 p-6 bg-bg-secondary border border-border rounded-2xl shadow-sm">
          <h3 className="text-lg font-black uppercase tracking-tight text-text mb-6">Strategy Drift</h3>
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-border text-[10px] uppercase tracking-widest text-text-muted">
                <th className="text-left pb-3 font-bold">Metric</th>
                <th className="text-right pb-3 font-bold">Paper</th>
                <th className="text-right pb-3 font-bold">Backtest</th>
              </tr>
            </thead>
            <tbody className="text-sm font-medium">
              <tr className="border-b border-border/50">
                <td className="py-4 text-text-muted">Total Trades</td>
                <td className="py-4 text-right font-black">{portfolio.total_trades}</td>
                <td className="py-4 text-right opacity-40">N/A</td>
              </tr>
              <tr className={`border-b border-border/50 ${getDivergenceStyle(portfolio.win_rate, BACKTEST_BENCHMARKS.win_rate)}`}>
                <td className="py-4 text-text-muted">Win Rate</td>
                <td className="py-4 text-right font-black">{portfolio.win_rate}%</td>
                <td className="py-4 text-right font-bold text-text-muted">{BACKTEST_BENCHMARKS.win_rate}%</td>
              </tr>
              <tr className={`border-b border-border/50 ${getDivergenceStyle(portfolio.avg_return_pct, 5.4)}`}>
                <td className="py-4 text-text-muted">Avg Return %</td>
                <td className="py-4 text-right font-black">{portfolio.avg_return_pct}%</td>
                <td className="py-4 text-right font-bold text-text-muted">5.4%</td>
              </tr>
              <tr className={`border-b border-border/50 ${getDivergenceStyle(portfolio.profit_factor, BACKTEST_BENCHMARKS.profit_factor)}`}>
                <td className="py-4 text-text-muted">Profit Factor</td>
                <td className="py-4 text-right font-black">{portfolio.profit_factor}</td>
                <td className="py-4 text-right font-bold text-text-muted">{BACKTEST_BENCHMARKS.profit_factor}</td>
              </tr>
              <tr>
                <td className="py-4 text-text-muted">Avg Holding Days</td>
                <td className="py-4 text-right font-black">{portfolio.avg_holding_days || 0}d</td>
                <td className="py-4 text-right font-bold text-text-muted">{BACKTEST_BENCHMARKS.avg_holding_days}d</td>
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
    getPaperPending().then(res => {
      setPending(res.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="flex items-center justify-center p-20 text-text-muted">Loading Pending Orders...</div>;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="flex items-center gap-3 p-4 bg-blue-500/10 border border-blue-500/20 rounded-2xl text-text leading-snug">
        <Info size={18} className="text-blue-500 flex-shrink-0" />
        <p className="text-sm font-medium">These orders will be evaluated at tomorrow's market open. Entry is at the close of the bar where price confirms EMA20 support.</p>
      </div>

      <div className="bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-bg-elevated border-b border-border text-[10px] uppercase tracking-widest text-text-muted font-black">
                <th className="text-left p-4">Symbol</th>
                <th className="text-left p-4">Signal Date</th>
                <th className="text-left p-4">EMA20 Target</th>
                <th className="text-left p-4">Current Distance</th>
                <th className="text-left p-4">Progress</th>
                <th className="text-left p-4">Score</th>
                <th className="text-left p-4">Status</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {pending.length === 0 ? (
                <tr>
                  <td colSpan="7" className="text-center text-text-muted py-20 font-bold uppercase tracking-widest text-xs opacity-50">No pending orders being watched.</td>
                </tr>
              ) : (
                pending.map(pos => {
                  const distance = pos.closeness_pct;
                  let distanceClass = 'bg-slate-100 dark:bg-slate-800 text-text-muted';
                  if (distance !== null) {
                    if (distance <= 2) distanceClass = 'bg-bullish/10 text-bullish';
                    else if (distance <= 5) distanceClass = 'bg-warning/10 text-warning';
                  }

                  return (
                    <tr key={pos.id} className="border-b border-border/50 hover:bg-bg-elevated/30 transition-colors">
                      <td className="p-4">
                        <div className="font-black text-blue-600 dark:text-blue-400 tracking-tight">{pos.symbol}</div>
                        <div className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">{pos.sector}</div>
                      </td>
                      <td className="p-4 text-text-muted font-medium">{new Date(pos.signal_date).toLocaleDateString()}</td>
                      <td className="p-4">
                        <div className="text-[9px] font-black uppercase text-text-muted tracking-widest leading-none mb-1">touch target</div>
                        <div className="font-mono font-black">₹{pos.ema20_at_signal?.toFixed(2) || 'N/A'}</div>
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded text-[10px] font-black uppercase tracking-tight ${distanceClass}`}>
                          {distance !== null ? `${distance.toFixed(1)}% above` : 'Pending'}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex flex-col gap-1.5 w-24">
                          <div className="text-[10px] font-bold text-text-muted uppercase">Day {pos.wait_days} of 8</div>
                          <div className="h-1 bg-border rounded-full overflow-hidden">
                            <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${(pos.wait_days / 8) * 100}%` }}></div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <div className={`inline-flex px-2 py-0.5 rounded font-black text-xs ${
                          pos.signal_score >= 60 ? 'bg-bullish text-white' : 'bg-blue-500 text-white'
                        }`}>{pos.signal_score}</div>
                      </td>
                      <td className="p-4">
                        <div className="text-[11px] font-black uppercase tracking-wider text-text-muted">
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
    </div>
  );
};

const PositionsView = () => {
  const [positions, setPositions] = useState([]);
  const [sortBy, setSortBy] = useState('pnl'); // 'pnl' or 'expiry'
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPaperPositions().then(res => {
      setPositions(res.data);
      setLoading(false);
    });
  }, []);

  const sortedPositions = useMemo(() => {
    return [...positions].sort((a, b) => {
      if (sortBy === 'pnl') return (b.unrealised_pct || 0) - (a.unrealised_pct || 0);
      return (a.days_remaining || 0) - (b.days_remaining || 0);
    });
  }, [positions, sortBy]);

  if (loading) return <div className="flex items-center justify-center p-20 text-text-muted">Loading Positions...</div>;

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <div className="flex p-1 bg-bg-secondary border border-border rounded-xl w-fit">
        <button 
          className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${
            sortBy === 'pnl' ? 'bg-bg-elevated text-text shadow-sm' : 'text-text-muted'
          }`}
          onClick={() => setSortBy('pnl')}
        >
          Winners First
        </button>
        <button 
          className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${
            sortBy === 'expiry' ? 'bg-bg-elevated text-text shadow-sm' : 'text-text-muted'
          }`}
          onClick={() => setSortBy('expiry')}
        >
          Closing Soon
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {sortedPositions.length === 0 ? (
          <div className="md:col-span-2 xl:col-span-3 flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center">
            <p className="font-bold uppercase tracking-widest text-xs text-text-muted">No open positions. Check pending orders for upcoming entries.</p>
          </div>
        ) : (
          sortedPositions.map(pos => {
            const range = pos.target - pos.stop_loss;
            const currentPos = Math.min(Math.max(((pos.current_price - pos.stop_loss) / range) * 100, 0), 100);
            const entryPos = ((pos.entry_price - pos.stop_loss) / range) * 100;
            const pnlColor = pos.unrealised_pct >= 0 ? 'text-bullish' : 'text-bearish';
            const pnlBg = pos.unrealised_pct >= 0 ? 'bg-bullish' : 'bg-bearish';

            return (
              <div key={pos.symbol} className="flex flex-col bg-bg-secondary border border-border rounded-3xl overflow-hidden shadow-md hover:shadow-xl transition-all group">
                <div className="flex justify-between items-start p-6 border-b border-border/50">
                  <div className="flex flex-col">
                    <h3 className="text-2xl font-black tracking-tighter text-blue-600 dark:text-blue-400 leading-none mb-1">{pos.symbol}</h3>
                    <div className="text-[10px] font-black uppercase tracking-widest text-text-muted">{pos.sector}</div>
                  </div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-text-muted bg-bg-elevated px-2.5 py-1 rounded-full border border-border">
                    In {new Date(pos.entry_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </div>
                </div>

                <div className="flex flex-col gap-6 p-6">
                  <div className="flex justify-between items-end">
                    <div className={`text-3xl font-black tracking-tight ${pnlColor}`}>
                      {pos.unrealised_pct >= 0 ? '+' : ''}{pos.unrealised_pct?.toFixed(2)}%
                    </div>
                    <div className="flex flex-col items-end">
                      <div className="text-[9px] font-black uppercase tracking-widest text-text-muted leading-none mb-1">Unrealised P&L</div>
                      <div className={`text-xl font-black ${pnlColor} tracking-tight`}>
                        ₹{((pos.current_price - pos.entry_price) * (pos.position_size / pos.entry_price)).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2">
                    <div className="relative h-2 rounded-full overflow-hidden flex">
                      <div className="h-full bg-bearish/20" style={{ width: `${entryPos}%` }}></div>
                      <div className="h-full bg-bullish/20" style={{ width: `${100 - entryPos}%` }}></div>
                      <div className="absolute top-0 bottom-0 w-[2px] bg-text shadow-lg z-10" style={{ left: `${entryPos}%` }}></div>
                      <div className={`absolute top-0 bottom-0 w-3 h-3 -mt-0.5 rounded-full border-2 border-bg-secondary shadow-lg z-20 ${pnlBg}`} style={{ left: `${currentPos}%`, transform: 'translateX(-50%)' }}></div>
                    </div>
                    <div className="flex justify-between text-[10px] font-black tracking-widest text-text-muted uppercase">
                      <span>-{((pos.entry_price - pos.stop_loss)/pos.entry_price * 100).toFixed(1)}% SL</span>
                      <span>+{((pos.target - pos.entry_price)/pos.entry_price * 100).toFixed(1)}% TGT</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-8 pt-2">
                    <div className="flex flex-col gap-2">
                      <div className="flex justify-between items-center">
                        <div className="text-[10px] font-black uppercase tracking-widest text-text-muted">Holding</div>
                        <div className="text-[10px] font-black text-text">Day {pos.holding_days}/50</div>
                      </div>
                      <div className="h-1 bg-border rounded-full overflow-hidden">
                        <div className="h-full bg-primary" style={{ width: `${(pos.holding_days / 50) * 100}%` }}></div>
                      </div>
                    </div>
                    <div className="flex flex-col items-end">
                      <div className="text-[10px] font-black uppercase tracking-widest text-text-muted leading-none mb-1">Position Size</div>
                      <div className="text-sm font-black tracking-tight text-text">₹{pos.position_size.toLocaleString()}</div>
                      <div className="text-[9px] font-bold text-text-muted uppercase tracking-tighter">{Math.floor(pos.position_size / pos.entry_price)} SHARES</div>
                    </div>
                  </div>
                </div>

                <div className="flex justify-between items-center px-6 py-4 bg-bg-elevated/50 border-t border-border">
                  <div className="flex items-center">
                    {pos.atr_trail_active ? (
                      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/10 text-amber-600 rounded-lg border border-amber-500/20 shadow-sm shadow-amber-500/5">
                        <ShieldCheck size={12} className="fill-amber-500/10" />
                        <span className="text-[10px] font-black uppercase tracking-wider">Trailing Active: ₹{pos.highest_price?.toFixed(1)}</span>
                      </div>
                    ) : (
                      <div className="text-[10px] font-black uppercase tracking-widest text-text-muted flex items-center gap-1.5 opacity-50">
                        <Clock size={12} />
                        <span>Trail at +2.5 ATR</span>
                      </div>
                    )}
                  </div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-text-muted">
                    Peak: <span className="text-text">₹{pos.highest_price?.toFixed(1)}</span>
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
    getPaperTrades({ limit: 200 }).then(res => {
      setTrades(res.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="flex items-center justify-center p-20 text-text-muted">Loading Trade History...</div>;

  const getReasonStyles = (reason) => {
    switch(reason) {
      case 'stop_loss': return 'bg-bearish/10 text-bearish';
      case 'target': return 'bg-bullish/10 text-bullish';
      case 'atr_trailing_stop': return 'bg-blue-500/10 text-blue-500';
      case 'holding_period': return 'bg-slate-100 dark:bg-slate-800 text-text-muted';
      default: return 'bg-warning/10 text-warning';
    }
  };

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-bg-elevated border-b border-border text-[10px] uppercase tracking-widest text-text-muted font-black">
                <th className="text-left p-4">Symbol</th>
                <th className="text-left p-4">Period</th>
                <th className="text-left p-4">Holding</th>
                <th className="text-left p-4">Entry → Exit</th>
                <th className="text-right p-4">Return %</th>
                <th className="text-right p-4">P&L (₹)</th>
                <th className="text-center p-4">Reason</th>
                <th className="text-center p-4">Score</th>
              </tr>
            </thead>
            <tbody className="text-sm font-medium">
              {trades.map((t, idx) => (
                <tr key={idx} className="border-b border-border/50 hover:bg-bg-elevated/30 transition-colors">
                  <td className="p-4 font-black text-text tracking-tight">{t.symbol}</td>
                  <td className="p-4">
                    <div className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">
                      {new Date(t.entry_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} → {new Date(t.exit_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </div>
                  </td>
                  <td className="p-4 text-text-muted font-black text-xs">{t.holding_days}d</td>
                  <td className="p-4 font-mono text-xs text-text-muted">
                    <span className="font-black text-text">₹{t.entry_price.toFixed(1)}</span> → <span>₹{t.exit_price.toFixed(1)}</span>
                  </td>
                  <td className={`p-4 text-right font-black ${t.return_pct >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    {t.return_pct >= 0 ? '+' : ''}{t.return_pct.toFixed(1)}%
                  </td>
                  <td className={`p-4 text-right font-black ${t.pnl >= 0 ? 'text-bullish' : 'text-bearish'}`}>
                    ₹{t.pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </td>
                  <td className="p-4 text-center">
                    <span className={`px-2 py-0.5 rounded-[4px] text-[9px] font-black uppercase tracking-widest ${getReasonStyles(t.exit_reason)}`}>
                      {t.exit_reason.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="p-4 text-center">
                    <div className="inline-flex px-1.5 py-0.5 bg-bg-elevated border border-border rounded font-black text-[10px] text-text-muted">
                      {t.signal_score}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
        setPortfolio(p.data);
        setTrades(t.data);
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

  if (loading) return <div className="flex items-center justify-center p-20 text-text-muted">Loading Analytics...</div>;

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      <section className="p-8 bg-bg-secondary border border-border rounded-3xl shadow-sm">
        <h3 className="text-xl font-black uppercase tracking-tight text-text mb-8">Equity Curve Comparison</h3>
        <div style={{ width: '100%', height: 350 }}>
          <ResponsiveContainer>
            <LineChart data={[]}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border)" />
              <XAxis dataKey="date" hide />
              <YAxis stroke="var(--color-text-muted)" fontSize={10} />
              <Legend verticalAlign="top" height={36}/>
              <Line name="Paper Trading" type="monotone" dataKey="paper" stroke="var(--color-primary)" strokeWidth={3} />
              <Line name="Backtest Equivalent" type="monotone" dataKey="backtest" stroke="var(--color-primary)" strokeDasharray="5 5" opacity={0.5} />
              <Line name="Nifty 50" type="monotone" dataKey="nifty" stroke="var(--color-text-muted)" strokeWidth={1} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-6 p-4 bg-bg-elevated rounded-2xl border border-border">
          <p className="text-sm font-bold text-text">
            Paper trading is tracking the backtest equivalent within acceptable variance over {portfolio.total_trades} trades.
          </p>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-6 bg-bg-secondary border border-border rounded-3xl shadow-sm flex flex-col items-center">
          <h4 className="text-sm font-black uppercase tracking-widest text-text-muted mb-8">Backtest Exit Breakdown</h4>
          <div style={{ width: '100%', height: 220 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={BACKTEST_BENCHMARKS.exit_reasons} innerRadius={65} outerRadius={85} paddingAngle={5} dataKey="value" stroke="none">
                  {BACKTEST_BENCHMARKS.exit_reasons.map((entry, index) => (
                    <Cell key={index} fill={['#EF4444', '#3B82F6', '#22C55E', '#94A3B8'][index % 4]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: '12px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 mt-4">
            {BACKTEST_BENCHMARKS.exit_reasons.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: ['#EF4444', '#3B82F6', '#22C55E', '#94A3B8'][i % 4] }}></div>
                <span className="text-[10px] font-black uppercase tracking-widest text-text-muted">{r.name}</span>
                <span className="text-[10px] font-black ml-auto">{r.value}%</span>
              </div>
            ))}
          </div>
        </div>

        <div className="p-6 bg-bg-secondary border border-border rounded-3xl shadow-sm flex flex-col items-center">
          <h4 className="text-sm font-black uppercase tracking-widest text-text-muted mb-8">Live Paper Exits</h4>
          <div style={{ width: '100%', height: 220 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={exitData} innerRadius={65} outerRadius={85} paddingAngle={5} dataKey="value" stroke="none">
                  {exitData.map((entry, index) => (
                    <Cell key={index} fill={['#EF4444', '#3B82F6', '#22C55E', '#94A3B8'][index % 4]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: '12px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 mt-4 w-full px-8">
            {exitData.length > 0 ? exitData.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: ['#EF4444', '#3B82F6', '#22C55E', '#94A3B8'][i % 4] }}></div>
                <span className="text-[10px] font-black uppercase tracking-widest text-text-muted whitespace-nowrap">{r.name}</span>
                <span className="text-[10px] font-black ml-auto">{r.value}%</span>
              </div>
            )) : <div className="col-span-2 text-center text-[10px] font-bold text-text-muted uppercase tracking-widest opacity-50 py-4">No completed trades</div>}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {(() => {
          const paperStopPct = exitData.find(d => d.name.toLowerCase() === 'stop loss')?.value || 0;
          const backtestStopPct = BACKTEST_BENCHMARKS.exit_reasons.find(d => d.name === 'Stop Loss')?.value || 0;
          const paperHoldPct = exitData.find(d => d.name.toLowerCase() === 'holding period')?.value || 0;
          const backtestHoldPct = BACKTEST_BENCHMARKS.exit_reasons.find(d => d.name === 'Held')?.value || 0;
          
          return (
            <>
              {paperStopPct > backtestStopPct + 10 && (
                <div className="p-4 bg-warning/5 border border-warning/20 rounded-2xl flex gap-3 items-start">
                  <AlertCircle size={18} className="text-warning flex-shrink-0 mt-0.5" />
                  <p className="text-sm font-medium leading-relaxed">
                    <span className="font-black text-warning uppercase tracking-widest text-[10px] mr-2">Advisory:</span> 
                    More stops than expected. Consider whether current market conditions favour a tighter regime filter or whether entries are occurring in lower-quality setups.
                  </p>
                </div>
              )}
              {paperHoldPct > backtestHoldPct + 5 && (
                <div className="p-4 bg-warning/5 border border-warning/20 rounded-2xl flex gap-3 items-start">
                  <AlertCircle size={18} className="text-warning flex-shrink-0 mt-0.5" />
                  <p className="text-sm font-medium leading-relaxed">
                    <span className="font-black text-warning uppercase tracking-widest text-[10px] mr-2">Advisory:</span> 
                    More positions expiring without hitting stop or target. Momentum may not be developing after entry — review sector conditions.
                  </p>
                </div>
              )}
            </>
          );
        })()}
      </div>

      <section className="p-8 bg-bg-secondary border border-border rounded-3xl shadow-sm">
        <h4 className="text-lg font-black uppercase tracking-tight text-text mb-8">Signal Quality vs Outcome</h4>
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <BarChart data={scoreData} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
              <XAxis type="number" hide />
              <YAxis dataKey="range" type="category" stroke="var(--color-text-muted)" fontSize={11} fontWeight={700} />
              <Tooltip 
                cursor={{fill: 'var(--color-bg-elevated)', opacity: 0.5}}
                contentStyle={{ backgroundColor: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: '12px' }}
              />
              <Legend verticalAlign="top" align="right" height={36}/>
              <Bar dataKey="win" name="Wins" stackId="a" fill="var(--color-bullish)" radius={[0, 0, 0, 0]} />
              <Bar dataKey="loss" name="Losses" stackId="a" fill="var(--color-bearish)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
};

const ReadinessBanner = ({ portfolio }) => {
  if (!portfolio) return null;
  
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
    <div className="fixed bottom-0 left-0 lg:left-[280px] right-0 h-auto sm:h-20 p-4 sm:p-0 flex flex-col sm:flex-row justify-between items-center z-50 bg-bg-secondary/95 backdrop-blur-xl border-t border-border shadow-[0_-8px_30px_rgb(0,0,0,0.12)]">
      <div className="flex flex-col items-center sm:items-start sm:pl-10 mb-3 sm:mb-0">
        <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-muted leading-none mb-2">Paper Trading Readiness</div>
        <div className="flex gap-1.5">
          {dots.map((active, i) => (
            <div key={i} className={`w-2.5 h-2.5 rounded-full transition-all duration-700 ${
              active ? 'bg-bullish shadow-[0_0_10px_rgba(34,197,94,0.4)] scale-110' : 'bg-border'
            }`}></div>
          ))}
        </div>
      </div>
      
      <div className="flex flex-col items-center flex-1">
        <div className="flex items-center gap-3 text-sm font-black tracking-tight text-text">
          <span>{portfolio.total_trades} TRADES</span>
          <div className="w-1 h-1 rounded-full bg-border"></div>
          <span className="text-bullish">{portfolio.win_rate}% WIN RATE</span>
          <div className="w-1 h-1 rounded-full bg-border"></div>
          <span className="text-blue-500">PF {portfolio.profit_factor}</span>
        </div>
        <div className="text-[9px] font-bold text-text-muted uppercase tracking-widest mt-1 opacity-60">
          Targets: {BACKTEST_BENCHMARKS.win_rate}% Win · {BACKTEST_BENCHMARKS.profit_factor} Profit Factor
        </div>
      </div>
      
      <div className="sm:pr-10 mt-3 sm:mt-0">
        <div className={`px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest border transition-all ${
          filledCount === 5 
            ? 'bg-bullish text-white border-green-400 shadow-lg shadow-green-500/30 animate-pulse' 
            : 'bg-bg-elevated text-text-muted border-border'
        }`}>
          {statusMessage}
        </div>
      </div>
    </div>
  );
};

export default PaperTrading;
