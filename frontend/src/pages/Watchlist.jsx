import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { 
  getWatchlist, 
  updateWatchlistStatus, 
  removeFromWatchlist 
} from '../api/client';
import { DataTable } from '../components/ui/DataTable';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { 
  CheckCircle, 
  XCircle, 
  Clock, 
  TrendingUp, 
  ShieldCheck, 
  ShieldX, 
  CircleAlert,
  Trash2
} from 'lucide-react';
import SetupBadge from '../components/SetupBadge';

const Watchlist = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchWatchlistData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getWatchlist();
      setItems(data || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch watchlist');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWatchlistData();
  }, [fetchWatchlistData]);

  const handleStatusUpdate = async (symbol, status) => {
    try {
      await updateWatchlistStatus(symbol, status);
      // Update local state or refetch
      setItems(prev => prev.map(item => 
        item.symbol === symbol ? { ...item, status } : item
      ));
    } catch (err) {
      alert(`Failed to update status: ${err.message}`);
    }
  };

  const handleDelete = async (symbol) => {
    if (!window.confirm(`Remove ${symbol} from watchlist?`)) return;
    try {
      await removeFromWatchlist(symbol);
      setItems(prev => prev.filter(item => item.symbol !== symbol));
    } catch (err) {
      alert(`Failed to remove: ${err.message}`);
    }
  };

  const columns = [
    { 
      key: 'symbol', 
      label: 'Symbol', 
      sortable: true,
      render: (val) => (
        <Link to={`/stocks/${val}`} className="text-blue-600 dark:text-blue-400 font-black no-underline hover:underline transition-all tracking-tighter">
          {val.replace('.NS', '')}
        </Link>
      )
    },
    { 
      key: 'signal_date', 
      label: 'Signal Date', 
      sortable: true,
      render: (val) => new Date(val).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    },
    {
      key: 'days_elapsed',
      label: 'Days',
      sortable: true,
      accessor: (row) => {
        const signal = new Date(row.signal_date);
        const today = new Date();
        const diff = Math.floor((today - signal) / (1000 * 60 * 60 * 24));
        return diff;
      },
      render: (val) => (
        <div className="flex items-center gap-1.5">
          <Clock size={14} className={val > 5 ? 'text-amber-500' : 'text-slate-400'} />
          <span className={val > 8 ? 'text-red-500 font-black' : ''}>{val}d</span>
        </div>
      )
    },
    {
      key: 'quality',
      label: 'Quality',
      sortable: true,
      accessor: (row) => row.quality_tier || '',
      render: (val) => (
        <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${
          val === 'A' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
          val === 'B' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
          'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
        }`}>
          Tier {val || 'C'}
        </span>
      )
    },
    {
      key: 'entry_zone',
      label: 'Entry Zone',
      render: (_, row) => {
        if (!row.planned_entry_low || !row.planned_entry_high) return '-';
        return (
            <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-slate-500 uppercase font-bold tracking-tighter">₹{row.planned_entry_low.toFixed(1)} - ₹{row.planned_entry_high.toFixed(1)}</span>
                <div className="h-1.5 w-20 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 w-1/2" />
                </div>
            </div>
        );
      }
    },
    {
      key: 'live_price',
      label: 'Live vs EMA20',
      render: (_, row) => {
        const price = row.live_price || row.close_price;
        const ema20 = row.ema20_at_signal; // Ideally should be live EMA20
        if (!price || !ema20) return '-';
        const diff = ((price - ema20) / ema20) * 100;
        return (
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-xs">₹{price.toLocaleString('en-IN')}</span>
            <span className={`text-[10px] font-bold ${diff < 1 ? 'text-green-600' : 'text-slate-500'}`}>
              {diff > 0 ? '+' : ''}{diff.toFixed(2)}% vs EMA
            </span>
          </div>
        );
      }
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (val) => (
        <span className={`text-[10px] font-black uppercase px-2 py-1 rounded-full ${
            val === 'watching' ? 'bg-blue-100 text-blue-700' :
            val === 'entered' ? 'bg-green-100 text-green-700' :
            val === 'skipped' ? 'bg-slate-100 text-slate-700' :
            'bg-red-100 text-red-700'
        }`}>
            {val}
        </span>
      )
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (_, row) => (
        <div className="flex gap-2">
          {row.status === 'watching' && (
            <>
              <button 
                onClick={() => handleStatusUpdate(row.symbol, 'entered')}
                className="p-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
                title="Enter Trade"
              >
                <TrendingUp size={16} />
              </button>
              <button 
                onClick={() => handleStatusUpdate(row.symbol, 'skipped')}
                className="p-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 transition-colors"
                title="Skip/Dismiss"
              >
                <XCircle size={16} />
              </button>
            </>
          )}
          <button 
            onClick={() => handleDelete(row.symbol)}
            className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
            title="Remove"
          >
            <Trash2 size={16} />
          </button>
        </div>
      )
    }
  ];

  return (
    <div className="w-full animate-fade-in">
      {error && <ErrorBanner message={error} />}

      <header className="mb-10">
        <h1 className="text-3xl sm:text-4xl font-black tracking-tighter mb-1 uppercase">Watchlist</h1>
        <p className="text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-[10px]">Active setups awaiting entry or monitoring.</p>
      </header>

      <div className="flex flex-col gap-6">
        <DataTable 
          columns={columns} 
          data={items} 
          loading={loading}
          initialSort={{ key: 'signal_date', direction: 'desc' }}
        />
        
        {items.length === 0 && !loading && (
          <div className="bg-bg-secondary p-20 rounded-3xl border-2 border-dashed border-border flex flex-col items-center justify-center text-center">
            <div className="bg-slate-100 dark:bg-slate-800 p-4 rounded-full mb-4">
              <Clock size={32} className="text-slate-400" />
            </div>
            <h3 className="text-lg font-black uppercase tracking-tight">Watchlist is Empty</h3>
            <p className="text-text-muted text-sm mt-1 max-w-xs">Add stocks from the dashboard to track them for high-probability entries.</p>
            <Link to="/" className="mt-6 px-6 py-3 bg-blue-600 text-white rounded-xl font-black uppercase text-xs tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-500/20">
              Go to Dashboard
            </Link>
          </div>
        )}
      </div>
    </div>
  );
};

export default Watchlist;
