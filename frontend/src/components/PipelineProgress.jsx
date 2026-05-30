const PipelineProgress = ({ fetched, scored, total, tier1Count }) => {
  // Phase 1: Fetching (0% to 50% of bar)
  // Phase 2: Scoring (50% to 100% of bar)
  // Use tier1_count as the denominator for scoring phase if total unknown

  const fetchPct = total > 0 ? Math.min((fetched / total) * 100, 100) : 0;
  // eslint-disable-next-line no-unused-vars
  const scorePct =
    tier1Count > 0 ? Math.min((scored / tier1Count) * 100, 100) : 0;

  // Overall: fetching is first half, scoring is second half
  const overallPct =
    total > 0
      ? Math.min(
          (fetched / total) * 50 + (scored / Math.max(tier1Count, 1)) * 50,
          100
        )
      : fetchPct;

  return (
    <div className='w-full mt-4'>
      <div className='h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden border border-border shadow-inner'>
        <div
          className='h-full bg-blue-600 rounded-full transition-[width] duration-700 ease-in-out shadow-[0_0_8px_rgba(37,99,235,0.5)]'
          style={{ width: `${overallPct}%` }}
        />
      </div>
      <div className='flex justify-between items-center text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mt-2'>
        <div className='flex gap-3'>
          <span>
            FETCH:{' '}
            <span className='text-text'>
              {fetched}
              {total > 0 ? `/${total}` : ''}
            </span>
          </span>
          <span>
            SCORE:{' '}
            <span className='text-blue-500'>
              {scored}
              {tier1Count > 0 ? `/${tier1Count}` : ''}
            </span>
          </span>
        </div>
        <span className='bg-blue-600 text-white px-2 py-0.5 rounded-lg shadow-sm'>
          {overallPct.toFixed(0)}%
        </span>
      </div>
    </div>
  );
};

export default PipelineProgress;
