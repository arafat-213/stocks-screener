import { memo } from 'react';

const Slider = memo(({ value, onChange, min = 0, max = 100, step = 1, label, className = "" }) => {
  return (
    <div className={`w-full relative pb-2 ${className}`}>
      {label && (
        <div className="flex justify-between items-center mb-3">
          <label className="text-[0.75rem] font-bold uppercase text-text-muted tracking-wider">{label}</label>
          <span className="text-[0.85rem] font-bold text-primary bg-primary/10 px-2 py-0.5 rounded font-mono">{value}</span>
        </div>
      )}
      <input 
        type="range" 
        min={min} 
        max={max} 
        step={step}
        value={value} 
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="appearance-none w-full h-1.5 bg-border rounded-full outline-none cursor-pointer relative z-[2] dark:bg-white/10 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-[18px] [&::-webkit-slider-thumb]:w-[18px] [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-primary [&::-webkit-slider-thumb]:mt-[-6px] [&::-webkit-slider-thumb]:shadow-sm [&::-webkit-slider-thumb]:transition-all [&::-webkit-slider-thumb]:duration-150 [&::-webkit-slider-thumb]:z-[3] [&::-webkit-slider-thumb]:hover:shadow-md [&::-webkit-slider-thumb]:active:scale-110 [&::-webkit-slider-thumb]:active:bg-primary [&::-webkit-slider-thumb]:active:border-white dark:[&::-webkit-slider-thumb]:bg-bg-secondary"
      />
      <div 
        className="absolute bottom-[8px] left-0 h-1.5 bg-primary rounded-full pointer-events-none z-[1]" 
        style={{ width: `${((value - min) / (max - min)) * 100}%` }}
      ></div>
    </div>
  );
});

export default Slider;
