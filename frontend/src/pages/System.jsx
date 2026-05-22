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
    'running': { icon: <RefreshCcw className="animate-spin text-bullish" />, label: 'Running', class: 'bullish' },
    'stopping': { icon: <RefreshCcw className="animate-spin text-warning" />, label: 'Stopping', class: 'warning' },
    'idle': { icon: <CheckCircle2 className="text-bullish" />, label: 'Idle', class: 'bullish' },
    'never_run': { icon: <AlertCircle className="text-warning" />, label: 'Never Run', class: 'warning' },
    'error': { icon: <AlertCircle className="text-bearish" />, label: 'Error', class: 'bearish' }
  };

  const currentStatus = statusMap[status] || statusMap['idle'];

  return (
    <div className="max-w-[1000px] mx-auto p-6 flex flex-col gap-8">
      <header>
        <h1 className="text-[2rem] font-bold mb-2">System Settings</h1>
        <p className="text-text-muted">Manage the screening engine and application preferences.</p>
      </header>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(400px,1fr))] gap-6">
        {/* Pipeline Control Card */}
        <section className="bg-bg-secondary border border-border rounded-lg shadow-sm p-6 flex flex-col gap-6">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="text-primary" />
            <h2 className="text-[1.25rem] font-bold">Pipeline Engine</h2>
          </div>

          <div className="bg-bg-elevated p-5 rounded-lg border border-border">
            <div className="flex items-center gap-4">
              {currentStatus.icon}
              <div>
                <div className="text-[0.8rem] text-text-muted uppercase tracking-wider">Engine Status</div>
                <div className="text-[1.25rem] font-bold">{currentStatus.label}</div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-bg-secondary border border-border p-4 rounded-md flex flex-col gap-1">
              <span className="text-[0.75rem] text-text-muted">Stocks Fetched</span>
              <span className="text-[1.1rem] font-semibold font-mono">{pipeline?.stocks_fetched || 0}</span>
            </div>
            <div className="bg-bg-secondary border border-border p-4 rounded-md flex flex-col gap-1">
              <span className="text-[0.75rem] text-text-muted">Stocks Scored</span>
              <span className="text-[1.1rem] font-semibold font-mono">{pipeline?.stocks_scored || 0}</span>
            </div>
          </div>

          <div className="flex gap-3">
            {status === 'running' ? (
              <button 
                className="bg-bearish text-white px-5 py-3 rounded-md font-semibold flex items-center gap-2 transition-all duration-200 border-none cursor-pointer hover:enabled:brightness-110 hover:enabled:shadow-[0_4px_12px_rgba(239,68,68,0.2)] disabled:opacity-50 disabled:cursor-not-allowed" 
                onClick={handleStopPipeline}
                disabled={isBusy && status !== 'running'}
              >
                <Square size={20} fill="currentColor" />
                Stop Engine
              </button>
            ) : (
              <>
                <button 
                  className="bg-primary text-white px-5 py-3 rounded-md font-semibold flex items-center gap-2 transition-all duration-200 border-none cursor-pointer hover:enabled:brightness-110 hover:enabled:shadow-[0_4px_12px_rgba(59,130,246,0.2)] disabled:opacity-50 disabled:cursor-not-allowed" 
                  onClick={() => handleRunPipeline()}
                  disabled={isBusy}
                >
                  <Play size={20} />
                  Start Full Run
                </button>
                <button 
                  className="bg-bg-elevated text-text px-5 py-3 rounded-md font-semibold flex items-center gap-2 border border-border cursor-pointer transition-all duration-200 hover:enabled:bg-border disabled:opacity-50 disabled:cursor-not-allowed" 
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
        <section className="bg-bg-secondary border border-border rounded-lg shadow-sm p-6 flex flex-col gap-6">
          <div className="flex items-center gap-3 mb-2">
            <Monitor className="text-primary" />
            <h2 className="text-[1.25rem] font-bold">Preferences</h2>
          </div>

          <div className="flex justify-between items-center p-4 bg-bg-elevated rounded-md">
            <div>
              <div className="font-semibold mb-1">Visual Theme</div>
              <div className="text-text-muted">Current: {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</div>
            </div>
            <button 
              onClick={toggleTheme}
              className="bg-bg-elevated text-text px-5 py-3 rounded-md font-semibold flex items-center gap-2 border border-border cursor-pointer transition-all duration-200 hover:enabled:bg-border disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Toggle
            </button>
          </div>

          <div className="mt-6 flex flex-col gap-3">
            <div className="flex items-center gap-3 mb-2">
              <Database className="text-primary" />
              <h2 className="text-[1.25rem] font-bold">Data Sources</h2>
            </div>
            <div className="text-text-muted">
              Market data provided by Yahoo Finance and NSE India. Updates occur daily after market close (3:30 PM IST).
            </div>
          </div>
        </section>
      </div>

      {pipeline?.scored_at && (
        <div className="text-text-muted font-mono mt-8 text-[0.75rem] text-center">
          Last successful run: {new Date(pipeline.scored_at).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default System;
