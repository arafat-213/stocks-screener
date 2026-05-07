import { X, Filter, RotateCcw } from 'lucide-react';
import './FilterBottomSheet.css';

const FilterBottomSheet = ({ 
  isOpen, 
  onClose, 
  confluenceFilter, 
  setConfluenceFilter, 
  availableSectors, 
  selectedSectors, 
  toggleSector, 
  resetFilters 
}) => {
  // We keep it in DOM but hidden for animations to work smoothly
  return (
    <div className={`bottom-sheet-overlay ${isOpen ? 'open' : ''}`} onClick={onClose}>
      <div className={`bottom-sheet-content ${isOpen ? 'open' : ''}`} onClick={e => e.stopPropagation()}>
        <div className="bottom-sheet-header">
          <div className="title">
            <Filter size={18} />
            <h3>Filters</h3>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={24} />
          </button>
        </div>

        <div className="bottom-sheet-body">
          <div className="filter-section">
            <h4>Confluence</h4>
            <div className="chip-group">
              {['all', '3', '2+'].map(c => (
                <button 
                  key={c} 
                  className={`chip ${confluenceFilter === c ? 'active' : ''}`}
                  onClick={() => setConfluenceFilter(c)}
                >
                  {c === 'all' ? 'All Stocks' : c === '3' ? '3/3 Only' : '2/3+'}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-section">
            <div className="section-header">
              <h4>Sectors</h4>
              <span className="count">{availableSectors.length}</span>
            </div>
            <div className="chip-group wrap">
              {availableSectors.map(sector => (
                <button 
                  key={sector} 
                  className={`chip ${selectedSectors.includes(sector) ? 'active' : ''}`}
                  onClick={() => toggleSector(sector)}
                >
                  {sector}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="bottom-sheet-footer">
          <button className="reset-btn" onClick={resetFilters}>
            <RotateCcw size={16} />
            Reset
          </button>
          <button className="apply-btn" onClick={onClose}>
            Apply Filters
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilterBottomSheet;
