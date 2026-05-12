import './ScoreBreakdown.css';

const ScoreBreakdown = ({ breakdown, totalScore }) => {
  const technical = breakdown.filter(b => b.category === 'technical');
  const fundamental = breakdown.filter(b => b.category === 'fundamental');

  return (
    <div className="score-breakdown">
      <div className="breakdown-total">
        <span className="breakdown-total-label">Total Score</span>
        <span className="breakdown-total-value">{totalScore?.toFixed(1)}</span>
        <span className="breakdown-total-max">/ 100</span>
      </div>

      <div className="breakdown-section">
        <div className="breakdown-section-label">Technical <span className="muted">(max 70)</span></div>
        {technical.map(item => <BreakdownRow key={item.label} item={item} />)}
      </div>

      <div className="breakdown-section">
        <div className="breakdown-section-label">Fundamental <span className="muted">(max 30)</span></div>
        {fundamental.map(item => <BreakdownRow key={item.label} item={item} />)}
      </div>

      <p className="breakdown-disclaimer">
        * Pledge and ROCE values may show 0 if cache is outdated.
      </p>
    </div>
  );
};

const BreakdownRow = ({ item }) => {
  const pct = item.max > 0 ? (item.earned / item.max) * 100 : 0;
  const isZero = item.earned === 0;

  return (
    <div className="breakdown-row">
      <div className="breakdown-row-label">{item.label}</div>
      <div className="breakdown-bar-container">
        <div 
          className={`breakdown-bar-fill ${isZero ? 'zero' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="breakdown-row-pts">
        <span className={isZero ? 'muted' : 'earned'}>{item.earned}</span>
        <span className="muted">/{item.max}</span>
      </div>
      <div className="breakdown-row-signal muted">{item.signal}</div>
    </div>
  );
};

export default ScoreBreakdown;
