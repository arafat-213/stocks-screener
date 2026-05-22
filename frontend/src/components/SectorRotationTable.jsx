import { useMemo } from 'react';
import { DataTable } from './ui/DataTable';
import { TrendingUp, BarChart3, Users } from 'lucide-react';

export const SectorRotationTable = ({ data, loading }) => {
  const columns = useMemo(() => [
    {
      key: 'sector',
      label: 'Sector',
      sortable: true,
      render: (val) => <span className="bold">{val}</span>
    },
    {
      key: 'avg_rs',
      label: 'Avg RS Percentile',
      sortable: true,
      render: (val) => (
        <div className="flex-center-gap-8">
          <div className="rs-bar-bg" style={{ width: '80px', height: '8px', background: 'var(--color-bg-elevated)', borderRadius: '4px', overflow: 'hidden' }}>
            <div 
              className="rs-bar-fill" 
              style={{ 
                width: `${val}%`, 
                height: '100%', 
                background: val > 70 ? 'var(--color-bullish)' : val > 50 ? 'var(--color-primary)' : 'var(--color-neutral)'
              }} 
            />
          </div>
          <span className="mono bold">{val?.toFixed(1)}</span>
        </div>
      )
    },
    {
      key: 'avg_momentum_3m',
      label: '3M Momentum',
      sortable: true,
      render: (val) => (
        <span className={val >= 0 ? 'text-positive mono' : 'text-negative mono'}>
          {val >= 0 ? '+' : ''}{val?.toFixed(1)}%
        </span>
      )
    },
    {
      key: 'bullish_pct',
      label: '% Bullish',
      sortable: true,
      render: (val) => (
        <span className={`status-badge ${val > 50 ? 'bullish' : 'neutral'}`}>
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
    <div className="bg-bg-secondary border border-border rounded-lg shadow-sm results-card">
      <div className="card-header">
        <div className="report-header-flex">
          <BarChart3 size={20} className="text-primary" />
          <h3 className="m-0">Sector Rotation Analysis</h3>
        </div>
        <div className="flex-center-gap-12">
            <span className="fs-12 text-text-muted">Latest Daily Snapshot</span>
            <span className="count-badge">{data.length} sectors</span>
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
