import { useState, useEffect } from 'react';
import { 
  Play, 
  Square, 
  Activity, 
  RefreshCcw, 
  CheckCircle2,
  AlertCircle,
  Database,
  Monitor
} from 'lucide-react';
import { fetchPipelineStatus, runScreener, stopPipeline } from '../api/client';
import { useTheme } from '../hooks/useTheme';
import './Dashboard.css';

const System = () => {
  const [pipeline, setPipeline] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const getStatus = async () => {
    try {
      const response = await fetchPipelineStatus();
      setPipeline(response.data);
    } catch (error) {
      console.error('Failed to fetch pipeline status:', error);
    }
  };

  useEffect(() => {
    getStatus();
    const interval = setInterval(getStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRunPipeline = async (limit = null) => {
    setIsRunning(true);
    try {
      await runScreener(limit);
      getStatus();
    } catch (error) {
      console.error('Failed to run pipeline:', error);
    } finally {
      setIsRunning(false);
    }
  };

  const handleStopPipeline = async () => {
    setIsStopping(true);
    try {
      await stopPipeline();
      getStatus();
    } catch (error) {
      console.error('Failed to stop pipeline:', error);
    } finally {
      setIsStopping(false);
    }
  };

  const statusMap = {
    'running': { icon: <RefreshCcw className="spin text-bullish" />, label: 'Running', class: 'bullish' },
    'idle': { icon: <CheckCircle2 className="text-bullish" />, label: 'Idle', class: 'bullish' },
    'never_run': { icon: <AlertCircle className="text-warning" />, label: 'Never Run', class: 'warning' },
    'error': { icon: <AlertCircle className="text-bearish" />, label: 'Error', class: 'bearish' }
  };

  const currentStatus = statusMap[pipeline?.status] || statusMap['idle'];

  return (
    <div className="system-page">
      <header className="page-header">
        <h1>System Settings</h1>
        <p className="text-muted">Manage the screening engine and application preferences.</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '32px' }}>
        {/* Pipeline Control Card */}
        <section className="card" style={{ padding: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
            <Activity className="text-primary" />
            <h2 style={{ fontSize: '1.25rem' }}>Pipeline Engine</h2>
          </div>

          <div className="status-hero card" style={{ padding: '24px', background: 'var(--color-bg-elevated)', border: 'none', marginBottom: '32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              {currentStatus.icon}
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-muted)' }}>Engine Status</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800 }}>{currentStatus.label}</div>
              </div>
            </div>
          </div>

          <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '32px' }}>
            <div className="stat-box">
              <span className="label">Stocks Fetched</span>
              <span className="value mono">{pipeline?.stocks_fetched || 0}</span>
            </div>
            <div className="stat-box">
              <span className="label">Stocks Scored</span>
              <span className="value mono">{pipeline?.stocks_scored || 0}</span>
            </div>
          </div>

          <div className="controls" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {pipeline?.status === 'running' ? (
              <button 
                className="primary-button" 
                onClick={handleStopPipeline}
                disabled={isStopping}
                style={{ width: '100%', margin: 0, background: 'var(--color-bearish)' }}
              >
                <Square size={20} fill="currentColor" />
                Stop Engine
              </button>
            ) : (
              <>
                <button 
                  className="primary-button" 
                  onClick={() => handleRunPipeline()}
                  disabled={isRunning}
                  style={{ width: '100%', margin: 0 }}
                >
                  <Play size={20} />
                  Start Full Run
                </button>
                <button 
                  className="secondary-button" 
                  onClick={() => handleRunPipeline(50)}
                  disabled={isRunning}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  <Play size={18} />
                  Quick Test (50)
                </button>
              </>
            )}
          </div>
        </section>

        {/* Preferences Card */}
        <section className="card" style={{ padding: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
            <Monitor className="text-primary" />
            <h2 style={{ fontSize: '1.25rem' }}>Preferences</h2>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-lg)' }}>
            <div>
              <div style={{ fontWeight: 600 }}>Visual Theme</div>
              <div className="text-muted" style={{ fontSize: '0.85rem' }}>Current: {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</div>
            </div>
            <button 
              onClick={toggleTheme}
              className="secondary-button"
              style={{ padding: '8px 16px' }}
            >
              Toggle
            </button>
          </div>

          <div style={{ marginTop: '40px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <Database className="text-primary" />
              <h2 style={{ fontSize: '1.25rem' }}>Data Sources</h2>
            </div>
            <div className="text-muted" style={{ fontSize: '0.85rem' }}>
              Market data provided by Yahoo Finance and NSE India. Updates occur daily after market close (3:30 PM IST).
            </div>
          </div>
        </section>
      </div>

      {pipeline?.scored_at && (
        <div className="text-muted mono" style={{ marginTop: '32px', fontSize: '0.75rem', textAlign: 'center' }}>
          Last successful run: {new Date(pipeline.scored_at).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default System;
