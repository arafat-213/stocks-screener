import { Target, ShieldAlert, Zap } from 'lucide-react';
import './TradingPlan.css';

const TradingPlan = ({ setup }) => {
  if (!setup) return null;

  return (
    <div className="trading-plan-card">
      <div className="plan-header">
        <Zap size={18} className="text-primary" />
        <h3>Trading Plan: {setup.setup_type.replace(/_/g, ' ')}</h3>
      </div>

      <div className="plan-grid">
        <div className="plan-item entry">
          <label>Entry Zone</label>
          <div className="value">
            ₹{setup.entry_zone.low.toFixed(2)} - ₹
            {setup.entry_zone.high.toFixed(2)}
          </div>
        </div>

        <div className="plan-item stop">
          <label>
            <ShieldAlert size={14} /> Stop Loss
          </label>
          <div className="value bearish">₹{setup.stop_loss.toFixed(2)}</div>
          <span className="basis">{setup.stop_basis}</span>
        </div>

        <div className="plan-targets">
          <label>
            <Target size={14} /> Targets (R-Multiple)
          </label>
          <div className="target-list">
            {setup.targets.map((t, i) => (
              <div key={i} className="target-pill">
                <span className="rr">{t.rr}R</span>
                <span className="price">₹{t.level.toFixed(2)}</span>
                <span className="target-label">{t.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="plan-footer">
        <span>Risk per share: ₹{setup.risk_per_share.toFixed(2)}</span>
        <span>ATR: {setup.atr.toFixed(1)}</span>
      </div>
    </div>
  );
};

export default TradingPlan;
