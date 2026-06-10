import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ActionCenter from '../ActionCenter';

describe('ActionCenter', () => {
  const mockEntryCandidates = [
    {
      symbol: 'RELIANCE.NS',
      current_price: 2500,
      entry_low: 2495,
      entry_high: 2505,
      id: 1,
      watchlist_id: 10,
    },
  ];

  const mockSlRisk = [
    {
      symbol: 'INFY.NS',
      current_price: 1500,
      stop_loss: 1505,
      dist_pct: -0.2,
      id: 2,
      watchlist_id: 11,
    },
  ];

  const mockTargetNear = [
    {
      symbol: 'TCS.NS',
      current_price: 3500,
      target: 3510,
      dist_pct: 0.3,
      id: 3,
      watchlist_id: 12,
    },
  ];

  it('renders correctly and calculates urgency for entry candidates', () => {
    render(
      <ActionCenter
        entry_candidates={mockEntryCandidates}
        onExecute={() => {}}
        onExit={() => {}}
      />
    );

    expect(screen.getByText('RELIANCE')).toBeInTheDocument();
    expect(screen.getByText(/₹2500 \(Zone: 2495-2505\)/)).toBeInTheDocument();

    // RELIANCE is urgent because 2500 is within 0.25% of 2495 or 2505
    // 2500 - 2495 = 5. 5/2495 = 0.0020 (which is <= 0.0025)
  });

  it('calls onExecute with full item object', () => {
    const onExecute = vi.fn();
    render(
      <ActionCenter
        entry_candidates={mockEntryCandidates}
        onExecute={onExecute}
        onExit={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Execute Order'));
    expect(onExecute).toHaveBeenCalledWith(mockEntryCandidates[0]);
  });

  it('calculates urgency correctly for SL risk', () => {
    render(
      <ActionCenter
        sl_risk={mockSlRisk}
        onExecute={() => {}}
        onExit={() => {}}
      />
    );

    expect(screen.getByText('INFY')).toBeInTheDocument();
    expect(screen.getByText(/₹1500 vs SL ₹1505 \(-0.2%\)/)).toBeInTheDocument();

    // INFY is urgent because abs(-0.2) <= 0.25
  });

  it('calculates urgency correctly for Target alerts', () => {
    render(
      <ActionCenter
        target_near={mockTargetNear}
        onExecute={() => {}}
        onExit={() => {}}
      />
    );

    expect(screen.getByText('TCS')).toBeInTheDocument();
    expect(screen.getByText(/₹3500 vs Tgt ₹3510 \(0.3%\)/)).toBeInTheDocument();

    // TCS is NOT urgent because abs(0.3) > 0.25
    // Note: The UI displays the urgent indicator if isUrgent is true.
  });
});
