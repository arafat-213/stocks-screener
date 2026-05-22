import { memo } from 'react';

const Toggle = memo(({ checked, onChange, label, icon: Icon }) => {
  return (
    <div 
      className={`group flex justify-between items-center px-4 py-3 bg-bg-secondary border-2 rounded-xl cursor-pointer transition-all duration-300 select-none shadow-sm ${checked ? 'border-blue-600 bg-blue-50 dark:bg-blue-900/10' : 'border-border hover:border-blue-500'}`} 
      onClick={() => onChange(!checked)}
    >
      <div className="flex items-center gap-3">
        {Icon && <Icon size={16} className={`transition-colors duration-300 ${checked ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 group-hover:text-blue-500'}`} />}
        <span className={`text-[11px] font-black uppercase tracking-wider transition-colors ${checked ? 'text-blue-700 dark:text-blue-300' : 'text-slate-500 dark:text-slate-400'}`}>{label}</span>
      </div>
      <div className={`w-10 h-6 rounded-full relative transition-colors duration-300 ${checked ? 'bg-blue-600 shadow-[0_0_8px_rgba(37,99,235,0.4)]' : 'bg-slate-200 dark:bg-slate-800'}`}>
        <div className={`w-4 h-4 bg-white rounded-full absolute top-[4px] left-[4px] transition-transform duration-300 shadow-lg ${checked ? 'translate-x-4' : 'translate-x-0'}`} />
      </div>
    </div>
  );
});

export default Toggle;
