import React, { useState, useEffect, useMemo } from 'react';
import { Play, Activity, Filter, ArrowUpDown, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { fetchResults, fetchPipelineStatus, runScreener } from '../api/client';
import StockCard from '../components/StockCard';
import StockCardSkeleton from '../components/StockCardSkeleton';
import './Dashboard.css';

const Dashboard = () => {
  const [stocks, setStocks] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Filters and Sort State
  const [confluenceFilter, setConfluenceFilter] = useState('all'); // 'all', '3', '2+'
  const [selectedSectors, setSelectedSectors] = useState([]);
  const [sortBy, setSortBy] = useState('confluence'); // 'confluence', 'score', 'rsi', 'pe'

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
      <div className="dashboard-layout">
        <aside className="dashboard-sidebar">
          <div className="brand">
            <Activity color="#16a34a" size={28} />
            <h1>Stock AI</h1>
          </div>
          <div className="funnel-stats">
            <div className="skeleton-line" style={{ height: '100px', borderRadius: '12px' }}></div>
          </div>
        </aside>
        <main className="dashboard-main">
          <div className="summary-bar">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="summary-item">
                <div className="skeleton-line" style={{ height: '40px' }}></div>
              </div>
            ))}
          </div>
          <div className="stock-grid" style={{ marginTop: '32px' }}>
            {[1, 2, 3, 4, 5, 6].map(i => <StockCardSkeleton key={i} />)}
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
    <div className="dashboard-layout">
      {/* Sidebar */}
      <aside className="dashboard-sidebar">
        <div className="brand">
          <Activity color="#16a34a" size={28} />
          <h1>Stock AI</h1>
        </div>

        <div className="funnel-stats">
          <h3>Pipeline Health</h3>
          <div className="stat-row">
            <span>Fetched</span>
            <span className="stat-val">{pipeline?.stocks_fetched || 0}</span>
          </div>
          <div className="stat-row">
            <span>Tier 1 (Filters)</span>
            <span className="stat-val">{pipeline?.tier1_count || 0}</span>
          </div>
          <div className="stat-row">
            <span>Tier 2 (Cache)</span>
            <span className="stat-val">{pipeline?.tier2_count || 0}</span>
          </div>
          <div className="stat-row highlight">
            <span>Scored</span>
            <span className="stat-val">{pipeline?.stocks_scored || 0}</span>
          </div>
        </div>

        <div className="filter-group">
          <div className="filter-header">
            <Filter size={16} />
            <h3>Confluence</h3>
          </div>
          <div className="radio-group">
            {['all', '3', '2+'].map(c => (
              <label key={c} className={`radio-label ${confluenceFilter === c ? 'active' : ''}`}>
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

        <div className="filter-group sectors">
          <div className="filter-header">
            <h3>Sectors</h3>
            <span className="count">{availableSectors.length}</span>
          </div>
          <div className="checkbox-list">
            {availableSectors.map(sector => (
              <label key={sector} className="checkbox-label">
                <input 
                  type="checkbox" 
                  checked={selectedSectors.includes(sector)}
                  onChange={() => toggleSector(sector)}
                />
                <span>{sector}</span>
              </label>
            ))}
          </div>
        </div>

        <button 
          className="pipeline-btn" 
          onClick={handleRunPipeline}
          disabled={pipeline?.status === 'running'}
        >
          {pipeline?.status === 'running' ? (
            <><Loader2 className="animate-spin" size={18} /> Running...</>
          ) : (
            <><Play size={18} /> Run Pipeline</>
          )}
        </button>
      </aside>

      {/* Main Content */}
      <main className="dashboard-main">
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

          <div className="action-bar">
            <h2>Market Screener</h2>
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
        </header>

        {filteredStocks.length > 0 ? (
          <div className="stock-grid">
            {filteredStocks.map(stock => (
              <StockCard key={stock.symbol} stock={stock} />
            ))}
          </div>
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
