import { useState, useEffect, useMemo } from 'react';
import { 
  Search, 
  RefreshCw, 
  Loader2, 
  Target
} from 'lucide-react';
import { 
  fetchResults, 
  getScreensList, 
  getScreenBySlug 
} from '../api/client';
import ScreenCard from '../components/ScreenCard';
import ScreenResultTable from '../components/ScreenResultTable';
import Select from '../components/ui/Select';
import Slider from '../components/ui/Slider';
import './Dashboard.css'; // Will refactor this to a shared page CSS later

const Discover = () => {
  const [activeTab, setActiveTab] = useState('strategies'); // 'strategies' | 'interactive'
  
  // Strategies State
  const [screens, setScreens] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [strategyResults, setStrategyResults] = useState([]);
  const [loadingScreens, setLoadingScreens] = useState(true);
  const [loadingStrategyResults, setLoadingStrategyResults] = useState(false);
  const [liveMode, setLiveMode] = useState(false);
  
  // Interactive State
  const [stocks, setStocks] = useState([]);
  const [loadingStocks, setLoadingStocks] = useState(true);
  const [interactiveFilters, setInteractiveFilters] = useState({
    sector: 'All',
    minScore: 0,
    minROE: '',
    maxPE: '',
    minRS: 0,
    capCategory: 'All'
  });
  const [sortConfig] = useState({ key: 'confluence_count', direction: 'desc' });

  // Fetch Screens List
  useEffect(() => {
    const fetchScreens = async () => {
      try {
        const res = await getScreensList();
        setScreens(res.data);
        if (res.data.length > 0) setSelectedSlug(res.data[0].slug);
      } catch (err) {
        console.error('Failed to load screens:', err);
      } finally {
        setLoadingScreens(false);
      }
    };
    fetchScreens();
  }, []);

  // Fetch Strategy Results
  useEffect(() => {
    if (!selectedSlug || activeTab !== 'strategies') return;
    
    const fetchResults = async () => {
      setLoadingStrategyResults(true);
      try {
        const res = await getScreenBySlug(selectedSlug, liveMode);
        setStrategyResults(res.data);
      } catch (e) {
        setStrategyResults([]);
      } finally {
        setLoadingStrategyResults(false);
      }
    };
    
    fetchResults();
  }, [selectedSlug, liveMode, activeTab]);

  // Fetch All Stocks for Interactive
  useEffect(() => {
    if (activeTab !== 'interactive') return;
    
    const loadData = async () => {
      setLoadingStocks(true);
      try {
        const response = await fetchResults();
        setStocks(response.data);
      } catch (error) {
        console.error('Error fetching interactive results:', error);
      } finally {
        setLoadingStocks(false);
      }
    };
    loadData();
  }, [activeTab]);

  // Interactive Filter Logic
  const filteredStocks = useMemo(() => {
    return stocks.filter(stock => {
      const matchSector = interactiveFilters.sector === 'All' || stock.sector === interactiveFilters.sector;
      const matchScore = (stock.timeframes?.D?.score || 0) >= interactiveFilters.minScore;
      const matchROE = !interactiveFilters.minROE || (stock.fundamentals?.roe || 0) >= parseFloat(interactiveFilters.minROE);
      const matchPE = !interactiveFilters.maxPE || (stock.fundamentals?.pe || 9999) <= parseFloat(interactiveFilters.maxPE);
      const matchRS = (stock.timeframes?.D?.rs_score ?? 0) >= interactiveFilters.minRS;
      const matchCap = interactiveFilters.capCategory === 'All' || (stock.fundamentals?.market_cap_category || '').toLowerCase() === interactiveFilters.capCategory.toLowerCase();
      
      return matchSector && matchScore && matchROE && matchPE && matchRS && matchCap;
    });
  }, [stocks, interactiveFilters]);

  const sortedStocks = useMemo(() => {
    const sortableItems = [...filteredStocks];
    if (sortConfig.key) {
      sortableItems.sort((a, b) => {
        let aValue, bValue;
        if (sortConfig.key === 'score') {
          aValue = a.timeframes?.D?.score || 0;
          bValue = b.timeframes?.D?.score || 0;
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

  const sectors = useMemo(() => {
    const s = new Set(stocks.map(stock => stock.sector).filter(Boolean));
    return ['All', ...Array.from(s).sort()];
  }, [stocks]);

  return (
    <div className="discover-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Discovery</h1>
          <p className="text-muted">Explore strategies or create your own market screens.</p>
        </div>
        
        <div className="tabs-container card">
          <button 
            className={`tab-btn ${activeTab === 'strategies' ? 'active' : ''}`}
            onClick={() => setActiveTab('strategies')}
          >
            <Target size={18} />
            <span>Strategies</span>
          </button>
          <button 
            className={`tab-btn ${activeTab === 'interactive' ? 'active' : ''}`}
            onClick={() => setActiveTab('interactive')}
          >
            <Search size={18} />
            <span>Interactive</span>
          </button>
        </div>
      </header>

      {activeTab === 'strategies' ? (
        <section className="strategies-tab">
          <div className="stock-grid" style={{ marginBottom: '32px' }}>
            {loadingScreens ? (
              [...Array(3)].map((_, i) => (
                <div key={i} className="card skeleton-card" style={{ height: '140px' }} />
              ))
            ) : (
              screens.map(screen => (
                <ScreenCard
                  key={screen.slug}
                  screen={screen}
                  isSelected={selectedSlug === screen.slug}
                  onClick={() => setSelectedSlug(screen.slug)}
                />
              ))
            )}
          </div>

          {selectedSlug && (
            <div className="card results-card">
              <div className="card-header">
                <h3>
                  {screens.find(s => s.slug === selectedSlug)?.label}
                  <span className="count-badge">{strategyResults.length} hits</span>
                </h3>
                <button 
                  onClick={() => setLiveMode(!liveMode)}
                  className={`live-toggle ${liveMode ? 'active' : ''}`}
                >
                  <RefreshCw size={14} className={loadingStrategyResults ? "animate-spin" : ""} />
                  Live Mode
                </button>
              </div>
              <ScreenResultTable 
                results={strategyResults} 
                slug={selectedSlug} 
                loading={loadingStrategyResults} 
              />
            </div>
          )}
        </section>
      ) : (
        <section className="interactive-tab">
          <div className="card filter-panel" style={{ marginBottom: '24px', padding: '24px' }}>
            <div className="filter-grid">
              <Select 
                label="Sector"
                value={interactiveFilters.sector}
                onChange={(val) => setInteractiveFilters({...interactiveFilters, sector: val})}
                options={sectors.map(s => ({ value: s, label: s }))}
              />
              <Select 
                label="Market Cap"
                value={interactiveFilters.capCategory}
                onChange={(val) => setInteractiveFilters({...interactiveFilters, capCategory: val})}
                options={[
                  { value: 'All', label: 'All Categories' },
                  { value: 'Largecap', label: 'Large Cap' },
                  { value: 'Midcap', label: 'Mid Cap' },
                  { value: 'Smallcap', label: 'Small Cap' }
                ]}
              />
              <Slider 
                label="Min Score"
                value={interactiveFilters.minScore}
                onChange={(val) => setInteractiveFilters({...interactiveFilters, minScore: val})}
                min={0}
                max={100}
              />
              <div className="filter-item">
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>Max P/E</label>
                <input 
                  type="number" placeholder="e.g. 30"
                  value={interactiveFilters.maxPE}
                  onChange={(e) => setInteractiveFilters({...interactiveFilters, maxPE: e.target.value})}
                  className="custom-number-input"
                  style={{ width: '100%', padding: '10px 14px', background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontSize: '0.9rem' }}
                />
              </div>
            </div>
          </div>

          <div className="card results-card">
            {loadingStocks ? (
              <div className="loading-state">
                <Loader2 className="animate-spin" size={32} />
                <p>Analyzing market...</p>
              </div>
            ) : (
              <ScreenResultTable 
                results={sortedStocks} 
                loading={false} 
              />
            )}
          </div>
        </section>
      )}
    </div>
  );
};

export default Discover;
