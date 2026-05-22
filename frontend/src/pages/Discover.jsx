import { useState, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { 
  Search, 
  RefreshCw, 
  Target
} from 'lucide-react';
import { 
  fetchResults, 
  getScreensList, 
  getScreenBySlug 
} from '../api/client';
import { useFetch } from '../hooks/useFetch';
import ScreenCard from '../components/ScreenCard';
import { DataTable } from '../components/ui/DataTable';
import Select from '../components/ui/Select';
import Slider from '../components/ui/Slider';
import { ExportButton } from '../components/ui/ExportButton';
import './Dashboard.css';

const SCREEN_COLUMNS = {
  'momentum-monsters':      ['symbol', 'name', 'rs_score', 'momentum_3m', 'adx', 'score'],
  'value-with-momentum':    ['symbol', 'name', 'peg_ratio', 'momentum_1m', 'ema_slope', 'score'],
  'near-breakout':          ['symbol', 'name', 'pct_from_resistance', 'volume_breakout', 'score'],
  '52w-high':               ['symbol', 'name', 'pct_from_52w_high', 'week52_high', 'score'],
  '52w-low':                ['symbol', 'name', 'pct_from_52w_low', 'week52_low', 'score'],
  'low-debt-midcap':        ['symbol', 'name', 'market_cap_category', 'de_ratio', 'fcf_positive', 'score'],
  'undervalued-fundamentals':['symbol', 'name', 'peg_ratio', 'ev_to_ebitda', 'dividend_yield', 'score'],
  'steady-compounders':     ['symbol', 'name', 'roce', 'dividend_consistency', 'above_200ema', 'score'],
  'ema-crossover':          ['symbol', 'name', 'ema_signal', 'adx', 'rsi', 'score'],
  'volume-surge':           ['symbol', 'name', 'volume_breakout', 'is_bullish', 'rsi', 'score'],
  'rsi-recovery':           ['symbol', 'name', 'rsi_signal', 'rsi', 'ema_slope', 'score'],
  'mtf-confluence':         ['symbol', 'name', 'confluence_count', 'rsi', 'score'],
  'fresh-breakout':         ['symbol', 'name', 'pct_from_52w_high', 'volume_breakout', 'adx', 'score'],
  'sector-leaders':         ['symbol', 'name', 'rs_score', 'sector', 'score'],
  'hot-sectors':            ['symbol', 'name', 'rs_score', 'sector', 'score'],
  'qarp':                   ['symbol', 'name', 'roce', 'roe', 'peg_ratio', 'de_ratio', 'score'],
  'dividend-growth':        ['symbol', 'name', 'dividend_yield', 'dividend_consistency', 'fcf_positive', 'score'],
  '_default':               ['symbol', 'name', 'score', 'rsi', 'confluence_count'],
};

const COLUMN_META = {
  symbol: { 
    label: 'Symbol', 
    key: 'symbol', 
    sortable: true,
    render: (v) => (
      <Link to={`/stocks/${v}`} className="symbol-link">
        {v}
      </Link>
    )
  },
  name: { label: 'Name', key: 'name', sortable: true },
  sector: { label: 'Sector', key: 'sector', sortable: true },
  score: { 
    label: 'Score', 
    key: 'score', 
    sortable: true,
    accessor: (row) => row.timeframes?.D?.score ?? row.score,
    render: (v) => v != null ? v.toFixed(1) : '—' 
  },
  rs_score: { 
    label: 'RS Score', 
    key: 'rs_score', 
    sortable: true,
    accessor: (row) => row.timeframes?.D?.rs_score ?? row.rs_score,
    render: (v) => v != null ? v.toFixed(0) : '—' 
  },
  momentum_1m: { 
    label: '1M Mom %', 
    key: 'momentum_1m', 
    sortable: true,
    render: (v) => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—' 
  },
  momentum_3m: { 
    label: '3M Mom %', 
    key: 'momentum_3m', 
    sortable: true,
    render: (v) => v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—' 
  },
  adx: { 
    label: 'ADX', 
    key: 'adx', 
    sortable: true,
    render: (v) => v != null ? v.toFixed(1) : '—' 
  },
  peg_ratio: { 
    label: 'PEG', 
    key: 'peg_ratio', 
    sortable: true,
    render: (v) => v != null ? v.toFixed(2) : '—' 
  },
  ev_to_ebitda: { 
    label: 'EV/EBITDA', 
    key: 'ev_to_ebitda', 
    sortable: true,
    render: (v) => v != null ? v.toFixed(1) : '—' 
  },
  dividend_yield: { 
    label: 'Div Yield', 
    key: 'dividend_yield', 
    sortable: true,
    render: (v) => v != null ? `${(v * 100).toFixed(2)}%` : '—' 
  },
  roce: { 
    label: 'ROCE %', 
    key: 'roce', 
    sortable: true,
    render: (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—' 
  },
  roe: { 
    label: 'ROE %', 
    key: 'roe', 
    sortable: true,
    accessor: (row) => row.indicators?.fundamental?.roe ?? row.roe,
    render: (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—' 
  },
  de_ratio: { 
    label: 'D/E', 
    key: 'de_ratio', 
    sortable: true,
    render: (v) => v != null ? v.toFixed(2) : '—' 
  },
  pct_from_52w_high: { 
    label: '% from High', 
    key: 'pct_from_52w_high', 
    sortable: true,
    render: (v) => v != null ? `${v.toFixed(1)}%` : '—' 
  },
  pct_from_52w_low: { 
    label: '% from Low', 
    key: 'pct_from_52w_low', 
    sortable: true,
    render: (v) => v != null ? `${v.toFixed(1)}%` : '—' 
  },
  week52_high: { 
    label: '52W High', 
    key: 'week52_high', 
    sortable: true,
    render: (v) => v != null ? `₹${v.toLocaleString('en-IN')}` : '—' 
  },
  week52_low: { 
    label: '52W Low', 
    key: 'week52_low', 
    sortable: true,
    render: (v) => v != null ? `₹${v.toLocaleString('en-IN')}` : '—' 
  },
  pct_from_resistance: { 
    label: '% to Break', 
    key: 'pct_from_resistance', 
    sortable: true,
    render: (v) => v != null ? `${v.toFixed(1)}%` : '—' 
  },
  volume_breakout: { 
    label: 'Vol Break', 
    key: 'volume_breakout', 
    sortable: true,
    render: (v) => v ? '✓' : '—' 
  },
  fcf_positive: { 
    label: 'FCF+', 
    key: 'fcf_positive', 
    sortable: true,
    render: (v) => v ? '✓' : '—' 
  },
  dividend_consistency: { 
    label: 'Div 3Y', 
    key: 'dividend_consistency', 
    sortable: true,
    render: (v) => v ? '✓' : '—' 
  },
  above_200ema: { 
    label: '>200 EMA', 
    key: 'above_200ema', 
    sortable: true,
    render: (v) => v ? '✓' : '—' 
  },
  market_cap_category: { label: 'Cap', key: 'market_cap_category', sortable: true },
  ema_slope: { 
    label: 'EMA Trend', 
    key: 'ema_slope', 
    sortable: true,
    render: (v) => v != null ? (v > 0 ? '↑' : '↓') : '—' 
  },
  confluence_count: { 
    label: 'Conf.', 
    key: 'confluence_count', 
    sortable: true,
    render: (v) => v != null ? `${v}/3` : '—' 
  },
  rsi: { 
    label: 'RSI', 
    key: 'rsi', 
    sortable: true,
    render: (v) => v != null ? v.toFixed(1) : '—' 
  },
  ema_signal: { 
    label: 'EMA Signal', 
    key: 'ema_signal', 
    sortable: true,
    render: (v) => v ? v.replace('_', ' ') : '—' 
  },
  rsi_signal: { 
    label: 'RSI Signal', 
    key: 'rsi_signal', 
    sortable: true,
    render: (v) => v ? v.replace('_', ' ') : '—' 
  },
  is_bullish: { 
    label: 'Bullish', 
    key: 'is_bullish', 
    sortable: true,
    render: (v) => v ? '✓' : '—' 
  },
};

const Discover = () => {
  const [activeTab, setActiveTab] = useState('strategies'); // 'strategies' | 'interactive'
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [liveMode, setLiveMode] = useState(false);
  
  const [interactiveFilters, setInteractiveFilters] = useState({
    sector: 'All',
    minScore: 0,
    minROE: '',
    maxPE: '',
    minRS: 0,
    capCategory: 'All'
  });

  // Fetch Screens List
  const { data: screens = [], loading: loadingScreens } = useFetch(getScreensList, {
    onSuccess: (data) => {
      if (data && data.length > 0 && !selectedSlug) {
        setSelectedSlug(data[0].slug);
      }
    }
  });

  // Fetch Strategy Results
  const { data: strategyResults = [], loading: loadingStrategyResults } = useFetch(
    useCallback(() => getScreenBySlug(selectedSlug, liveMode), [selectedSlug, liveMode]),
    { 
      autoFetch: !!selectedSlug && activeTab === 'strategies',
      deps: [selectedSlug, liveMode, activeTab]
    }
  );

  // Fetch All Stocks for Interactive (renamed local function to loadInteractiveData)
  const { data: stocks = [], loading: loadingStocks } = useFetch(fetchResults, {
    autoFetch: activeTab === 'interactive',
    deps: [activeTab]
  });

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

  const sectors = useMemo(() => {
    const s = new Set(stocks.map(stock => stock.sector).filter(Boolean));
    return ['All', ...Array.from(s).sort()];
  }, [stocks]);

  const getColumnsForSlug = (slug) => {
    const keys = SCREEN_COLUMNS[slug] || SCREEN_COLUMNS['_default'];
    return keys.map(key => COLUMN_META[key]);
  };

  const currentColumns = useMemo(() => getColumnsForSlug(selectedSlug), [selectedSlug]);
  const defaultColumns = useMemo(() => getColumnsForSlug('_default'), []);

  return (
    <div className="discover-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Discovery</h1>
          <p className="text-text-muted">Explore strategies or create your own market screens.</p>
        </div>
        
        <div className="tabs-container bg-bg-secondary border border-border rounded-lg shadow-sm">
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
          <div className="stock-grid mb-32">
            {loadingScreens ? (
              [...Array(3)].map((_, i) => (
                <div key={i} className="bg-bg-secondary border border-border rounded-lg shadow-sm skeleton-card skeleton-h-140" />
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
            <div className="bg-bg-secondary border border-border rounded-lg shadow-sm results-card">
              <div className="card-header">
                <h3>
                  {screens.find(s => s.slug === selectedSlug)?.label}
                  <span className="count-badge">{strategyResults.length} hits</span>
                </h3>
                <div className="header-actions" style={{ display: 'flex', gap: '8px' }}>
                  <ExportButton 
                    data={strategyResults}
                    columns={currentColumns}
                    filename={`${selectedSlug}-${new Date().toISOString().split('T')[0]}.csv`}
                    disabled={loadingStrategyResults}
                  />
                  <button 
                    onClick={() => setLiveMode(!liveMode)}
                    className={`live-toggle ${liveMode ? 'active' : ''}`}
                  >
                    <RefreshCw size={14} className={loadingStrategyResults ? "animate-spin" : ""} />
                    Live Mode
                  </button>
                  </div>
                  </div>
                  <DataTable 
                  columns={currentColumns}
                  data={strategyResults}
                  loading={loadingStrategyResults}
                  initialSort={{ key: 'score', direction: 'desc' }}
                  />            </div>
          )}
        </section>
      ) : (
        <section className="interactive-tab">
          <div className="bg-bg-secondary border border-border rounded-lg shadow-sm filter-panel mb-24 p-24">
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
                <label className="filter-label-styled">Max P/E</label>
                <input 
                  type="number" placeholder="e.g. 30"
                  value={interactiveFilters.maxPE}
                  onChange={(e) => setInteractiveFilters({...interactiveFilters, maxPE: e.target.value})}
                  className="custom-number-input"
                  
                />
              </div>
            </div>
          </div>

          <div className="bg-bg-secondary border border-border rounded-lg shadow-sm results-card">
            <div className="card-header">
              <h3>Results <span className="count-badge">{filteredStocks.length} stocks</span></h3>
              <ExportButton 
                data={filteredStocks}
                columns={defaultColumns}
                filename={`interactive-screen-${new Date().toISOString().split('T')[0]}.csv`}
                disabled={loadingStocks}
              />
            </div>
            <DataTable 
              columns={defaultColumns}
              data={filteredStocks}
              loading={loadingStocks}
              initialSort={{ key: 'score', direction: 'desc' }}
            />
          </div>
        </section>
      )}
    </div>
  );
};

export default Discover;
