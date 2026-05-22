# Tailwind CSS Migration Design Specification

## Overview
This document outlines the strategy for migrating the Stock AI frontend from custom CSS (component-specific `.css` files and global `index.css`) to a utility-first approach using Tailwind CSS. The goal is to preserve the exact existing layout, theme switching, and visual design while eliminating all custom CSS files.

## Approach
The migration will follow a **Design System Mapping** approach. We will first configure Tailwind to understand the existing design tokens (colors, spacing, typography) and then systematically replace global utilities and component-specific styles with inline Tailwind classes.

## Section 1: Foundation (Tailwind Setup & Config Mapping)

1.  **Installation:** Install `tailwindcss`, `postcss`, and `autoprefixer` in `frontend/`.
2.  **Configuration (`tailwind.config.js`):**
    *   Set up content paths (`'./index.html', './src/**/*.{js,ts,jsx,tsx}'`).
    *   Configure dark mode to support the existing application logic (e.g., `darkMode: ['class', '[data-theme="dark"]']`).
    *   **Theme Extension:**
        *   **Colors:** Map semantic variables (`--color-bg`, `--color-primary`, `--color-bullish`, etc.) to Tailwind configuration (e.g., `colors: { background: 'var(--color-bg)', primary: 'var(--color-primary)' }`).
        *   **Typography:** Map `--font-main` and `--font-mono` to `fontFamily.sans` and `fontFamily.mono`.
        *   **Border Radius:** Map `--radius-*` variables.
        *   **Shadows:** Map `--shadow-*` variables.
3.  **Entry Point (`index.css`):**
    *   Add `@tailwind base; @tailwind components; @tailwind utilities;`.
    *   Retain the root CSS variables for theme switching to minimize disruption to existing logic.

## Section 2: Global Utilities and Base Elements

1.  **Base Elements (`@layer base`):**
    *   Migrate element-level styling (e.g., global `input`, `select`, `textarea` padding and borders, scrollbar styling) into Tailwind's `@layer base` within `index.css` to ensure consistent defaults across the application without repeating classes on every input.
2.  **Global Utility Classes Migration:**
    *   Perform a project-wide search and replace for global utility classes defined in `index.css` (e.g., `.flex`, `.flex-col`, `.items-center`, `.gap-2`, `.text-bullish`).
    *   Replace them with exact Tailwind equivalents in JSX (e.g., `className="flex flex-col items-center gap-2 text-bullish"`).
3.  **Complex Utilities (`.card`, `.glass`):**
    *   Replace instances of `.card` and `.glass` in JSX with their expanded utility string equivalents.
    *   Example: `.card` becomes `bg-bg-secondary border border-border rounded-lg shadow-sm`.
    *   Remove these definitions from `index.css` once fully migrated.

## Section 3: Component-Specific CSS Migration

1.  **Iterative Conversion:**
    *   Process remaining component `.css` files (e.g., `Dashboard.css`, `StockCard.css`) iteratively.
    *   Translate specific class rules (including hover, focus, disabled states, and media queries) into inline Tailwind utilities.
    *   Apply these utility strings directly to the corresponding JSX elements.
2.  **Cleanup:**
    *   Remove the CSS import statement (e.g., `import './Dashboard.css'`) from the component file.
    *   Delete the `.css` file.
3.  **Animations & Complex States:**
    *   Migrate keyframe animations (e.g., `.spin`, `.fade-in`) to `tailwind.config.js` under `theme.extend.animation` and `theme.extend.keyframes`.
    *   Manage complex state-based styling (e.g., active tabs, dynamic status badges) within JSX using template literals to conditionally apply Tailwind utility classes.
