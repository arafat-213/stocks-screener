import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import Backtest from '../Backtest';
import * as client from '../../api/client';

// ---------------------------------------------------------------------------
// API Mocks
// ---------------------------------------------------------------------------
vi.mock('../../api/client', () => ({
  getBacktestRuns: vi.fn(),
  getBacktestRun: vi.fn(() => Promise.resolve({ data: null })),
  getScreensList: vi.fn(() => Promise.resolve({ data: [] })),
  getBacktestTrades: vi.fn(() => Promise.resolve({ data: { trades: [], total: 0 } })),
  runBacktest: vi.fn(() => Promise.resolve({ data: { run_id: 'test-run' } })),
}));

vi.mock('../../hooks/useTheme', () => ({
  useTheme: vi.fn(() => ({ isDark: false })),
}));

const renderBacktest = () =>
  render(
    <BrowserRouter>
      <Backtest />
    </BrowserRouter>
  );

describe('Backtest Summary Chip', () => {
  it('renders MTF indicators in the summary chip', async () => {
    const mockRuns = [
      {
        run_id: 'run-1',
        status: 'complete',
        created_at: new Date().toISOString(),
        config: {
          score_threshold: 70,
          holding_days: 15,
          stop_loss_pct: 5.0,
          require_weekly_confirmation: true,
          require_monthly_confirmation: false,
        },
      },
      {
        run_id: 'run-2',
        status: 'complete',
        created_at: new Date().toISOString(),
        config: {
          score_threshold: 65,
          holding_days: 10,
          stop_loss_pct: 8.0,
          require_weekly_confirmation: false,
          require_monthly_confirmation: true,
        },
      }
    ];

    vi.mocked(client.getBacktestRuns).mockResolvedValue(mockRuns);

    renderBacktest();

    await waitFor(() => {
      expect(screen.getByText(/T:70 | H:15/)).toBeInTheDocument();
    });

    // Check first run summary
    const summary1 = screen.getByText(/T:70 | H:15 | SL:5% | W:✓ | M:✗/);
    expect(summary1).toBeInTheDocument();

    // Check second run summary
    const summary2 = screen.getByText(/T:65 | H:10 | SL:8% | W:✗ | M:✓/);
    expect(summary2).toBeInTheDocument();
  });

  it('handles undefined weekly confirmation as true (✓)', async () => {
    const mockRuns = [
      {
        run_id: 'run-3',
        status: 'complete',
        created_at: new Date().toISOString(),
        config: {
          score_threshold: 60,
          holding_days: 20,
          stop_loss_pct: 7.0,
          // require_weekly_confirmation is undefined
          require_monthly_confirmation: false,
        },
      }
    ];

    vi.mocked(client.getBacktestRuns).mockResolvedValue(mockRuns);

    renderBacktest();

    await waitFor(() => {
      expect(screen.getByText(/T:60 | H:20 | SL:7% | W:✓ | M:✗/)).toBeInTheDocument();
    });
  });
});
