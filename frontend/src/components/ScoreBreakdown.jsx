import { Activity } from 'lucide-react';
import { filter, map } from 'lodash/fp';
import { memo } from 'react';

const ScoreBreakdown = memo(({ breakdown, totalScore }) => {
  const technical = filter((b) => b.category === 'technical', breakdown);
  const fundamental = filter((b) => b.category === 'fundamental', breakdown);

  return (
    <div className='flex flex-col gap-6'>
      <div className='flex items-baseline justify-between bg-slate-50 dark:bg-slate-900/50 p-4 rounded-2xl border-2 border-border shadow-inner'>
        <div className='flex flex-col'>
          <span className='text-[10px] text-slate-500 dark:text-slate-400 uppercase font-black tracking-[0.2em] mb-1'>
            Total Intelligence Score
          </span>
          <div className='flex items-baseline gap-2'>
            <span className='text-5xl font-black tracking-tighter text-blue-600 dark:text-blue-400'>
              {totalScore?.toFixed(1)}
            </span>
            <span className='text-xl font-black text-slate-400 tracking-tighter'>
              / 100
            </span>
          </div>
        </div>
        <div
          className={`p-2 rounded-xl shadow-lg ${totalScore >= 70 ? 'bg-green-500 shadow-green-500/20' : totalScore >= 50 ? 'bg-blue-500 shadow-blue-500/20' : 'bg-slate-500 shadow-slate-500/20'}`}
        >
          <Activity className='text-white' size={32} />
        </div>
      </div>

      <div className='flex flex-col gap-3'>
        <div className='text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 mb-2 border-b-2 border-border pb-1'>
          Technical Analysis <span className='opacity-60'>(max 70)</span>
        </div>
        {map(
          (item) => (
            <BreakdownRow key={item.label} item={item} />
          ),
          technical
        )}
      </div>

      <div className='flex flex-col gap-3'>
        <div className='text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400 mb-2 border-b-2 border-border pb-1'>
          Fundamental Health <span className='opacity-60'>(max 30)</span>
        </div>
        {map(
          (item) => (
            <BreakdownRow key={item.label} item={item} />
          ),
          fundamental
        )}
      </div>

      <p className='text-[0.7rem] text-text-muted m-0 italic'>
        * Pledge and ROCE values may show 0 if cache is outdated.
      </p>
    </div>
  );
});

const getSignalColor = (signal) => {
  if (!signal) return 'text-slate-400';
  const s = signal.toLowerCase();
  if (
    s.includes('bullish') ||
    s.includes('high') ||
    s.includes('strong') ||
    s.includes('positive') ||
    s.includes('above')
  )
    return 'text-green-600 dark:text-green-400 font-bold';
  if (
    s.includes('bearish') ||
    s.includes('low') ||
    s.includes('weak') ||
    s.includes('negative') ||
    s.includes('below')
  )
    return 'text-red-600 dark:text-red-400 font-bold';
  return 'text-slate-500 dark:text-slate-400';
};

const BreakdownRow = ({ item }) => {
  const pct = item.max > 0 ? (item.earned / item.max) * 100 : 0;
  const isZero = item.earned === 0;

  return (
    <div className='grid grid-cols-[100px_1fr_44px_80px] items-center gap-4'>
      <div className='text-[11px] font-bold text-text uppercase tracking-tight'>
        {item.label}
      </div>
      <div className='h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden border border-border shadow-inner'>
        <div
          className={`h-full bg-blue-600 rounded-full transition-all duration-700 shadow-[0_0_8px_rgba(37,99,235,0.4)] ${isZero ? 'bg-transparent shadow-none' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className='text-[10px] text-right font-mono'>
        <span className={isZero ? 'text-slate-400' : 'text-text font-black'}>
          {item.earned}
        </span>
        <span className='text-slate-400'>/{item.max}</span>
      </div>
      <div
        className={`text-[10px] truncate font-black uppercase tracking-tight text-right ${getSignalColor(item.signal)}`}
      >
        {item.signal}
      </div>
    </div>
  );
};

export default ScoreBreakdown;
