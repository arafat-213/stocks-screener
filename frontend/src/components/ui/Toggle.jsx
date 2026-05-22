import { memo } from 'react';

const Toggle = memo(({ checked, onChange, label, icon: Icon }) => {
  return (
    <div 
      className="group flex justify-between items-center px-3 py-2 bg-bg-secondary border border-border rounded-md cursor-pointer transition-all duration-200 select-none hover:border-primary hover:bg-primary/5 dark:bg-bg-elevated" 
      onClick={() => onChange(!checked)}
    >
      <div className="flex items-center gap-2">
        {Icon && <Icon size={14} className="text-text-muted transition-colors duration-200 group-hover:text-primary" />}
        <span className="text-[0.85rem] font-medium text-text">{label}</span>
      </div>
      <div className={`w-9 h-5 rounded-full relative transition-colors duration-200 ${checked ? 'bg-primary' : 'bg-border'}`}>
        <div className={`w-3.5 h-3.5 bg-white rounded-full absolute top-[3px] left-[3px] transition-transform duration-200 shadow-sm ${checked ? 'translate-x-4' : 'translate-x-0'}`} />
      </div>
    </div>
  );
});

export default Toggle;
