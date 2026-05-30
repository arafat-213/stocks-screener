# Dashboard Rehaul & Mobile Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve mobile usability by moving filters to a slide-up bottom sheet and finalizing the dashboard layout.

**Architecture:** Use a React component for the bottom sheet with CSS transitions for the slide-up effect. Implement responsive logic in the Dashboard component to switch between inline filters (desktop) and the bottom sheet (mobile).

**Tech Stack:** React, Lucide React (icons), Vanilla CSS.

---

### Task 1: Create FilterBottomSheet Component

**Files:**
- Create: `frontend/src/components/FilterBottomSheet.jsx`
- Create: `frontend/src/components/FilterBottomSheet.css`

- [ ] **Step 1: Implement `FilterBottomSheet.jsx`**

```jsx
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
  if (!isOpen) return null;

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
```

- [ ] **Step 2: Implement `FilterBottomSheet.css`**

```css
.bottom-sheet-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: flex-end;
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s ease;
}

.bottom-sheet-overlay.open {
  opacity: 1;
  visibility: visible;
}

.bottom-sheet-content {
  width: 100%;
  background: var(--color-bg-secondary);
  border-radius: 20px 20px 0 0;
  padding: 24px;
  transform: translateY(100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.bottom-sheet-content.open {
  transform: translateY(0);
}

.bottom-sheet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.bottom-sheet-header .title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bottom-sheet-header h3 {
  font-size: 18px;
  font-weight: 700;
}

.close-btn {
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 4px;
}

.bottom-sheet-body {
  overflow-y: auto;
  flex: 1;
  padding-bottom: 24px;
}

.filter-section {
  margin-bottom: 32px;
}

.filter-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-muted);
  margin-bottom: 16px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header .count {
  font-size: 12px;
  background: var(--color-bg-elevated);
  padding: 2px 8px;
  border-radius: 12px;
  color: var(--color-text-muted);
}

.chip-group {
  display: flex;
  gap: 8px;
}

.chip-group.wrap {
  flex-wrap: wrap;
}

.chip {
  background: var(--color-bg-elevated);
  border: 1px solid transparent;
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  color: var(--color-text);
}

.chip.active {
  background: #ecfdf5;
  color: #059669;
  border-color: #10b981;
  font-weight: 600;
}

.bottom-sheet-footer {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.reset-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: 1px solid var(--color-border);
  padding: 12px 20px;
  border-radius: 12px;
  font-weight: 600;
  cursor: pointer;
}

.apply-btn {
  flex: 1;
  background: var(--color-bullish);
  color: white;
  border: none;
  padding: 12px;
  border-radius: 12px;
  font-weight: 700;
  cursor: pointer;
}
```

- [ ] **Step 3: Commit Task 1**

```bash
git add frontend/src/components/FilterBottomSheet.*
git commit -m "feat: create FilterBottomSheet component for mobile"
```

---

### Task 2: Implement Responsive Dashboard and Bottom Sheet Trigger

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/pages/Dashboard.css`

- [ ] **Step 1: Add responsiveness logic to `Dashboard.jsx`**

```jsx
// Near top of component
const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false);
const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

useEffect(() => {
  const handleResize = () => {
    const mobile = window.innerWidth < 768;
    setIsMobile(mobile);
    if (mobile) setViewMode('grid');
  };
  window.addEventListener('resize', handleResize);
  return () => window.removeEventListener('resize', handleResize);
}, []);
```

- [ ] **Step 2: Update JSX in `Dashboard.jsx`**
  - Import `FilterBottomSheet`.
  - Conditional rendering for `filters-container` (Desktop only).
  - Add "Filter" button to `action-bar` (Mobile only).
  - Wrap filters in `FilterBottomSheet`.

- [ ] **Step 3: Update `Dashboard.css` for mobile responsiveness**
  - Add media queries for `summary-bar`, `action-bar`, and `stock-grid`.

- [ ] **Step 4: Commit Task 2**

```bash
git add frontend/src/pages/Dashboard.*
git commit -m "feat: implement responsive dashboard with mobile filters"
```
