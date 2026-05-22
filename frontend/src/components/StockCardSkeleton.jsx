
import './StockCard.css';

const StockCardSkeleton = () => {
  return (
    <div className="stock-bg-bg-secondary border border-border rounded-lg shadow-sm skeleton">
      <div className="bg-bg-secondary border border-border rounded-lg shadow-sm-top">
        <div className="symbol-section">
          <div className="skeleton-line title" style={{ width: '80px' }}></div>
          <div className="skeleton-line text" style={{ width: '120px' }}></div>
        </div>
        <div className="price-section">
          <div className="skeleton-line title" style={{ width: '60px' }}></div>
          <div className="skeleton-line text" style={{ width: '40px' }}></div>
        </div>
      </div>

      <div className="confluence-section">
        <div className="skeleton-line" style={{ width: '100px', height: '24px', borderRadius: '12px' }}></div>
        <div className="tf-indicators">
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton-line" style={{ width: '30px', height: '20px', borderRadius: '4px' }}></div>
          ))}
        </div>
      </div>

      <div className="metrics-section">
        <div className="metrics-row technical">
          {[1, 2, 3].map(i => (
            <div key={i} className="metric-item">
              <div className="skeleton-line" style={{ width: '30px', height: '10px' }}></div>
              <div className="skeleton-line" style={{ width: '40px', height: '14px' }}></div>
            </div>
          ))}
        </div>
        <div className="metrics-row fundamental">
          {[1, 2, 3].map(i => (
            <div key={i} className="metric-item">
              <div className="skeleton-line" style={{ width: '30px', height: '10px' }}></div>
              <div className="skeleton-line" style={{ width: '40px', height: '14px' }}></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default StockCardSkeleton;
