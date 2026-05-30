import { Target, ShieldAlert, Zap } from 'lucide-react';

const TradingPlan = ({ setup }) => {
  if (!setup) return null;

  return (
    <div className='bg-bg-secondary border-2 border-border rounded-2xl p-6 shadow-sm'>
      <div className='flex items-center gap-3 mb-6 capitalize font-black text-lg text-text'>
        <div className='bg-blue-500/10 p-2 rounded-lg'>
          <Zap size={20} className='text-blue-500 fill-blue-500' />
        </div>
        <h3 className='tracking-tight'>
          Plan: {setup.setup_type.replace(/_/g, ' ')}
        </h3>
      </div>

      <div className='grid grid-cols-1 gap-4 mb-6'>
        <div className='flex justify-between items-center bg-slate-50 dark:bg-slate-900 p-4 rounded-xl border border-border'>
          <div className='flex items-center gap-3'>
            <Target size={18} className='text-blue-500' />
            <span className='text-[10px] font-black uppercase tracking-widest text-slate-500'>
              Entry Zone
            </span>
          </div>
          <span className='text-sm font-black font-mono tracking-tighter'>
            ₹{setup.entry_zone.low.toFixed(1)} - ₹
            {setup.entry_zone.high.toFixed(1)}
          </span>
        </div>

        <div className='flex justify-between items-center bg-red-50 dark:bg-red-900/20 p-4 rounded-xl border border-red-100 dark:border-red-900/30'>
          <div className='flex items-center gap-3'>
            <ShieldAlert size={18} className='text-red-500' />
            <span className='text-[10px] font-black uppercase tracking-widest text-red-600 dark:text-red-400'>
              Stop Loss
            </span>
          </div>
          <span className='text-lg font-black font-mono text-red-600 dark:text-red-400 tracking-tighter'>
            ₹{setup.stop_loss.toFixed(1)}
          </span>
        </div>
      </div>

      <div className='flex flex-col gap-3 mb-6'>
        <span className='text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 ml-1'>
          Profit Targets
        </span>
        <div className='flex gap-2'>
          {setup.targets.map((t, idx) => (
            <div
              key={idx}
              className='flex-1 bg-green-50 dark:bg-green-900/20 p-3 rounded-xl border border-green-100 dark:border-green-900/30 flex flex-col items-center'
            >
              <span className='text-[9px] font-black text-green-700 dark:text-green-400 uppercase tracking-widest mb-1'>
                {t.rr}R
              </span>
              <span className='text-sm font-black font-mono text-green-700 dark:text-green-400'>
                ₹{t.level.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className='flex justify-between items-center bg-slate-50 dark:bg-slate-900/50 p-3 px-4 rounded-xl border border-border'>
        <div className='flex flex-col'>
          <span className='text-[9px] font-black text-slate-500 uppercase tracking-widest'>
            Risk/Share
          </span>
          <span className='font-bold text-xs'>
            ₹{setup.risk_per_share.toFixed(2)}
          </span>
        </div>
        <div className='h-6 w-px bg-border'></div>
        <div className='flex flex-col items-end'>
          <span className='text-[9px] font-black text-slate-500 uppercase tracking-widest'>
            ATR Volatility
          </span>
          <span className='font-bold text-xs'>{setup.atr.toFixed(1)}</span>
        </div>
      </div>
    </div>
  );
};

export default TradingPlan;
