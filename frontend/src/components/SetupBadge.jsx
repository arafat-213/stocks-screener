const SETUP_LABELS = {
  ema_crossover: 'EMA Cross',
  pullback_to_ema20: 'EMA20 Pullback',
  resistance_breakout: 'Breakout',
  trend_continuation: 'Trend',
};

const SetupBadge = ({ setup }) => {
  if (!setup) return null;

  const label = SETUP_LABELS[setup.setup_type] || 'Setup';

  const typeClasses = {
    ema_crossover: 'bg-blue-500/15 text-blue-500',
    pullback_to_ema20: 'bg-emerald-500/15 text-emerald-500',
    resistance_breakout: 'bg-amber-500/15 text-amber-500',
    trend_continuation: 'bg-gray-500/15 text-gray-500',
  };

  const typeClass = typeClasses[setup.setup_type] || 'bg-gray-500/15 text-gray-500';
  
  return (
    <div className={`inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold uppercase tracking-tight ${typeClass}`}>
      {label}
    </div>
  );
};

export default SetupBadge;
