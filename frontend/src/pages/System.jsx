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
import { usePipeline } from '../hooks/usePipeline';
import { useTheme } from '../hooks/useTheme';
import './System.css';

const System = () => {
  const { status, stats: pipeline, isBusy, run, stop } = usePipeline();
  const { theme, toggleTheme } = useTheme();

  const handleRunPipeline = async (limit = null) => {
    try {
      await run(limit);
    } catch (error) {
      console.error('Failed to run pipeline:', error);
    }
  };

  const handleStopPipeline = async () => {
    try {
      await stop();
    } catch (error) {
      console.error('Failed to stop pipeline:', error);
    }
  };

  const statusMap = {
    'running': { icon: <RefreshCcw className="spin text-bullish" />, label: 'Running', class: 'bullish' },
    'stopping': { icon: <RefreshCcw className="spin text-warning" />, label: 'Stopping', class: 'warning' },
    'idle': { icon: <CheckCircle2 className="text-bullish" />, label: 'Idle', class: 'bullish' },
    'never_run': { icon: <AlertCircle className="text-warning" />, label: 'Never Run', class: 'warning' },
    'error': { icon: <AlertCircle className="text-bearish" />, label: 'Error', class: 'bearish' }
  };

  const currentStatus = statusMap[status] || statusMap['idle'];

  return (
    <div className="system-page">
      <header className="page-header">
        <h1>System Settings</h1>
        <p className="text-text-muted">Manage the screening engine and application preferences.</p>
      </header>

      <div className="system-grid">
        {/* Pipeline Control Card */}
        <section className="bg-bg-secondary border border-border rounded-lg shadow-sm system-bg-bg-secondary border border-border rounded-lg shadow-sm">
          <div className="bg-bg-secondary border border-border rounded-lg shadow-sm-header-row">
            <Activity className="text-primary" />
            <h2>Pipeline Engine</h2>
          </div>

          <div className="status-hero bg-bg-secondary border border-border rounded-lg shadow-sm">
            <div className="status-flex">
              {currentStatus.icon}
              <div>
                <div className="status-label">Engine Status</div>
                <div className="status-value">{currentStatus.label}</div>
              </div>
            </div>
          </div>

          <div className="stats-grid">
            <div className="stat-box">
              <span className="label">Stocks Fetched</span>
              <span className="value mono">{pipeline?.stocks_fetched || 0}</span>
            </div>
            <div className="stat-box">
              <span className="label">Stocks Scored</span>
              <span className="value mono">{pipeline?.stocks_scored || 0}</span>
            </div>
          </div>

          <div className="controls">
            {status === 'running' ? (
              <button 
                className="primary-button stop-btn" 
                onClick={handleStopPipeline}
                disabled={isBusy && status !== 'running'}
              >
                <Square size={20} fill="currentColor" />
                Stop Engine
              </button>
            ) : (
              <>
                <button 
                  className="primary-button" 
                  onClick={() => handleRunPipeline()}
                  disabled={isBusy}
                >
                  <Play size={20} />
                  Start Full Run
                </button>
                <button 
                  className="secondary-button" 
                  onClick={() => handleRunPipeline(50)}
                  disabled={isBusy}
                >
                  <Play size={18} />
                  Quick Test (50)
                </button>
              </>
            )}
          </div>
        </section>

        {/* Preferences Card */}
        <section className="bg-bg-secondary border border-border rounded-lg shadow-sm system-bg-bg-secondary border border-border rounded-lg shadow-sm">
          <div className="bg-bg-secondary border border-border rounded-lg shadow-sm-header-row">
            <Monitor className="text-primary" />
            <h2>Preferences</h2>
          </div>

          <div className="preference-item">
            <div>
              <div className="pref-title">Visual Theme</div>
              <div className="text-text-muted">Current: {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</div>
            </div>
            <button 
              onClick={toggleTheme}
              className="secondary-button"
            >
              Toggle
            </button>
          </div>

          <div className="data-sources">
            <div className="bg-bg-secondary border border-border rounded-lg shadow-sm-header-row">
              <Database className="text-primary" />
              <h2>Data Sources</h2>
            </div>
            <div className="text-text-muted">
              Market data provided by Yahoo Finance and NSE India. Updates occur daily after market close (3:30 PM IST).
            </div>
          </div>
        </section>
      </div>

      {pipeline?.scored_at && (
        <div className="text-text-muted mono" style={{ marginTop: '32px', fontSize: '0.75rem', textAlign: 'center' }}>
          Last successful run: {new Date(pipeline.scored_at).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default System;
