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
    ema_crossover: 'bg-primary/15 text-primary',
    pullback_to_ema20: 'bg-green-500/15 text-green-600 dark:text-green-400',
    resistance_breakout: 'bg-warning/15 text-warning',
    trend_continuation: 'bg-text-muted/15 text-text-muted',
  };

  const typeClass = typeClasses[setup.setup_type] || 'bg-text-muted/15 text-text-muted';
  
  return (
    <div className={`inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold uppercase tracking-tight ${typeClass}`}>
      {label}
    </div>
  );
};

export default SetupBadge;
