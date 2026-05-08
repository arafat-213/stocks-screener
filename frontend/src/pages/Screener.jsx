import { useState, useEffect, useMemo } from 'react';
import { Activity, Loader2, Filter, ArrowUpDown } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fetchResults } from '../api/client';
import './Dashboard.css';

const Screener = () => {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    sector: 'All',
    minScore: 0,
    minROE: '',
    maxPE: '',
    minRS: 0,
    minMom3m: '',
    minADX: '',
    capCategory: 'All'
  });
  const [sortConfig, setSortConfig] = useState({ key: 'confluence_count', direction: 'desc' });

  useEffect(() => {
    const loadData = async () => {
      try {
        const response = await fetchResults();
        setStocks(response.data);
      } catch (error) {
        console.error('Error fetching screener results:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const sectors = useMemo(() => {
    const s = new Set(stocks.map(stock => stock.sector).filter(Boolean));
    return ['All', ...Array.from(s).sort()];
  }, [stocks]);

  const filteredStocks = useMemo(() => {
    return stocks.filter(stock => {
      const matchSector = filters.sector === 'All' || stock.sector === filters.sector;
      const matchScore = (stock.timeframes?.D?.score || 0) >= filters.minScore;
      const matchROE = !filters.minROE || (stock.fundamentals?.roe || 0) >= parseFloat(filters.minROE);
      const matchPE = !filters.maxPE || (stock.fundamentals?.pe || 9999) <= parseFloat(filters.maxPE);
      
      const matchRS = (stock.timeframes?.D?.rs_score ?? 0) >= filters.minRS;
      const matchMom = !filters.minMom3m || (stock.timeframes?.D?.momentum_3m ?? -999) >= parseFloat(filters.minMom3m);
      const matchADX = !filters.minADX || (stock.timeframes?.D?.adx ?? 0) >= parseFloat(filters.minADX);
      const matchCap = filters.capCategory === 'All' || (stock.fundamentals?.market_cap_category || '').toLowerCase() === filters.capCategory.toLowerCase();
      
      return matchSector && matchScore && matchROE && matchPE && matchRS && matchMom && matchADX && matchCap;
    });
  }, [stocks, filters]);

  const sortedStocks = useMemo(() => {
    const sortableItems = [...filteredStocks];
    if (sortConfig.key) {
      sortableItems.sort((a, b) => {
        let aValue, bValue;
        if (sortConfig.key === 'score') {
          aValue = a.timeframes?.D?.score || 0;
          bValue = b.timeframes?.D?.score || 0;
        } else if (sortConfig.key === 'roe') {
          aValue = a.fundamentals?.roe || 0;
          bValue = b.fundamentals?.roe || 0;
        } else if (sortConfig.key === 'pe') {
          aValue = a.fundamentals?.pe || 9999;
          bValue = b.fundamentals?.pe || 9999;
        } else if (sortConfig.key === 'rs_score') {
          aValue = a.timeframes?.D?.rs_score || 0;
          bValue = b.timeframes?.D?.rs_score || 0;
        } else if (sortConfig.key === 'momentum_3m') {
          aValue = a.timeframes?.D?.momentum_3m || -999;
          bValue = b.timeframes?.D?.momentum_3m || -999;
        } else if (sortConfig.key === 'adx') {
          aValue = a.timeframes?.D?.adx || 0;
          bValue = b.timeframes?.D?.adx || 0;
        } else {
          aValue = a[sortConfig.key];
          bValue = b[sortConfig.key];
        }

        if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return sortableItems;
  }, [filteredStocks, sortConfig]);

  const handleSort = (key) => {
    let direction = 'desc';
    if (sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc';
    }
    setSortConfig({ key, direction });
  };

  return (
    <div className="screener-page">
      {/* Main Content */}
      <main className="screener-content">
        <header className="screener-header" style={{ marginBottom: '24px' }}>
          <div className="action-bar">
            <h2>Interactive Screener</h2>
          </div>
        </header>

        {/* Filter Bar */}
        <div className="card" style={{ marginBottom: '24px', padding: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '24px' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Sector</label>
              <select 
                value={filters.sector} 
                onChange={(e) => setFilters({...filters, sector: e.target.value})}
                style={{ width: '100%' }}
              >
                {sectors.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Min Entry Score ({filters.minScore})</label>
              <input 
                type="range" min="0" max="100" 
                value={filters.minScore} 
                onChange={(e) => setFilters({...filters, minScore: parseInt(e.target.value)})}
                style={{ width: '100%' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Min ROE (%)</label>
              <input 
                type="number" placeholder="e.g. 15"
                value={filters.minROE}
                onChange={(e) => setFilters({...filters, minROE: e.target.value})}
                style={{ width: '100%' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Max P/E</label>
              <input 
                type="number" placeholder="e.g. 30"
                value={filters.maxPE}
                onChange={(e) => setFilters({...filters, maxPE: e.target.value})}
                style={{ width: '100%' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Min RS Score ({filters.minRS})</label>
              <input 
                type="range" min="0" max="100" 
                value={filters.minRS} 
                onChange={(e) => setFilters({...filters, minRS: parseInt(e.target.value)})}
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Min Mom 3M %</label>
              <input 
                type="number" placeholder="e.g. 10"
                value={filters.minMom3m}
                onChange={(e) => setFilters({...filters, minMom3m: e.target.value})}
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>ADX ≥</label>
              <input 
                type="number" placeholder="e.g. 20"
                value={filters.minADX}
                onChange={(e) => setFilters({...filters, minADX: e.target.value})}
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Cap Category</label>
              <select 
                value={filters.capCategory} 
                onChange={(e) => setFilters({...filters, capCategory: e.target.value})}
                style={{ width: '100%' }}
              >
                <option value="All">All</option>
                <option value="Largecap">Largecap</option>
                <option value="Midcap">Midcap</option>
                <option value="Smallcap">Smallcap</option>
              </select>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="dashboard-loading">
            <Loader2 className="animate-spin" size={40} />
            <p>Loading screened stocks...</p>
          </div>
        ) : (
          <div className="table-container">
            <table className="stocks-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort('symbol')} style={{ cursor: 'pointer' }}>Symbol <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('sector')} style={{ cursor: 'pointer' }}>Sector <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('confluence_count')} style={{ cursor: 'pointer' }}>Confluence <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('score')} style={{ cursor: 'pointer' }}>Daily Score <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('roe')} style={{ cursor: 'pointer' }}>ROE <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('pe')} style={{ cursor: 'pointer' }}>P/E <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('rs_score')} style={{ cursor: 'pointer' }}>RS <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('momentum_3m')} style={{ cursor: 'pointer' }}>Mom 3M <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th onClick={() => handleSort('adx')} style={{ cursor: 'pointer' }}>ADX <ArrowUpDown size={14} style={{ display: 'inline', marginLeft: '4px' }} /></th>
                  <th>{'>'}200 EMA</th>
                </tr>
              </thead>
              <tbody>
                {sortedStocks.map((stock) => (
                  <tr key={stock.symbol}>
                    <td><strong>{stock.symbol}</strong></td>
                    <td>{stock.sector}</td>
                    <td>
                      <span className={`status-badge ${stock.confluence_count >= 2 ? 'bullish' : 'neutral'}`}>
                        {stock.confluence_count}/3
                      </span>
                    </td>
                    <td>{stock.timeframes?.D?.score?.toFixed(1) || 'N/A'}</td>
                    <td>{stock.fundamentals?.roe?.toFixed(1) || 'N/A'}%</td>
                    <td>{stock.fundamentals?.pe?.toFixed(1) || 'N/A'}</td>
                    <td>{stock.timeframes?.D?.rs_score?.toFixed(0) || 'N/A'}</td>
                    <td className={stock.timeframes?.D?.momentum_3m > 0 ? 'success' : (stock.timeframes?.D?.momentum_3m < 0 ? 'danger' : '')}>
                      {stock.timeframes?.D?.momentum_3m != null ? `${stock.timeframes?.D?.momentum_3m > 0 ? '+' : ''}${stock.timeframes?.D?.momentum_3m.toFixed(1)}%` : 'N/A'}
                    </td>
                    <td>{stock.timeframes?.D?.adx?.toFixed(1) || 'N/A'}</td>
                    <td>{stock.timeframes?.D?.above_200ema ? '✓' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sortedStocks.length === 0 && (
              <div className="no-results">
                <Filter size={48} />
                <h3>No stocks match filters</h3>
                <p>Try adjusting your screening criteria.</p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default Screener;
