import { Star } from 'lucide-react';
import './WatchlistStar.css';

const WatchlistStar = ({ symbol, isWatched, onToggle }) => (
  <button
    className={`watchlist-star ${isWatched ? 'watched' : ''}`}
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggle(symbol); }}
    title={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
    aria-label={isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
  >
    <Star size={16} fill={isWatched ? 'currentColor' : 'none'} />
  </button>
);

export default WatchlistStar;
