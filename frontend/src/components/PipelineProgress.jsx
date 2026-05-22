const PipelineProgress = ({ fetched, scored, total, tier1Count }) => {
  // Phase 1: Fetching (0% to 50% of bar)
  // Phase 2: Scoring (50% to 100% of bar)
  // Use tier1_count as the denominator for scoring phase if total unknown
  
  const fetchPct = total > 0 ? Math.min((fetched / total) * 100, 100) : 0;
  // eslint-disable-next-line no-unused-vars
  const scorePct = tier1Count > 0 ? Math.min((scored / tier1Count) * 100, 100) : 0;
  
  // Overall: fetching is first half, scoring is second half
  const overallPct = total > 0 
    ? Math.min(((fetched / total) * 50) + (scored / Math.max(tier1Count, 1)) * 50, 100)
    : fetchPct;

  return (
    <div className="w-full mt-2">
      <div className="h-1 bg-bg-elevated rounded-sm overflow-hidden">
        <div 
          className="h-full bg-bullish rounded-sm transition-[width] duration-500 ease-in-out"
          style={{ width: `${overallPct}%` }}
        />
      </div>
      <div className="flex justify-between text-[0.7rem] text-text-muted mt-1">
        <span>Fetch: {fetched}{total > 0 ? `/${total}` : ''}</span>
        <span>{overallPct.toFixed(0)}%</span>
        <span>Score: {scored}{tier1Count > 0 ? `/${tier1Count}` : ''}</span>
      </div>
    </div>
  );
};

export default PipelineProgress;
