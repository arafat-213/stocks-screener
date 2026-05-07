# Frontend Design Rehaul (Pro Terminal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rehaul the stock-ai frontend into a professional, system-adaptive "Pro Terminal" with a hybrid table/card dashboard and full mobile responsiveness.

**Architecture:** A responsive layout shell with a fixed desktop sidebar and mobile bottom navigation. Uses CSS custom properties for system-aware theming and a CSS Grid-based market table for high-density data.

**Tech Stack:** React, CSS Modules (or vanilla CSS variables), Lucide React, lightweight-charts.

---

### Task 1: Design Tokens & Global CSS

**Files:**
- Modify: `frontend/src/index.css`
- Modify: `frontend/index.html` (for font pre-loading)

- [ ] **Step 1: Add Google Fonts to index.html**
Update `<head>` to include Plus Jakarta Sans, Inter, and JetBrains Mono with `font-display: swap`.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&family=Plus+Jakarta+Sans:wght@700;800&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Define CSS Variables in index.css**
Implement the "inverted hierarchy" tokens.

```css
:root {
  --color-bg: #FAFAFA;
  --color-bg-secondary: #FFFFFF;
  --color-bg-elevated: #F0F2F1;
  --color-text: #111827;
  --color-text-muted: #6B7280;
  --color-border: #E5E7EB;
  --color-bullish: #10B981;
  --color-bearish: #F43F5E;
  
  --font-main: 'Inter', sans-serif;
  --font-heading: 'Plus Jakarta Sans', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  
  --radius-standard: 12px;
  --radius-dense: 8px;
}

[data-theme="dark"] {
  --color-bg: #0A0A0A;
  --color-bg-secondary: #161616;
  --color-bg-elevated: #1F1F1F;
  --color-text: #FFFFFF;
  --color-text-muted: #9CA3AF;
  --color-border: #2B2B43;
}
```

- [ ] **Step 3: Apply Global Base Styles**
Update `body` and `button` styles to use the new tokens.

- [ ] **Step 4: Commit**
`git add frontend/src/index.css frontend/index.html && git commit -m "style: define Pro Terminal design tokens and fonts"`

---

### Task 2: Theme Detection & Root Shell

**Files:**
- Modify: `frontend/src/App.jsx`
- Create: `frontend/src/hooks/useTheme.js`

- [ ] **Step 1: Create useTheme hook**
Implement system preference detection and listener.

```javascript
import { useState, useEffect } from 'react';

export const useTheme = () => {
  const [isDark, setIsDark] = useState(window.matchMedia('(prefers-color-scheme: dark)').matches);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const listener = (e) => setIsDark(e.matches);
    media.addEventListener('change', listener);
    
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    
    return () => media.removeEventListener('change', listener);
  }, [isDark]);

  return { isDark };
};
```

- [ ] **Step 2: Integrate into App.jsx**
Apply the hook at the root level.

- [ ] **Step 3: Commit**
`git add frontend/src/hooks/useTheme.js frontend/src/App.jsx && git commit -m "feat: implement system-aware theme detection"`

---

### Task 3: Responsive Navigation Shell

**Files:**
- Create: `frontend/src/components/Navigation.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx` (remove existing sidebar)

- [ ] **Step 1: Create Navigation Component**
Implement Desktop Sidebar (slim-responsive) and Mobile Bottom Nav.

```javascript
// Navigation.jsx
// Desktop: <aside className="desktop-sidebar">
// Mobile: <nav className="mobile-bottom-nav">
```

- [ ] **Step 2: Add CSS for Navigation**
Implement the Emerald top border for active mobile tabs and tooltips for slim sidebar.

- [ ] **Step 3: Commit**
`git add frontend/src/components/Navigation.jsx && git commit -m "feat: add responsive navigation shell"`

---

### Task 4: Market Table Component

**Files:**
- Create: `frontend/src/components/MarketTable.jsx`
- Create: `frontend/src/components/MarketTable.css`

- [ ] **Step 1: Implement MarketTable.jsx**
Use `display: grid` with the explicit column widths.

```css
.market-table-grid {
  display: grid;
  grid-template-columns: 140px 100px 80px 70px 70px 100px 70px 1fr;
}
```

- [ ] **Step 2: Add Signal Indicators**
Use `::before` pseudo-elements for EMA/RSI signal dots.

- [ ] **Step 3: Implement Table Skeletons**
Ensure skeletons match the grid column template exactly.

- [ ] **Step 4: Commit**
`git add frontend/src/components/MarketTable.* && git commit -m "feat: implement high-density Market Table component"`

---

### Task 5: Dashboard Rehaul & Mobile Filters

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Create: `frontend/src/components/FilterBottomSheet.jsx`

- [ ] **Step 1: Implement View Toggle**
Add the Table/Card toggle in the header (right-aligned).

- [ ] **Step 2: Create FilterBottomSheet**
Implement the slide-up sheet for mobile filters.

- [ ] **Step 3: Integrate MarketTable**
Switch between `MarketTable` and `StockCard` grid based on toggle state.

- [ ] **Step 4: Commit**
`git add frontend/src/pages/Dashboard.jsx frontend/src/components/FilterBottomSheet.jsx && git commit -m "feat: rehaul dashboard with hybrid view and mobile filters"`

---

### Task 6: Stock Detail Page Fix

**Files:**
- Modify: `frontend/src/pages/StockDetail.jsx`
- Modify: `frontend/src/pages/StockDetail.css`
- Modify: `frontend/src/components/CandlestickChart.jsx`

- [ ] **Step 1: Update Layout to Split View**
Implement the split view for desktop and vertical stack for mobile.

- [ ] **Step 2: Fix Contrast**
Apply the new CSS variables to all text and container backgrounds.

- [ ] **Step 3: Theme-Aware lightweight-charts**
Update `CandlestickChart.jsx` to pass dynamic colors based on the current theme.

```javascript
// Inside CandlestickChart.jsx
const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
// Pass to createChart config...
```

- [ ] **Step 4: Commit**
`git add frontend/src/pages/StockDetail.* frontend/src/components/CandlestickChart.jsx && git commit -m "fix: resolve StockDetail contrast and implement split view"`

---

### Task 7: Verification & Polishing

- [ ] **Step 1: Verify Responsiveness**
Test layout at 375px (mobile), 768px (tablet), and 1440px (desktop).

- [ ] **Step 2: Verify Theme Switch**
Manually toggle system theme and verify all components (including charts) update correctly.

- [ ] **Step 3: Final Commit**
`git commit -m "chore: final polish and responsiveness verification"`
