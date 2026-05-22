import { Target, ShieldAlert, Zap } from 'lucide-react';

const TradingPlan = ({ setup }) => {
  if (!setup) return null;

  return (
    <div className="bg-bg-secondary border border-border rounded-lg p-4 mt-4 shadow-sm">
      <div className="flex items-center gap-2 mb-4 capitalize font-semibold">
        <Zap size={18} className="text-primary" />
        <h3 className="text-text">Trading Plan: {setup.setup_type.replace(/_/g, ' ')}</h3>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="flex flex-col">
          <label className="flex items-center gap-1 text-[0.75rem] text-text-muted mb-1">Entry Zone</label>
          <div className="text-[1.1rem] font-bold font-mono text-text">
            ₹{setup.entry_zone.low.toFixed(2)} - ₹
            {setup.entry_zone.high.toFixed(2)}
          </div>
        </div>

        <div className="flex flex-col">
          <label className="flex items-center gap-1 text-[0.75rem] text-text-muted mb-1">
            <ShieldAlert size={14} /> Stop Loss
          </label>
          <div className="text-[1.1rem] font-bold font-mono text-bearish">₹{setup.stop_loss.toFixed(2)}</div>
          <span className="text-[0.7rem] text-text-muted">{setup.stop_basis}</span>
        </div>

        <div className="col-span-2">
          <label className="flex items-center gap-1 text-[0.75rem] text-text-muted mb-1">
            <Target size={14} /> Targets (R-Multiple)
          </label>
          <div className="flex flex-wrap gap-3">
            {setup.targets.map((t, i) => (
              <div key={i} className="flex flex-col bg-primary/5 p-2 md:px-3 md:py-2 rounded-md border border-primary/20">
                <span className="text-[0.7rem] font-semibold text-bullish">{t.rr}R</span>
                <span className="font-bold font-mono text-text">₹{t.level.toFixed(2)}</span>
                <span className="text-[0.65rem] opacity-70 text-text-muted">{t.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex justify-between text-[0.75rem] text-text-muted border-t border-border pt-3">
        <span>Risk per share: ₹{setup.risk_per_share.toFixed(2)}</span>
        <span>ATR: {setup.atr.toFixed(1)}</span>
      </div>
    </div>
  );
};

export default TradingPlan;
