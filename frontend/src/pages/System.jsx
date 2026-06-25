import Play from 'lucide-react/dist/esm/icons/play';
import Activity from 'lucide-react/dist/esm/icons/activity';
import RefreshCcw from 'lucide-react/dist/esm/icons/refresh-ccw';
import CheckCircle2 from 'lucide-react/dist/esm/icons/check-circle-2';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Database from 'lucide-react/dist/esm/icons/database';
import Monitor from 'lucide-react/dist/esm/icons/monitor';
import { usePaperPipeline } from '../hooks/usePaperPipeline';
import { useTheme } from '../hooks/useTheme';

const statusMap = {
  running: {
    icon: <RefreshCcw className='animate-spin text-white' />,
    label: 'Running',
    class: 'bg-blue-600 text-white shadow-blue-500/30',
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
};

const System = () => {
  const { status, lastProcessedDate, goLiveDate, isRunning, trigger } =
    usePaperPipeline();
  const { theme, toggleTheme } = useTheme();

  const currentStatus = statusMap[status] || statusMap['idle'];

  const handleTrigger = async () => {
    try {
      await trigger();
    } catch (error) {
      console.error('Failed to trigger S3 paper pipeline:', error);
    }
  };

  return (
    <div className='w-full flex flex-col gap-10 animate-fade-in'>
      <header className='mb-2'>
        <h1 className='text-3xl sm:text-4xl font-black tracking-tighter mb-2 uppercase'>
          System Control
        </h1>
        <p className='text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-xs'>
          Manage the S3 paper engine, data integrity, and global preferences.
        </p>
      </header>

      <div className='grid grid-cols-1 lg:grid-cols-2 gap-8'>
        {/* S3 Paper Pipeline Card */}
        <section className='bg-bg-secondary border-2 border-border rounded-2xl shadow-sm p-8 flex flex-col gap-8 transition-all hover:border-blue-500/20'>
          <div className='flex items-center gap-3'>
            <div className='bg-blue-500/10 p-2 rounded-lg'>
              <Activity className='text-blue-500' />
            </div>
            <h2 className='text-xl font-black uppercase tracking-tight'>
              S3 Paper Engine
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
                  Daily Post-Close Job
                </div>
                <div className='text-2xl font-black tracking-tight'>
                  {currentStatus.label}
                </div>
              </div>
            </div>
          </div>

          <div className='grid grid-cols-2 gap-4'>
            <div className='bg-slate-50 dark:bg-slate-900 border-2 border-border p-5 rounded-2xl flex flex-col gap-1 shadow-sm'>
              <span className='text-[10px] font-black uppercase tracking-widest text-slate-500'>
                Last Processed
              </span>
              <span className='text-base font-black font-mono tracking-tighter'>
                {lastProcessedDate
                  ? new Date(lastProcessedDate).toLocaleDateString('en-IN', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })
                  : '—'}
              </span>
            </div>
            <div className='bg-slate-50 dark:bg-slate-900 border-2 border-border p-5 rounded-2xl flex flex-col gap-1 shadow-sm'>
              <span className='text-[10px] font-black uppercase tracking-widest text-slate-500'>
                Go-Live Date
              </span>
              <span className='text-base font-black font-mono tracking-tighter text-blue-500'>
                {goLiveDate
                  ? new Date(goLiveDate).toLocaleDateString('en-IN', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })
                  : '—'}
              </span>
            </div>
          </div>

          <div className='flex flex-col gap-3 mt-2'>
            <button
              className='bg-blue-600 text-white py-4 rounded-xl font-black uppercase tracking-[0.2em] text-xs flex items-center justify-center gap-3 transition-all hover:bg-blue-700 shadow-lg shadow-blue-500/20 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed'
              onClick={handleTrigger}
              disabled={isRunning}
            >
              {isRunning ? (
                <RefreshCcw size={18} className='animate-spin' />
              ) : (
                <Play size={18} fill='currentColor' />
              )}
              {isRunning ? 'Running...' : 'Run Now'}
            </button>
            <p className='text-[10px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-widest text-center'>
              Auto-scheduled daily at 7:30 PM IST
            </p>
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
              Price data is sourced via{' '}
              <span className='text-text'>NSE bhavcopy</span> (daily adjusted
              OHLCV). The S3 engine runs{' '}
              <span className='text-text'>post-close each trading day</span>,
              processing all unconfirmed days in ordered-replay fashion. Parity
              is shadow-checked monthly.
            </div>
          </div>
        </section>
      </div>

      {!!lastProcessedDate && (
        <div className='bg-slate-50 dark:bg-slate-900/50 py-3 px-6 rounded-full border border-border w-fit mx-auto text-slate-500 font-mono font-black text-[10px] uppercase tracking-[0.2em] shadow-sm'>
          S3 Engine Last Processed:{' '}
          {new Date(lastProcessedDate).toLocaleDateString('en-IN', {
            weekday: 'short',
            day: '2-digit',
            month: 'short',
            year: 'numeric',
          })}
        </div>
      )}
    </div>
  );
};

export default System;
