import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  History, 
  Briefcase, 
  ChevronRight, 
  X,
  AlertCircle,
  BarChart2,
  PieChart as PieChartIcon,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { 
  getJournalOpen, 
  getJournalClosed, 
  getJournalStats, 
  closeJournalEntry 
} from '../api/client';

const Journal = () => {
  const [activeTab, setActiveTab] = useState('open');
  const [stats, setStats] = useState(null);
  const [openPositions, setOpenPositions] = useState([]);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [closing, setClosing] = useState(false);

  // Form state for closing trade
  const [exitPrice, setExitPrice] = useState('');
  const [exitReason, setExitReason] = useState('target');

  const loadData = async () => {
    setLoading(true);
    try {
      const [statsRes, openRes, closedRes] = await Promise.all([
        getJournalStats(),
        getJournalOpen(),
        getJournalClosed()
      ]);
      setStats(statsRes.data);
      setOpenPositions(openRes.data);
      setTradeHistory(closedRes.data);
    } catch (error) {
      console.error('Error loading journal data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCloseClick = (trade) => {
    setSelectedTrade(trade);
    setExitPrice(trade.current_price || trade.entry_price);
    setExitReason('target');
    setModalOpen(true);
  };

  const handleCloseSubmit = async (e) => {
    e.preventDefault();
    if (!selectedTrade || !exitPrice) return;

    setClosing(true);
    try {
      await closeJournalEntry(selectedTrade.id, {
        exit_price: parseFloat(exitPrice),
        exit_reason: exitReason
      });
      setModalOpen(false);
      loadData();
    } catch (error) {
      console.error('Error closing trade:', error);
      alert('Failed to close trade. Please check console for details.');
    } finally {
      setClosing(false);
    }
  };

  if (loading && !stats) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-text-muted font-bold uppercase tracking-widest text-xs">Loading Journal...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8 pb-24 animate-fade-in">
      <header className="flex justify-between items-start">
        <div className="flex flex-col">
          <h1 className="text-3xl font-black tracking-tight text-text">Trade Journal</h1>
          <p className="text-text-muted">Track and analyze your live market performance</p>
        </div>
        <div className="flex gap-2">
          <div className="px-4 py-2 bg-bg-secondary border border-border rounded-xl shadow-sm">
            <div className="text-[10px] font-black uppercase tracking-widest text-text-muted mb-1">Last Updated</div>
            <div className="text-xs font-bold text-text">{new Date().toLocaleDateString()}</div>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard 
          label="Total Realized P&L" 
          value={`₹${stats?.total_pnl?.toLocaleString() || 0}`}
          subValue={`${stats?.total_return_pct?.toFixed(1)}% Return`}
          icon={<BarChart2 className="text-primary" size={20} />}
          trend={stats?.total_pnl >= 0 ? 'up' : 'down'}
        />
        <StatCard 
          label="Open Unrealized P&L" 
          value={`₹${stats?.unrealized_pnl?.toLocaleString() || 0}`}
          subValue={`${stats?.open_positions || 0} Positions`}
          icon={<PieChartIcon className="text-blue-500" size={20} />}
          trend={stats?.unrealized_pnl >= 0 ? 'up' : 'down'}
        />
        <StatCard 
          label="Strategy Win Rate" 
          value={`${stats?.win_rate || 0}%`}
          subValue={`${stats?.total_trades || 0} Total Trades`}
          icon={<TrendingUp className="text-bullish" size={20} />}
          progress={stats?.win_rate}
        />
      </div>

      {/* Tabs */}
      <div className="flex p-1 gap-1 bg-bg-secondary border border-border rounded-xl w-fit">
        <button
          className={`px-6 py-2 text-sm font-bold rounded-lg transition-all flex items-center gap-2 ${
            activeTab === 'open' 
              ? 'bg-bg-elevated text-text shadow-sm' 
              : 'text-text-muted hover:text-text hover:bg-bg-elevated/50'
          }`}
          onClick={() => setActiveTab('open')}
        >
          <Briefcase size={16} />
          Open Positions ({openPositions.length})
        </button>
        <button
          className={`px-6 py-2 text-sm font-bold rounded-lg transition-all flex items-center gap-2 ${
            activeTab === 'history' 
              ? 'bg-bg-elevated text-text shadow-sm' 
              : 'text-text-muted hover:text-text hover:bg-bg-elevated/50'
          }`}
          onClick={() => setActiveTab('history')}
        >
          <History size={16} />
          Trade History
        </button>
      </div>

      {/* Content Area */}
      <div className="min-h-[400px]">
        {activeTab === 'open' ? (
          <OpenPositionsTable 
            positions={openPositions} 
            onCloseTrade={handleCloseClick} 
          />
        ) : (
          <TradeHistoryTable 
            trades={tradeHistory} 
          />
        )}
      </div>

      {/* Close Trade Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-bg-secondary border border-border w-full max-w-md rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex justify-between items-center p-6 border-b border-border">
              <h3 className="text-xl font-black text-text uppercase tracking-tight">Close Position</h3>
              <button 
                onClick={() => setModalOpen(false)}
                className="p-2 hover:bg-bg-elevated rounded-full transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={handleCloseSubmit} className="p-6 flex flex-col gap-6">
              <div className="flex items-center gap-4 p-4 bg-bg-elevated rounded-2xl border border-border">
                <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center text-primary font-black text-xl">
                  {selectedTrade?.symbol?.substring(0, 1)}
                </div>
                <div>
                  <div className="text-lg font-black text-text">{selectedTrade?.symbol}</div>
                  <div className="text-xs font-bold text-text-muted uppercase tracking-widest">Entry: ₹{selectedTrade?.entry_price?.toLocaleString()}</div>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Exit Price (₹)</label>
                <input 
                  type="number" 
                  step="0.01"
                  required
                  value={exitPrice}
                  onChange={(e) => setExitPrice(e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder="0.00"
                />
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-text-muted ml-1">Exit Reason</label>
                <select 
                  value={exitReason}
                  onChange={(e) => setExitReason(e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 font-bold text-text focus:outline-none focus:ring-2 focus:ring-primary/50 appearance-none"
                >
                  <option value="target">Target Reached</option>
                  <option value="stop_loss">Stop Loss Hit</option>
                  <option value="atr_trailing_stop">Trailing Stop Hit</option>
                  <option value="holding_period">Holding Period Expired</option>
                  <option value="manual">Manual Exit (Custom)</option>
                </select>
              </div>

              <button 
                type="submit"
                disabled={closing}
                className="w-full bg-primary hover:bg-primary-dark disabled:opacity-50 text-white font-black py-4 rounded-2xl transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2"
              >
                {closing ? 'CLOSING...' : 'CONFIRM EXIT'}
                {!closing && <ChevronRight size={18} />}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

// --- Sub-components ---

const StatCard = ({ label, value, subValue, icon, trend, progress }) => (
  <div className="bg-bg-secondary border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-4 relative overflow-hidden group">
    <div className="flex justify-between items-start">
      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-black uppercase tracking-widest text-text-muted">{label}</span>
        <span className="text-2xl font-black text-text tracking-tight">{value}</span>
      </div>
      <div className="p-2 bg-bg-elevated rounded-xl border border-border shadow-sm group-hover:scale-110 transition-transform">
        {icon}
      </div>
    </div>
    
    <div className="flex items-center gap-2">
      {trend && (
        <div className={`flex items-center gap-0.5 text-xs font-black ${trend === 'up' ? 'text-bullish' : 'text-bearish'}`}>
          {trend === 'up' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
        </div>
      )}
      <span className="text-xs font-bold text-text-muted">{subValue}</span>
    </div>

    {progress !== undefined && (
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-border overflow-hidden">
        <div 
          className="h-full bg-bullish transition-all duration-1000 ease-out" 
          style={{ width: `${progress}%` }}
        ></div>
      </div>
    )}
  </div>
);

const OpenPositionsTable = ({ positions, onCloseTrade }) => {
  if (positions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center">
        <AlertCircle size={48} className="text-text-muted mb-4 opacity-20" />
        <h3 className="text-lg font-bold text-text mb-2">No Open Positions</h3>
        <p className="text-text-muted max-w-xs">Your active trades will appear here. Add trades from the screening results to track them.</p>
      </div>
    );
  }

  return (
    <div className="bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-bg-elevated border-b border-border text-[10px] uppercase tracking-widest text-text-muted font-black">
              <th className="text-left p-4">Symbol</th>
              <th className="text-left p-4">Entry Date</th>
              <th className="text-right p-4">Entry Price</th>
              <th className="text-right p-4">Current Price</th>
              <th className="text-right p-4">P&L (%)</th>
              <th className="text-center p-4">Targets</th>
              <th className="text-right p-4">Action</th>
            </tr>
          </thead>
          <tbody className="text-sm">
            {positions.map((pos) => {
              const pnlPct = pos.unrealised_pct || 0;
              const pnlColor = pnlPct >= 0 ? 'text-bullish' : 'text-bearish';
              
              // Calculate distance to target/SL for visual feedback
              const toTarget = pos.target ? ((pos.target - pos.current_price) / pos.current_price * 100) : null;
              const toStop = pos.stop_loss ? ((pos.current_price - pos.stop_loss) / pos.current_price * 100) : null;

              return (
                <tr key={pos.id} className="border-b border-border/50 hover:bg-bg-elevated/30 transition-colors group">
                  <td className="p-4">
                    <div className="font-black text-text tracking-tight group-hover:text-primary transition-colors">{pos.symbol}</div>
                    <div className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">Day {pos.holding_days} Holding</div>
                  </td>
                  <td className="p-4 text-text-muted font-medium">{new Date(pos.entry_date).toLocaleDateString()}</td>
                  <td className="p-4 text-right font-mono font-bold text-text-muted">₹{pos.entry_price?.toLocaleString()}</td>
                  <td className="p-4 text-right font-mono font-black text-text">₹{pos.current_price?.toLocaleString()}</td>
                  <td className={`p-4 text-right font-black ${pnlColor}`}>
                    {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                  </td>
                  <td className="p-4">
                    <div className="flex flex-col gap-1 max-w-[120px] mx-auto">
                      <div className="flex justify-between text-[9px] font-black uppercase tracking-tighter">
                        <span className="text-bearish">SL: {toStop?.toFixed(1)}%</span>
                        <span className="text-bullish">TGT: {toTarget?.toFixed(1)}%</span>
                      </div>
                      <div className="h-1 bg-border rounded-full overflow-hidden flex">
                        <div 
                          className="h-full bg-bearish opacity-30" 
                          style={{ width: `${Math.max(0, Math.min(100, (100 - (toStop || 0) * 10)))}%` }}
                        ></div>
                      </div>
                    </div>
                  </td>
                  <td className="p-4 text-right">
                    <button 
                      onClick={() => onCloseTrade(pos)}
                      className="px-4 py-1.5 bg-bg-elevated hover:bg-primary hover:text-white border border-border rounded-lg text-xs font-black transition-all shadow-sm"
                    >
                      CLOSE TRADE
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const TradeHistoryTable = ({ trades }) => {
  if (trades.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-20 bg-bg-secondary border-2 border-dashed border-border rounded-3xl text-center">
        <History size={48} className="text-text-muted mb-4 opacity-20" />
        <h3 className="text-lg font-bold text-text mb-2">Empty History</h3>
        <p className="text-text-muted max-w-xs">Once you close a trade, it will appear here in your performance history.</p>
      </div>
    );
  }

  const getReasonStyles = (reason) => {
    switch(reason) {
      case 'stop_loss': return 'bg-bearish/10 text-bearish border-bearish/20';
      case 'target': return 'bg-bullish/10 text-bullish border-bullish/20';
      case 'atr_trailing_stop': return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'holding_period': return 'bg-slate-100 dark:bg-slate-800 text-text-muted border-border';
      default: return 'bg-warning/10 text-warning border-warning/20';
    }
  };

  return (
    <div className="bg-bg-secondary border border-border rounded-2xl overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-bg-elevated border-b border-border text-[10px] uppercase tracking-widest text-text-muted font-black">
              <th className="text-left p-4">Symbol</th>
              <th className="text-left p-4">Dates</th>
              <th className="text-right p-4">Entry Price</th>
              <th className="text-right p-4">Exit Price</th>
              <th className="text-right p-4">Return %</th>
              <th className="text-center p-4">Exit Reason</th>
            </tr>
          </thead>
          <tbody className="text-sm">
            {trades.map((t, idx) => {
              const pnlColor = t.return_pct >= 0 ? 'text-bullish' : 'text-bearish';
              
              return (
                <tr key={idx} className="border-b border-border/50 hover:bg-bg-elevated/30 transition-colors">
                  <td className="p-4">
                    <div className="font-black text-text tracking-tight">{t.symbol}</div>
                    <div className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">{t.holding_days}d Holding</div>
                  </td>
                  <td className="p-4">
                    <div className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">
                      {new Date(t.entry_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} → {new Date(t.exit_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </div>
                  </td>
                  <td className="p-4 text-right font-mono text-xs text-text-muted">₹{t.entry_price?.toLocaleString()}</td>
                  <td className="p-4 text-right font-mono font-black text-text">₹{t.exit_price?.toLocaleString()}</td>
                  <td className={`p-4 text-right font-black ${pnlColor}`}>
                    {t.return_pct >= 0 ? '+' : ''}{t.return_pct?.toFixed(2)}%
                  </td>
                  <td className="p-4 text-center">
                    <span className={`px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest border ${getReasonStyles(t.exit_reason)}`}>
                      {t.exit_reason?.replace(/_/g, ' ')}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Journal;
