import './SetupBadge.css';

const SETUP_LABELS = {
  ema_crossover: 'EMA Cross',
  pullback_to_ema20: 'EMA20 Pullback',
  resistance_breakout: 'Breakout',
  trend_continuation: 'Trend',
};

const SetupBadge = ({ setup }) => {
  if (!setup) return null;

  const label = SETUP_LABELS[setup.setup_type] || 'Setup';
  
  return (
    <div className={`setup-badge setup-${setup.setup_type}`}>
      {label}
    </div>
  );
};

export default SetupBadge;
