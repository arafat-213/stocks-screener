import { Star } from 'lucide-react';

const WatchlistStar = ({ symbol, isWatched, onToggle }) => (
  <button
    className={`bg-none border-none cursor-pointer p-1 rounded-sm flex items-center transition-all duration-150 hover:text-blue-500 hover:scale-125 ${isWatched ? 'text-blue-500' : 'text-slate-400'}`}
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle(symbol); }}
    title={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
    aria-label={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
  >
    <Star size={16} fill={isWatched ? 'currentColor' : 'none'} />
  </button>
);

export default WatchlistStar;
