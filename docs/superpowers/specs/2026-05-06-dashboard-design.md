# Stock AI Dashboard Design

## Overview
A redesign of the Stock AI frontend to replace the basic HTML look with a "Terminal Aesthetic" – a professional, high-density interface inspired by financial platforms like Bloomberg.

## Aesthetic & Theming
- **Theme**: Financial/Professional. High contrast, clean lines, minimal use of gradients.
- **Typography**: System sans-serif for general text, monospace for data values to ensure alignment and readability.
- **Color Palette**:
  - Background: Clean white (light mode) or deep gray (dark mode support planned).
  - Borders/Separators: Subtle grays.
  - Signals:
    - Green (`#16a34a`) for positive/Buy signals, low RSI.
    - Red (`#dc2626`) for negative/Sell signals, high RSI.
    - Yellow/Orange for warnings or 'running' states.

## Layout Structure
The application will use a two-pane layout to separate system controls from data analysis.

### 1. Sidebar (Fixed Left)
- **Width**: Fixed width (e.g., 250px).
- **Header**: Project title ("Stock AI") with a clean icon (using Lucide icons).
- **System Status Module**:
  - Displays current pipeline status.
  - Visual indicator (e.g., pulsing dot when running).
- **Actions**:
  - "Run Screener Now" button, styled as a secondary action (solid outline or subtle background). Disabled when status is 'running'.

### 2. Main Content Area
- **Header**: Page title ("Top Scored Stocks") and a subtle "Last Updated" timestamp if available.
- **Data Grid**: A responsive grid container holding the `ScoreCard` components.

## Component Details

### ScoreCard
A compact, highly structured card designed for quick scanning.
- **Header Row**:
  - Left: Ticker symbol (Bold, prominent).
  - Right: Overall Score (Prominent, potentially color-coded based on threshold).
- **Metrics Area**:
  - A subtle separator line.
  - A 2-column or flex layout for individual metrics.
  - Labels: Small-caps, muted gray (e.g., "RSI", "SIGNAL").
  - Values: Monospace font.
    - RSI Value: Color-coded (Red > 70, Green < 30).
    - Signal Value: Color-coded ("BUY" = Green, "SELL" = Red, "HOLD" = Neutral).
- **Interaction**: Subtle border color change on hover to assist visual tracking.

## Technical Implementation Notes
- **CSS**: Update `index.css` and `App.css` to implement the layout and design tokens (variables for colors/fonts).
- **Components**: Refactor `App.jsx` for the two-pane layout and `ScoreCard.jsx` for the new internal structure.
- **Dependencies**: Utilize `lucide-react` (already in `package.json`) for icons in the sidebar.
