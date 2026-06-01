import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import Backtest from '../Backtest';

// ---------------------------------------------------------------------------
// API Mocks — prevent any real HTTP calls
// ---------------------------------------------------------------------------
vi.mock('../../api/client', () => ({
  getBacktestRuns: vi.fn(() => Promise.resolve({ data: [] })),
  getBacktestRun: vi.fn(() => Promise.resolve({ data: null })),
  getScreensList: vi.fn(() => Promise.resolve({ data: [] })),
  getBacktestTrades: vi.fn(() =>
    Promise.resolve({ data: { trades: [], total: 0 } })
  ),
}));

vi.mock('../../hooks/useTheme', () => ({
  useTheme: vi.fn(() => ({ isDark: false })),
}));

// ---------------------------------------------------------------------------
// Helper: render Backtest with Router context
// ---------------------------------------------------------------------------
const renderBacktest = () =>
  render(
    <BrowserRouter>
      <Backtest />
    </BrowserRouter>
  );

// ---------------------------------------------------------------------------
// Helper: find a toggle wrapper by its label text
// ---------------------------------------------------------------------------
const getToggleByLabel = (labelText) => {
  const label = screen.getByText(labelText);
  // The label is inside the toggle div
  return label.closest('div[class*="group flex"]');
};

// ---------------------------------------------------------------------------
// Helper: check if a toggle is currently "on"
// ---------------------------------------------------------------------------
const isToggleChecked = (wrapper) => {
  // Check for translate-x-4 class on the inner div
  const inner = wrapper.querySelector('div[class*="translate-x-4"]');
  return !!inner;
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Backtest MTF Confirmation Toggles', () => {
  it('renders Weekly Confirmation toggle in the ON state by default', async () => {
    renderBacktest();
    await waitFor(() => {
      expect(screen.getByText('Weekly Confirmation')).toBeInTheDocument();
    });
    const toggle = getToggleByLabel('Weekly Confirmation');
    expect(isToggleChecked(toggle)).toBe(true);
  });

  it('turns Weekly Confirmation OFF when clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Weekly Confirmation'));

    const toggle = getToggleByLabel('Weekly Confirmation');
    expect(isToggleChecked(toggle)).toBe(true);

    await user.click(toggle);
    expect(isToggleChecked(toggle)).toBe(false);
  });

  it('resets toggle to its default when Reset is clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Weekly Confirmation'));

    await user.click(getToggleByLabel('Weekly Confirmation')); // OFF

    expect(isToggleChecked(getToggleByLabel('Weekly Confirmation'))).toBe(
      false
    );

    const resetBtn = screen.getByTitle('Reset to defaults');
    await user.click(resetBtn);

    expect(isToggleChecked(getToggleByLabel('Weekly Confirmation'))).toBe(true);
  });
});
