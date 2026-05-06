import React, { useEffect, useState } from 'react';
import { Play, Activity } from 'lucide-react';
import { getTopStocks, getStatus, runScreener } from './api';
import ScoreCard from './components/ScoreCard';
import './App.css';

function App() {
  const [stocks, setStocks] = useState([]);
  const [status, setStatus] = useState({ status: 'idle' });

  const fetchData = async () => {
    try {
      const [stocksRes, statusRes] = await Promise.all([getTopStocks(), getStatus()]);
      setStocks(stocksRes.data);
      setStatus(statusRes.data);
    } catch (err) {
      console.error("Fetch failed", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRun = async () => {
    try {
      await runScreener();
      fetchData();
    } catch (err) {
      console.error("Run screener failed", err);
    }
  };

  return (
    <div className="dashboard-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Activity className="icon-accent" />
          <h1>Stock AI</h1>
        </div>
        
        <div className="status-module">
          <div className="status-indicator">
            <span className={`dot ${status.status}`}></span>
            <span className="status-text">Pipeline: {status.status?.toUpperCase() || 'IDLE'}</span>
          </div>
          <p className="last-run">Scored: {status.scored || 0}</p>
        </div>

        <button 
          className="run-button" 
          onClick={handleRun} 
          disabled={status.status === 'running'}
        >
          <Play size={16} />
          Run Screener
        </button>
      </aside>

      <main className="main-content">
        <header className="content-header">
          <h2>Top Scored Stocks</h2>
          <span className="timestamp">Real-time Analysis</span>
        </header>
        
        <div className="stock-grid">
          {stocks.map(s => <ScoreCard key={s.symbol} stock={s} />)}
        </div>
      </main>
    </div>
  );
}

export default App;
