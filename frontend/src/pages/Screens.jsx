import React, { useState, useEffect } from 'react';
import { getScreensList, getScreenBySlug } from '../api/client';
import ScreenCard from '../components/ScreenCard';
import ScreenResultTable from '../components/ScreenResultTable';
import { RefreshCw } from 'lucide-react';
import './Dashboard.css';

const Screens = () => {
  const [screens, setScreens] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [results, setResults] = useState([]);
  const [loadingScreens, setLoadingScreens] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('All');
  const [liveMode, setLiveMode] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchScreens = async () => {
      try {
        const res = await getScreensList();
        setScreens(res.data);
        if (res.data.length > 0) {
          setSelectedSlug(res.data[0].slug);
        }
      } catch (err) {
        setError('Could not load screens. Check that the pipeline has run at least once.');
      } finally {
        setLoadingScreens(false);
      }
    };
    fetchScreens();
  }, []);

  useEffect(() => {
    if (!selectedSlug) return;
    
    const fetchResults = async () => {
      setLoadingResults(true);
      try {
        const res = await getScreenBySlug(selectedSlug, liveMode);
        setResults(res.data);
      } catch (err) {
        setResults([]);
      } finally {
        setLoadingResults(false);
      }
    };
    
    fetchResults();
  }, [selectedSlug, liveMode]);

  const categories = ['All', ...new Set(screens.map(s => s.category))];
  const filteredScreens = screens.filter(s => categoryFilter === 'All' || s.category === categoryFilter);
  const activeScreen = screens.find(s => s.slug === selectedSlug);

  return (
    <div className="dashboard-page">
      <main className="dashboard-content" style={{ padding: '24px' }}>
        <header className="dashboard-header" style={{ marginBottom: '24px' }}>
          <div className="action-bar">
            <h2>Named Screens</h2>
            <p style={{ color: 'var(--color-text-muted)', margin: '8px 0 0 0', fontSize: '14px' }}>
              Pre-built strategies. Updated after each run.
            </p>
          </div>
        </header>

        {error ? (
          <div className="no-results">
            <p className="danger">{error}</p>
            <button className="primary-button" onClick={() => window.location.reload()}>Retry</button>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', overflowX: 'auto', paddingBottom: '8px' }}>
              {categories.map(cat => (
                <button
                  key={cat}
                  className={`filter-chip ${categoryFilter === cat ? 'active' : ''}`}
                  style={{ padding: '6px 12px' }}
                  onClick={() => setCategoryFilter(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="stock-grid" style={{ marginBottom: '32px' }}>
              {loadingScreens ? (
                [...Array(4)].map((_, i) => (
                  <div key={i} className="card" style={{ height: '120px', background: 'var(--color-bg-elevated)' }}></div>
                ))
              ) : (
                filteredScreens.map(screen => (
                  <ScreenCard
                    key={screen.slug}
                    screen={screen}
                    isSelected={selectedSlug === screen.slug}
                    onClick={() => setSelectedSlug(screen.slug)}
                  />
                ))
              )}
            </div>

            {activeScreen && (
              <div className="card" style={{ padding: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Results: {activeScreen.label} <span style={{ color: 'var(--color-text-muted)', fontSize: '13px', fontWeight: 'normal' }}>({results.length} hits)</span></h3>
                  <button 
                    onClick={() => setLiveMode(!liveMode)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '6px',
                      background: liveMode ? 'rgba(16, 185, 129, 0.1)' : 'transparent',
                      color: liveMode ? 'var(--color-bullish)' : 'var(--color-text-muted)',
                      border: `1px solid ${liveMode ? 'var(--color-bullish)' : 'var(--color-border)'}`,
                      padding: '4px 10px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', fontWeight: 600
                    }}
                  >
                    <RefreshCw size={14} className={loadingResults ? "animate-spin" : ""} />
                    Live Mode
                  </button>
                </div>
                <ScreenResultTable results={results} slug={selectedSlug} loading={loadingResults} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
};

export default Screens;
