const ScoreBreakdown = ({ breakdown, totalScore }) => {
  const technical = breakdown.filter(b => b.category === 'technical');
  const fundamental = breakdown.filter(b => b.category === 'fundamental');

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-1.5 mb-1">
        <span className="text-xs text-text-muted uppercase tracking-wider">Total Score</span>
        <span className="text-[1.8rem] font-bold text-primary">{totalScore?.toFixed(1)}</span>
        <span className="text-sm text-text-muted">/ 100</span>
      </div>

      <div className="flex flex-col gap-2">
        <div className="text-[0.7rem] uppercase tracking-wider text-text-muted mb-1">Technical <span className="opacity-60">(max 70)</span></div>
        {technical.map(item => <BreakdownRow key={item.label} item={item} />)}
      </div>

      <div className="flex flex-col gap-2">
        <div className="text-[0.7rem] uppercase tracking-wider text-text-muted mb-1">Fundamental <span className="opacity-60">(max 30)</span></div>
        {fundamental.map(item => <BreakdownRow key={item.label} item={item} />)}
      </div>

      <p className="text-[0.7rem] text-text-muted m-0 italic">
        * Pledge and ROCE values may show 0 if cache is outdated.
      </p>
    </div>
  );
};

const BreakdownRow = ({ item }) => {
  const pct = item.max > 0 ? (item.earned / item.max) * 100 : 0;
  const isZero = item.earned === 0;

  return (
    <div className="grid grid-cols-[90px_1fr_44px_80px] items-center gap-2">
      <div className="text-[0.8rem] text-text">{item.label}</div>
      <div className="h-1.5 bg-bg-elevated rounded-sm overflow-hidden">
        <div 
          className={`h-full bg-primary rounded-sm transition-all duration-400 ${isZero ? 'bg-bg-elevated' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-[0.8rem] text-right">
        <span className={isZero ? 'text-text-muted' : 'text-primary font-semibold'}>{item.earned}</span>
        <span className="text-text-muted">/{item.max}</span>
      </div>
      <div className="text-[0.7rem] text-text-muted truncate">{item.signal}</div>
    </div>
  );
};

export default ScoreBreakdown;
