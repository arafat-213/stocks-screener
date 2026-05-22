import { memo } from 'react';

const Slider = memo(({ value, onChange, min = 0, max = 100, step = 1, label, className = "" }) => {
  return (
    <div className={`w-full relative pb-4 ${className}`}>
      {label && (
        <div className="flex justify-between items-center mb-4">
          <label className="text-[10px] font-black uppercase text-slate-500 dark:text-slate-400 tracking-[0.2em]">{label}</label>
          <span className="text-sm font-black text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-3 py-1 rounded-lg font-mono shadow-sm border border-blue-100 dark:border-blue-900/50">{value}</span>
        </div>
      )}
      <div className="relative h-2 w-full bg-slate-100 dark:bg-slate-800 rounded-full border border-border">
          <input 
            type="range" 
            min={min} 
            max={max} 
            step={step}
            value={value} 
            onChange={(e) => onChange(parseFloat(e.target.value))}
            className="absolute inset-0 appearance-none w-full h-full bg-transparent outline-none cursor-pointer z-20 
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-6 [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:rounded-full 
              [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-blue-600 [&::-webkit-slider-thumb]:shadow-xl 
              [&::-webkit-slider-thumb]:hover:scale-110 [&::-webkit-slider-thumb]:active:scale-95 [&::-webkit-slider-thumb]:transition-all"
          />
          <div 
            className="absolute top-0 left-0 h-full bg-blue-600 rounded-full z-10 shadow-[0_0_12px_rgba(37,99,235,0.4)]" 
            style={{ width: `${((value - min) / (max - min)) * 100}%` }}
          ></div>
      </div>
    </div>
  );
});

export default Slider;
