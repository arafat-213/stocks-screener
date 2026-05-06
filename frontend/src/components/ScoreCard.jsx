import React from 'react';

export default function ScoreCard({ stock }) {
  const isHighRsi = stock.rsi > 70;
  const isLowRsi = stock.rsi < 30;
  const isBuy = stock.signal === 'BUY';
  const isSell = stock.signal === 'SELL';

  return (
    <div className="score-card">
      <div className="card-header">
        <span className="symbol">{stock.symbol}</span>
        <span className="score-value">{stock.score}</span>
      </div>
      <div className="divider"></div>
      <div className="metrics-grid">
        <div className="metric">
          <label>RSI</label>
          <span className={`value ${isHighRsi ? 'danger' : isLowRsi ? 'success' : ''}`}>
            {stock.rsi.toFixed(2)}
          </span>
        </div>
        <div className="metric">
          <label>SIGNAL</label>
          <span className={`value bold ${isBuy ? 'success' : isSell ? 'danger' : ''}`}>
            {stock.signal}
          </span>
        </div>
      </div>
    </div>
  );
}
