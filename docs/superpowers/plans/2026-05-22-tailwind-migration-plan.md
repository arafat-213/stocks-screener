# Tailwind CSS Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the frontend from custom CSS to Tailwind CSS while maintaining 100% visual parity and eliminating all `.css` files.

**Architecture:** Design System Mapping. Configure Tailwind theme to match existing CSS variables, then systematically replace custom classes with Tailwind utilities in JSX.

**Tech Stack:** React, Tailwind CSS, PostCSS, Autoprefixer.

---

### Task 1: Setup Tailwind Foundation

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Install dependencies**
Run: `cd frontend && npm install -D tailwindcss postcss autoprefixer`

- [ ] **Step 2: Initialize Tailwind**
Run: `cd frontend && npx tailwindcss init -p`

- [ ] **Step 3: Configure `tailwind.config.js`**
Update `frontend/tailwind.config.js` with existing design tokens:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        background: 'var(--color-bg)',
        'bg-secondary': 'var(--color-bg-secondary)',
        'bg-elevated': 'var(--color-bg-elevated)',
        text: 'var(--color-text)',
        'text-muted': 'var(--color-text-muted)',
        border: 'var(--color-border)',
        primary: 'var(--color-primary)',
        bullish: 'var(--color-bullish)',
        bearish: 'var(--color-bearish)',
        warning: 'var(--color-warning)',
      },
      fontFamily: {
        sans: ['var(--font-main)', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      borderRadius: {
        xl: 'var(--radius-xl)',
        lg: 'var(--radius-lg)',
        md: 'var(--radius-md)',
        sm: 'var(--radius-sm)',
      },
      animation: {
        spin: 'spin 1s linear infinite',
        'fade-in': 'fadeIn 0.4s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        }
      }
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Update `index.css`**
Add tailwind directives at the top of `frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
/* ... keep :root and [data-theme="dark"] variables ... */
```

- [ ] **Step 5: Verify setup**
Start dev server: `npm run dev` and ensure page still loads correctly (Tailwind Base resets might shift things slightly, which we'll fix in Task 2).

- [ ] **Step 6: Commit**
`git add frontend/package.json frontend/tailwind.config.js frontend/postcss.config.js frontend/src/index.css && git commit -m "chore: setup tailwind foundation"`

---

### Task 2: Global Utilities and Base Layer

**Files:**
- Modify: `frontend/src/index.css`
- Modify: All components (Search & Replace)

- [ ] **Step 1: Move base styles to `@layer base`**
In `index.css`, wrap existing global element styles (body, h1-h6, button, input, etc.) in `@layer base`.

- [ ] **Step 2: Replace global utility classes project-wide**
Search and replace the following patterns in all `src/**/*.{jsx,js}`:
- `className="flex"` -> `className="flex"` (no change needed but verify)
- `className="flex-col"` -> `className="flex flex-col"`
- `className="items-center"` -> `className="items-center"`
- `className="justify-between"` -> `className="justify-between"`
- `className="gap-2"` -> `className="gap-2"`
- `className="text-bullish"` -> `className="text-bullish"` (using our custom color)
- `className="text-muted"` -> `className="text-text-muted"`

- [ ] **Step 3: Replace `.card` and `.glass` classes**
Find all usages of `className="card"` and replace with `className="bg-bg-secondary border border-border rounded-lg shadow-sm"`.
Find all usages of `className="glass"` and replace with `className="bg-bg-secondary/70 backdrop-blur-md border border-border"`.

- [ ] **Step 4: Remove utilities from `index.css`**
Delete the `.flex`, `.card`, `.glass`, etc., class definitions from `index.css`.

- [ ] **Step 5: Commit**
`git add . && git commit -m "style: migrate global utilities to tailwind"`

---

### Task 3: Migrate Layout and App Components

**Files:**
- Modify: `frontend/src/components/MainLayout.jsx`
- Delete: `frontend/src/components/MainLayout.css`
- Modify: `frontend/src/App.jsx`
- Delete: `frontend/src/App.css`

- [ ] **Step 1: Migrate `MainLayout.jsx`**
Translate all classes in `MainLayout.css` to inline Tailwind classes in `MainLayout.jsx`. Remove the CSS import.

- [ ] **Step 2: Migrate `App.jsx`**
Translate any styles from `App.css` and remove the import. Delete `App.css`.

- [ ] **Step 3: Commit**
`git add . && git commit -m "style: migrate layout and app components to tailwind"`

---

### Task 4: Migrate Dashboard Page and Summary Components

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Delete: `frontend/src/pages/Dashboard.css`
- Modify: `frontend/src/components/PipelineProgress.jsx`
- Delete: `frontend/src/components/PipelineProgress.css`

- [ ] **Step 1: Migrate `Dashboard.jsx`**
Focus on the complex grid layouts and summary bar. Translate media queries to Tailwind prefixes (`sm:`, `lg:`).

- [ ] **Step 2: Migrate `PipelineProgress.jsx`**
Handle the progress bar animations using Tailwind.

- [ ] **Step 3: Commit**
`git add . && git commit -m "style: migrate dashboard page to tailwind"`

---

### Task 5: Migrate Stock and Market Components

**Files:**
- Modify: `frontend/src/components/StockCard.jsx`, `MarketTable.jsx`, `ScoreBreakdown.jsx`
- Delete: Corresponding `.css` files.

- [ ] **Step 1: Migrate `StockCard.jsx`**
- [ ] **Step 2: Migrate `MarketTable.jsx`** (Handle table hover states and borders)
- [ ] **Step 3: Migrate `ScoreBreakdown.jsx`**

- [ ] **Step 4: Commit**
`git add . && git commit -m "style: migrate stock and market components to tailwind"`

---

### Task 6: Final Cleanup and Remaining Components

**Files:**
- Modify: Remaining UI components (Button, Select, Slider, Toggle, etc.)
- Delete: All remaining `.css` files in `frontend/src/`.

- [ ] **Step 1: Migrate UI primitive components**
- [ ] **Step 2: Migrate remaining pages** (Backtest, System, StockDetail)
- [ ] **Step 3: Final check for unused CSS imports**
- [ ] **Step 4: Delete all converted `.css` files**
- [ ] **Step 5: Verify light/dark theme toggle still works perfectly**

- [ ] **Step 6: Commit**
`git add . && git commit -m "style: complete tailwind migration and cleanup"`
