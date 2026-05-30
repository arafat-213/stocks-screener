import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
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
  runBacktest: vi.fn(() => Promise.resolve({ data: { run_id: 'test-run' } })),
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
  return label.closest('.toggle-wrapper');
};

// ---------------------------------------------------------------------------
// Helper: check if a toggle is currently "on"
// ---------------------------------------------------------------------------
const isToggleChecked = (wrapper) =>
  wrapper.querySelector('.toggle-switch')?.classList.contains('checked') ??
  false;

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

  it('renders Monthly Confirmation toggle in the OFF state by default', async () => {
    renderBacktest();
    await waitFor(() => {
      expect(screen.getByText('Monthly Confirmation')).toBeInTheDocument();
    });
    const toggle = getToggleByLabel('Monthly Confirmation');
    expect(isToggleChecked(toggle)).toBe(false);
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

  it('turns Monthly Confirmation ON when clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Monthly Confirmation'));

    const toggle = getToggleByLabel('Monthly Confirmation');
    expect(isToggleChecked(toggle)).toBe(false);

    await user.click(toggle);
    expect(isToggleChecked(toggle)).toBe(true);
  });

  it('resets both toggles to their defaults when Reset is clicked', async () => {
    const user = userEvent.setup();
    renderBacktest();
    await waitFor(() => screen.getByText('Weekly Confirmation'));

    await user.click(getToggleByLabel('Weekly Confirmation')); // OFF
    await user.click(getToggleByLabel('Monthly Confirmation')); // ON

    expect(isToggleChecked(getToggleByLabel('Weekly Confirmation'))).toBe(
      false
    );
    expect(isToggleChecked(getToggleByLabel('Monthly Confirmation'))).toBe(
      true
    );

    const resetBtn = screen.getByTitle('Reset to defaults');
    await user.click(resetBtn);

    expect(isToggleChecked(getToggleByLabel('Weekly Confirmation'))).toBe(true);
    expect(isToggleChecked(getToggleByLabel('Monthly Confirmation'))).toBe(
      false
    );
  });
});
