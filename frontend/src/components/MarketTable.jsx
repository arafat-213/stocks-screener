import { Link } from 'react-router-dom';
import './MarketTable.css';

const MarketTable = ({ stocks }) => {

  return (
    <div className="market-table-container">
      <div className="market-table">
        <div className="market-table-header">
          <div className="header-cell">Symbol</div>
          <div className="header-cell cell-numeric">Price</div>
          <div className="header-cell cell-numeric">Change %</div>
          <div className="header-cell cell-numeric">Score</div>
          <div className="header-cell cell-numeric">RS</div>
          <div className="header-cell cell-numeric">ADX</div>
          <div className="header-cell cell-numeric">ROE %</div>
          <div className="header-cell cell-numeric">P/E</div>
          <div className="header-cell">Sector</div>
        </div>
        <div className="market-table-body">
          {stocks.map((stock) => {
            const daily = stock.timeframes?.D || {};
            const isPositive = stock.price_change_pct >= 0;
            
            return (
              <Link 
                key={stock.symbol} 
                to={`/stocks/${stock.symbol}`} 
                className="table-row"
              >
                <div className="table-cell cell-symbol">
                  {stock.symbol.replace('.NS', '')}
                </div>
                <div className="table-cell cell-numeric">
                  ₹{stock.close_price?.toLocaleString('en-IN', { minimumFractionDigits: 1 })}
                </div>
                <div className={`table-cell cell-numeric ${isPositive ? 'text-positive' : 'text-negative'}`}>
                  {isPositive ? '+' : ''}{stock.price_change_pct?.toFixed(2)}%
                </div>
                <div className="table-cell cell-numeric bold">
                  {daily.score || '-'}
                </div>
                <div className="table-cell cell-numeric text-primary bold">
                  {daily.rs_score?.toFixed(0) || '-'}
                </div>
                <div className="table-cell cell-numeric">
                  {daily.adx?.toFixed(1) || '-'}
                </div>
                <div className="table-cell cell-numeric">
                  {stock.fundamentals?.roe?.toFixed(1) || '-'}%
                </div>
                <div className="table-cell cell-numeric">
                  {stock.fundamentals?.pe?.toFixed(1) || '-'}
                </div>
                <div className="table-cell cell-sector">
                  {stock.sector}
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export const MarketTableSkeleton = ({ rows = 10 }) => {
  return (
    <div className="market-table-container">
      <div className="market-table">
        <div className="market-table-header">
          <div className="header-cell">Symbol</div>
          <div className="header-cell cell-numeric">Price</div>
          <div className="header-cell cell-numeric">Change %</div>
          <div className="header-cell cell-numeric">Score</div>
          <div className="header-cell cell-numeric">RSI</div>
          <div className="header-cell">EMA</div>
          <div className="header-cell cell-numeric">P/E</div>
          <div className="header-cell">Sector</div>
        </div>
        <div className="market-table-body">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="table-row">
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
              <div className="table-cell"><div className="skeleton-cell"></div></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default MarketTable;
