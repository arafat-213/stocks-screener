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
    maxPE: ''
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
      return matchSector && matchScore && matchROE && matchPE;
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
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: '#6b7280' }}>Sector</label>
              <select 
                value={filters.sector} 
                onChange={(e) => setFilters({...filters, sector: e.target.value})}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #e5e7eb', outline: 'none' }}
              >
                {sectors.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: '#6b7280' }}>Min Entry Score ({filters.minScore})</label>
              <input 
                type="range" min="0" max="100" 
                value={filters.minScore} 
                onChange={(e) => setFilters({...filters, minScore: parseInt(e.target.value)})}
                style={{ width: '100%', accentColor: '#16a34a' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: '#6b7280' }}>Min ROE (%)</label>
              <input 
                type="number" placeholder="e.g. 15"
                value={filters.minROE}
                onChange={(e) => setFilters({...filters, minROE: e.target.value})}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #e5e7eb', outline: 'none' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', fontWeight: '600', textTransform: 'uppercase', color: '#6b7280' }}>Max P/E</label>
              <input 
                type="number" placeholder="e.g. 30"
                value={filters.maxPE}
                onChange={(e) => setFilters({...filters, maxPE: e.target.value})}
                style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #e5e7eb', outline: 'none' }}
              />
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
