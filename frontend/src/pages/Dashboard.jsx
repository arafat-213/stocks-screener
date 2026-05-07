import { useState, useEffect, useMemo } from 'react';
import { Play, Filter, ArrowUpDown, AlertCircle, LayoutGrid, List } from 'lucide-react';
import { fetchResults, fetchPipelineStatus, runScreener } from '../api/client';
import StockCard from '../components/StockCard';
import StockCardSkeleton from '../components/StockCardSkeleton';
import MarketTable, { MarketTableSkeleton } from '../components/MarketTable';
import './Dashboard.css';

const Dashboard = () => {
  const [stocks, setStocks] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Filters and Sort State
  const [confluenceFilter, setConfluenceFilter] = useState('all'); // 'all', '3', '2+'
  const [selectedSectors, setSelectedSectors] = useState([]);
  const [sortBy, setSortBy] = useState('confluence'); // 'confluence', 'score', 'rsi', 'pe'
  const [viewMode, setViewMode] = useState('table'); // 'grid', 'table'

  const fetchData = async () => {
    try {
      const [resultsRes, statusRes] = await Promise.all([
        fetchResults(),
        fetchPipelineStatus()
      ]);
      setStocks(resultsRes.data);
      setPipeline(statusRes.data);
      setLoading(false);
    } catch (err) {
      console.error("Failed to fetch dashboard data:", err);
      setError("Failed to load dashboard. Please try again.");
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000); // Poll every 15s
    return () => clearInterval(interval);
  }, []);

  const handleRunPipeline = async () => {
    try {
      await runScreener();
      fetchData();
    } catch (err) {
      console.error("Failed to run pipeline:", err);
    }
  };

  // Derived: Available Sectors (only from current stocks)
  const availableSectors = useMemo(() => {
    const sectors = new Set(stocks.map(s => s.sector).filter(Boolean));
    return Array.from(sectors).sort();
  }, [stocks]);

  // Client-side Filtering and Sorting
  const filteredStocks = useMemo(() => {
    return stocks
      .filter(stock => {
        // Confluence Filter
        if (confluenceFilter === '3') return stock.confluence_count === 3;
        if (confluenceFilter === '2+') return stock.confluence_count >= 2;
        return true;
      })
      .filter(stock => {
        // Sector Filter
        if (selectedSectors.length === 0) return true;
        return selectedSectors.includes(stock.sector);
      })
      .sort((a, b) => {
        // Sorting Logic
        if (sortBy === 'confluence') {
          if (b.confluence_count !== a.confluence_count) return b.confluence_count - a.confluence_count;
          return (b.timeframes?.D?.score || 0) - (a.timeframes?.D?.score || 0);
        }
        if (sortBy === 'score') return (b.timeframes?.D?.score || 0) - (a.timeframes?.D?.score || 0);
        if (sortBy === 'rsi') return (a.timeframes?.D?.rsi || 0) - (b.timeframes?.D?.rsi || 0); // Low RSI first
        if (sortBy === 'pe') {
          const peA = a.fundamentals?.pe || 999;
          const peB = b.fundamentals?.pe || 999;
          return peA - peB;
        }
        return 0;
      });
  }, [stocks, confluenceFilter, selectedSectors, sortBy]);

  const toggleSector = (sector) => {
    setSelectedSectors(prev => 
      prev.includes(sector) ? prev.filter(s => s !== sector) : [...prev, sector]
    );
  };

  const resetFilters = () => {
    setConfluenceFilter('all');
    setSelectedSectors([]);
  };

  if (loading) {
    return (
      <div className="dashboard-page">
        <main className="dashboard-content">
          <div className="summary-bar">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="summary-item">
                <div className="skeleton-line" style={{ height: '40px' }}></div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: '32px' }}>
            {viewMode === 'grid' ? (
              <div className="stock-grid">
                {[1, 2, 3, 4, 5, 6].map(i => <StockCardSkeleton key={i} />)}
              </div>
            ) : (
              <MarketTableSkeleton rows={10} />
            )}
          </div>
        </main>
      </div>
    );
  }

  if (pipeline?.status === 'never_run') {
    return (
      <div className="empty-state">
        <AlertCircle size={64} />
        <h1>No Data Available</h1>
        <p>The pipeline hasn't been run yet. Start it to see market analysis.</p>
        <button className="primary-button" onClick={handleRunPipeline}>
          <Play size={20} /> Run Initial Pipeline
        </button>
      </div>
    );
  }

  const market = pipeline?.market_context?.[0] || {};
  const isMarketUp = market.change_pct >= 0;

  return (
    <div className="dashboard-page">
      {/* Main Content */}
      <main className="dashboard-content">
        <header className="dashboard-header">
          <div className="summary-bar">
            <div className="summary-item">
              <span className="label">Total Scored</span>
              <span className="value">{stocks.length}</span>
            </div>
            <div className="summary-item">
              <span className="label">3/3 Confluence</span>
              <span className="value success">{stocks.filter(s => s.confluence_count === 3).length}</span>
            </div>
            <div className="summary-item market">
              <span className="label">Nifty 50</span>
              <span className={`value ${isMarketUp ? 'success' : 'danger'}`}>
                {market.close?.toLocaleString('en-IN')} 
                <small>({isMarketUp ? '▲' : '▼'} {Math.abs(market.change_pct)?.toFixed(2)}%)</small>
              </span>
            </div>
            <div className="summary-item timestamp">
              <span className="label">Last Updated</span>
              <span className="value">{new Date(pipeline?.scored_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          </div>

          <div className="filters-container card" style={{ padding: '20px', marginBottom: '24px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '32px', alignItems: 'flex-start' }}>
              <div className="filter-group">
                <div className="filter-header" style={{ marginBottom: '12px' }}>
                  <Filter size={16} style={{ marginRight: '8px', display: 'inline' }} />
                  <h3 style={{ display: 'inline', fontSize: '14px' }}>Confluence</h3>
                </div>
                <div className="radio-group" style={{ flexDirection: 'row', gap: '8px' }}>
                  {['all', '3', '2+'].map(c => (
                    <label key={c} className={`radio-label ${confluenceFilter === c ? 'active' : ''}`} style={{ border: '1px solid var(--color-border)' }}>
                      <input 
                        type="radio" 
                        name="confluence" 
                        value={c} 
                        checked={confluenceFilter === c}
                        onChange={(e) => setConfluenceFilter(e.target.value)}
                      />
                      {c === 'all' ? 'All Stocks' : c === '3' ? '3/3 Only' : '2/3+'}
                    </label>
                  ))}
                </div>
              </div>

              <div className="filter-group sectors" style={{ flex: 1, minWidth: '300px' }}>
                <div className="filter-header" style={{ marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '14px' }}>Sectors <span className="count" style={{ marginLeft: '8px' }}>{availableSectors.length}</span></h3>
                </div>
                <div className="checkbox-list" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: '8px', maxHeight: 'none' }}>
                  {availableSectors.map(sector => (
                    <label key={sector} className={`checkbox-label ${selectedSectors.includes(sector) ? 'active' : ''}`} style={{ padding: '4px 12px', borderRadius: '20px', border: '1px solid var(--color-border)', fontSize: '12px' }}>
                      <input 
                        type="checkbox" 
                        checked={selectedSectors.includes(sector)}
                        onChange={() => toggleSector(sector)}
                        style={{ display: 'none' }}
                      />
                      <span>{sector}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="action-bar">
            <h2>Market Screener</h2>
            <div style={{ display: 'flex', gap: '12px' }}>
              <div className="view-toggle sort-controls">
                <button 
                  className={`toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
                  onClick={() => setViewMode('table')}
                  title="Table View"
                  style={{ background: 'none', border: 'none', padding: '4px', cursor: 'pointer', display: 'flex', color: viewMode === 'table' ? 'var(--color-bullish)' : 'inherit' }}
                >
                  <List size={20} />
                </button>
                <button 
                  className={`toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
                  onClick={() => setViewMode('grid')}
                  title="Grid View"
                  style={{ background: 'none', border: 'none', padding: '4px', cursor: 'pointer', display: 'flex', color: viewMode === 'grid' ? 'var(--color-bullish)' : 'inherit' }}
                >
                  <LayoutGrid size={20} />
                </button>
              </div>
              <div className="sort-controls">
                <ArrowUpDown size={16} />
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                  <option value="confluence">Confluence</option>
                  <option value="score">Daily Score</option>
                  <option value="rsi">Low RSI</option>
                  <option value="pe">Value (P/E)</option>
                </select>
              </div>
            </div>
          </div>
        </header>

        {filteredStocks.length > 0 ? (
          viewMode === 'grid' ? (
            <div className="stock-grid">
              {filteredStocks.map(stock => (
                <StockCard key={stock.symbol} stock={stock} />
              ))}
            </div>
          ) : (
            <MarketTable stocks={filteredStocks} />
          )
        ) : (
          <div className="no-results">
            <Filter size={48} />
            <h3>No stocks match filters</h3>
            <p>Try adjusting your confluence or sector selections.</p>
            <button onClick={resetFilters} className="text-button">Reset All Filters</button>
          </div>
        )}
      </main>
    </div>
  );
};

export default Dashboard;

