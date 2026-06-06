const ScoreCard = ({ label, scoreData }) => {
  if (!scoreData) {
    return (
      <div className='bg-bg-secondary rounded-lg p-5 border border-border'>
        <h3 className='text-[12px] text-text-muted mb-4 uppercase tracking-widest font-bold'>
          {label} Timeframe
        </h3>
        <div className='flex justify-between items-center'>
          <div className='text-[42px] font-extrabold text-text-muted'>--</div>
          <div className='text-right'>
            <div className='inline-block px-3 py-1.5 rounded-lg text-sm font-bold bg-text-muted/10 text-text-muted'>
              No Signal
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isBullish = scoreData.ema_signal?.toLowerCase() === 'bullish';

  return (
    <div className='bg-bg-secondary rounded-xl p-6 border-2 border-border shadow-sm hover:border-blue-500/30 transition-colors'>
      <h3 className='text-[11px] text-slate-500 dark:text-slate-400 mb-4 uppercase tracking-[0.2em] font-black'>
        {label} Timeframe
      </h3>
      <div className='flex justify-between items-center'>
        <div
          className={`text-5xl font-black ${
            scoreData.score >= 70
              ? 'text-green-500'
              : scoreData.score >= 50
                ? 'text-blue-500'
                : 'text-text'
          }`}
        >
          {scoreData.score?.toFixed(1) || scoreData.score}
        </div>
        <div className='text-right flex flex-col gap-2'>
          <div
            className={`inline-block px-3 py-1.5 rounded-lg text-xs font-black uppercase tracking-wider ${
              isBullish
                ? 'bg-green-500 text-white shadow-lg shadow-green-500/20'
                : 'bg-red-500 text-white shadow-lg shadow-red-500/20'
            }`}
          >
            {scoreData.ema_signal}
          </div>
          <div className='text-[13px] font-mono font-bold text-slate-500 dark:text-slate-400'>
            RSI:{' '}
            <span
              className={
                scoreData.rsi <= 30
                  ? 'text-green-500'
                  : scoreData.rsi >= 70
                    ? 'text-red-500'
                    : 'text-text'
              }
            >
              {scoreData.rsi?.toFixed(1)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScoreCard;
