import {
  Play,
  Square,
  Activity,
  RefreshCcw,
  CheckCircle2,
  AlertCircle,
  Database,
  Monitor,
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
    running: {
      icon: <RefreshCcw className='animate-spin text-white' />,
      label: 'Running',
      class: 'bg-blue-600 text-white shadow-blue-500/30',
    },
    stopping: {
      icon: <RefreshCcw className='animate-spin text-white' />,
      label: 'Stopping',
      class: 'bg-amber-500 text-white shadow-amber-500/30',
    },
    idle: {
      icon: <CheckCircle2 className='text-white' />,
      label: 'Engine Idle',
      class: 'bg-green-500 text-white shadow-green-500/30',
    },
    never_run: {
      icon: <AlertCircle className='text-white' />,
      label: 'Not Initialized',
      class: 'bg-slate-500 text-white shadow-slate-500/30',
    },
    error: {
      icon: <AlertCircle className='text-white' />,
      label: 'Engine Error',
      class: 'bg-red-500 text-white shadow-red-500/30',
    },
  };

  const currentStatus = statusMap[status] || statusMap['idle'];

  return (
    <div className='w-full flex flex-col gap-10 animate-fade-in'>
      <header className='mb-2'>
        <h1 className='text-3xl sm:text-4xl font-black tracking-tighter mb-2 uppercase'>
          System Control
        </h1>
        <p className='text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-xs'>
          Manage the screening engine, data integrity, and global preferences.
        </p>
      </header>

      <div className='grid grid-cols-1 lg:grid-cols-2 gap-8'>
        {/* Pipeline Control Card */}
        <section className='bg-bg-secondary border-2 border-border rounded-2xl shadow-sm p-8 flex flex-col gap-8 transition-all hover:border-blue-500/20'>
          <div className='flex items-center gap-3'>
            <div className='bg-blue-500/10 p-2 rounded-lg'>
              <Activity className='text-blue-500' />
            </div>
            <h2 className='text-xl font-black uppercase tracking-tight'>
              Pipeline Engine
            </h2>
          </div>

          <div
            className={`p-6 rounded-2xl border-2 border-transparent transition-all flex items-center justify-between shadow-lg ${currentStatus.class}`}
          >
            <div className='flex items-center gap-4'>
              <div className='bg-white/20 p-2 rounded-xl backdrop-blur-md'>
                {currentStatus.icon}
              </div>
              <div>
                <div className='text-[10px] uppercase font-black tracking-[0.2em] opacity-80'>
                  Current Operational Status
                </div>
                <div className='text-2xl font-black tracking-tight'>
                  {currentStatus.label}
                </div>
              </div>
            </div>
            {status === 'running' && (
              <div className='font-black text-xl bg-white/20 px-3 py-1 rounded-lg backdrop-blur-md'>
                {pipeline?.stocks_scored || 0} / {pipeline?.total_symbols || 0}
              </div>
            )}
          </div>

          <div className='grid grid-cols-2 gap-4'>
            <div className='bg-slate-50 dark:bg-slate-900 border-2 border-border p-5 rounded-2xl flex flex-col gap-1 shadow-sm'>
              <span className='text-[10px] font-black uppercase tracking-widest text-slate-500'>
                Fetched Assets
              </span>
              <span className='text-3xl font-black font-mono tracking-tighter'>
                {pipeline?.stocks_fetched || 0}
              </span>
            </div>
            <div className='bg-slate-50 dark:bg-slate-900 border-2 border-border p-5 rounded-2xl flex flex-col gap-1 shadow-sm'>
              <span className='text-[10px] font-black uppercase tracking-widest text-slate-500'>
                Scored Assets
              </span>
              <span className='text-3xl font-black font-mono tracking-tighter text-blue-500'>
                {pipeline?.stocks_scored || 0}
              </span>
            </div>
          </div>

          <div className='flex flex-col gap-3 mt-2'>
            {status === 'running' ? (
              <button
                className='bg-red-600 text-white py-4 rounded-xl font-black uppercase tracking-[0.2em] text-xs flex items-center justify-center gap-3 transition-all hover:bg-red-700 shadow-lg shadow-red-500/20 active:scale-[0.98]'
                onClick={handleStopPipeline}
                disabled={isBusy && status !== 'running'}
              >
                <Square size={18} fill='currentColor' />
                Emergency Stop
              </button>
            ) : (
              <div className='grid grid-cols-1 sm:grid-cols-2 gap-3'>
                <button
                  className='bg-blue-600 text-white py-4 rounded-xl font-black uppercase tracking-[0.2em] text-xs flex items-center justify-center gap-3 transition-all hover:bg-blue-700 shadow-lg shadow-blue-500/20 active:scale-[0.98]'
                  onClick={() => handleRunPipeline()}
                  disabled={isBusy}
                >
                  <Play size={18} fill='currentColor' />
                  Full Analysis
                </button>
                <button
                  className='bg-slate-100 dark:bg-slate-800 text-text py-4 rounded-xl font-black uppercase tracking-[0.2em] text-xs flex items-center justify-center gap-3 border-2 border-border transition-all hover:border-blue-500 active:scale-[0.98]'
                  onClick={() => handleRunPipeline(50)}
                  disabled={isBusy}
                >
                  <Play size={18} />
                  Rapid Test
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Preferences Card */}
        <section className='bg-bg-secondary border-2 border-border rounded-2xl shadow-sm p-8 flex flex-col gap-8 transition-all hover:border-blue-500/20'>
          <div className='flex items-center gap-3'>
            <div className='bg-indigo-500/10 p-2 rounded-lg'>
              <Monitor className='text-indigo-500' />
            </div>
            <h2 className='text-xl font-black uppercase tracking-tight'>
              System Preferences
            </h2>
          </div>

          <div className='flex justify-between items-center p-6 bg-slate-50 dark:bg-slate-900 border-2 border-border rounded-2xl shadow-sm'>
            <div>
              <div className='font-black uppercase tracking-widest text-[10px] text-slate-500 mb-1'>
                UI Appearance
              </div>
              <div className='text-lg font-black'>
                {theme === 'dark' ? 'DARK MODE (OLED)' : 'LIGHT MODE (CLEAN)'}
              </div>
            </div>
            <button
              onClick={toggleTheme}
              className='bg-bg-secondary text-text px-6 py-2.5 rounded-xl font-black uppercase tracking-widest text-[10px] border-2 border-border cursor-pointer transition-all hover:border-blue-500 shadow-sm'
            >
              Toggle Theme
            </button>
          </div>

          <div className='flex flex-col gap-4'>
            <div className='flex items-center gap-3'>
              <div className='bg-amber-500/10 p-2 rounded-lg'>
                <Database className='text-amber-500' size={20} />
              </div>
              <h3 className='text-sm font-black uppercase tracking-widest'>
                Connectivity & Data
              </h3>
            </div>
            <div className='text-sm font-bold text-slate-500 dark:text-slate-400 leading-relaxed bg-slate-50 dark:bg-slate-900 p-5 rounded-2xl border border-border'>
              Assets are fetched from{' '}
              <span className='text-text'>Yahoo Finance (yfinance)</span> and
              validated against <span className='text-text'>NSE India</span>{' '}
              universes. Analysis results are cached for 12 hours. The next
              automated synchronization is scheduled for 3:45 PM IST.
            </div>
          </div>
        </section>
      </div>

      {pipeline?.scored_at && (
        <div className='bg-slate-50 dark:bg-slate-900/50 py-3 px-6 rounded-full border border-border w-fit mx-auto text-slate-500 font-mono font-black text-[10px] uppercase tracking-[0.2em] shadow-sm'>
          System Last Synchronized:{' '}
          {new Date(pipeline.scored_at).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default System;
