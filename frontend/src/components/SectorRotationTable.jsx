import { useMemo } from 'react';
import { DataTable } from './ui/DataTable';
import { TrendingUp, BarChart3, Users } from 'lucide-react';

export const SectorRotationTable = ({ data, loading }) => {
  const columns = useMemo(() => [
    {
      key: 'sector',
      label: 'Sector',
      sortable: true,
      render: (val) => <span className="font-bold">{val}</span>
    },
    {
      key: 'avg_rs',
      label: 'Avg RS Percentile',
      sortable: true,
      render: (val) => (
        <div className="flex items-center gap-3">
          <div className="w-24 h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden flex shrink-0 border border-slate-200 dark:border-slate-700">
            <div 
              className="h-full rounded-full transition-all duration-1000 shadow-[0_0_8px_rgba(59,130,246,0.5)]" 
              style={{ 
                width: `${val}%`, 
                backgroundColor: val > 70 ? '#22C55E' : val > 50 ? '#3B82F6' : '#94A3B8'
              }} 
            />
          </div>
          <span className={`font-mono font-black text-sm ${val > 70 ? 'text-green-500' : val > 50 ? 'text-blue-500' : 'text-slate-500'}`}>{val?.toFixed(1)}</span>
        </div>
      )
    },
    {
      key: 'avg_momentum_3m',
      label: '3M Momentum',
      sortable: true,
      render: (val) => (
        <span className={`px-2 py-1 rounded font-mono font-black text-xs ${val >= 0 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}>
          {val >= 0 ? '+' : ''}{val?.toFixed(1)}%
        </span>
      )
    },
    {
      key: 'bullish_pct',
      label: '% Bullish',
      sortable: true,
      render: (val) => (
        <span className={`px-3 py-1 rounded-full text-[11px] font-black uppercase tracking-wider border shadow-sm ${val > 70 ? 'bg-green-500 text-white border-green-600' : val > 50 ? 'bg-blue-500 text-white border-blue-600' : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'}`}>
          {val?.toFixed(0)}%
        </span>
      )
    },
    {
      key: 'stock_count',
      label: 'Stocks',
      sortable: true,
      render: (val) => <span className="text-text-muted">{val}</span>
    }
  ], []);

  return (
    <div className="bg-bg-secondary border border-border rounded-lg shadow-sm">
      <div className="flex justify-between items-center p-4 border-b border-border">
        <div className="flex items-center gap-3">
          <BarChart3 size={20} className="text-primary" />
          <h3 className="m-0 font-bold text-lg">Sector Rotation Analysis</h3>
        </div>
        <div className="flex items-center gap-3">
            <span className="text-[12px] text-text-muted">Latest Daily Snapshot</span>
            <span className="bg-bg-elevated px-2 py-1 rounded text-xs font-bold text-text-muted border border-border">{data.length} sectors</span>
        </div>
      </div>
      
      <DataTable 
        columns={columns} 
        data={data} 
        loading={loading}
        initialSort={{ key: 'avg_rs', direction: 'desc' }}
      />
    </div>
  );
};
