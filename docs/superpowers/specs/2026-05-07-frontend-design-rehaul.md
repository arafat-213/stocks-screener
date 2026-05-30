# Design Spec: Frontend Design Rehaul (Pro Terminal)

**Date:** 2026-05-07
**Topic:** Frontend Design, Responsiveness, and Theming
**Status:** Draft

## 1. Goal
Rehaul the `stock-ai` frontend to provide a professional, high-density "Pro Terminal" experience that is fully mobile-responsive and supports system-adaptive light/dark modes.

## 2. Visual Identity & Design System

### 2.1 Color Tokens
The design uses an "inverted hierarchy" where row/card elements are lighter than the page background in light mode, and darker in dark mode.

| Token | Light Mode | Dark Mode | Usage |
| :--- | :--- | :--- | :--- |
| `--color-bg` | `#FAFAFA` | `#0A0A0A` | Page background |
| `--color-bg-secondary` | `#FFFFFF` | `#161616` | Cards, Table Rows, Sidebar |
| `--color-bg-elevated` | `#F0F2F1` | `#1F1F1F` | Hover states, Secondary elements |
| `--color-text` | `#111827` | `#FFFFFF` | Primary text |
| `--color-text-muted` | `#6B7280` | `#9CA3AF` | Muted/Secondary labels |
| `--color-border` | `#E5E7EB` | `#2B2B43` | Borders |
| `--color-bullish` | `#10B981` | `#10B981` | Positive change, Bullish signals |
| `--color-bearish` | `#F43F5E` | `#F43F5E` | Negative change, Bearish signals |

### 2.2 Typography
- **Headlines:** `Plus Jakarta Sans`
- **Body:** `Inter`
- **Metrics/Numbers:** `JetBrains Mono` (Monospace for alignment in tables)
- **Constraint:** Load via a single `@import` with `font-display: swap`.

### 2.3 Styling
- **Borders:** 1px solid `--color-border`. Avoid heavy shadows.
- **Radius:** `--radius-standard: 12px` (Cards), `--radius-dense: 8px` (Table rows).

## 3. Layout & Navigation

### 3.1 Responsive Shell
- **Desktop (>= 1024px):** Fixed left sidebar (260px).
- **Tablet (768px - 1024px):** Icon-only sidebar with `title` tooltips on hover.
- **Mobile (< 768px):**
    - Bottom Navigation Bar: `[Dashboard, Screener, Reports]`.
    - Active state: Emerald (`--color-bullish`) top border.
    - Filter Drawer: Slide-up "Bottom Sheet" for sectors and pipeline controls.

### 3.2 Dashboard Header
- Left: Page title + Key Summary Stats (Total Scored, 3/3 Confluence).
- Right: Table/Card View Toggle.

## 4. Components

### 4.1 Market Table (Desktop Default)
- **Grid Layout:** `display: grid` with fixed column widths:
  ```css
  grid-template-columns: 140px 100px 80px 70px 70px 100px 70px 1fr;
  ```
- **Sticky Header:** Top row stays fixed on scroll.
- **Signal Indicators:** EMA/RSI cells use `::before` pseudo-element dots for visual signals.
- **Skeletons:** Must match grid column template exactly to prevent layout shift.

### 4.2 Enhanced Stock Card (Gallery/Mobile View)
- Prominent 3/3 Confluence badge in top-right.
- Mono-spaced metrics for price and technical scores.
- Subtle 1px border shift on hover.

### 4.3 Stock Detail Page
- **Desktop:** Split view (Chart left, Stats right).
- **Mobile:** Vertical stack.
- **Chart Panel:** Min-height 400px; `height: calc(100vh - 120px)`.
- **Contrast Fix:** Apply `--color-text` and `--color-bg` tokens to resolve white-on-white bug.

## 5. Technical Requirements

### 5.1 Theme Awareness
- Root attribute: `html[data-theme="dark"]`.
- **Theme Detection:** On app init, read `window.matchMedia('(prefers-color-scheme: dark)')` and set `document.documentElement.setAttribute('data-theme', ...)` accordingly. Listen for changes with `addEventListener('change', ...)`.
- **Chart.js / lightweight-charts:** Must pass explicit background/text colors derived from current theme state to `createChart()`:
  ```js
  createChart(container, {
    layout: {
      background: { color: isDark ? '#161616' : '#FFFFFF' },
      textColor: isDark ? '#FFFFFF' : '#111827' },
    },
    grid: {
      vertLines: { color: isDark ? '#1F1F1F' : '#F0F2F1' },
      horzLines: { color: isDark ? '#1F1F1F' : '#F0F2F1' },
    }
  })
  ```

### 5.2 Performance
- `React.memo` for table rows and cards.
- Stable props: Ensure filtered/sorted data is memoized with `useMemo` at the page level.

### 5.3 Animations
- Mobile Filter Sheet: Slide-up CSS transition.
- View Toggle: Subtle cross-fade between Table and Grid.
