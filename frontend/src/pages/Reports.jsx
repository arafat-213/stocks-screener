import { useState, useEffect } from 'react';
import { Activity, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getReportList, getReportByDate } from '../api/client';
import './Dashboard.css'; // Reuse dashboard styles for consistency

const Reports = () => {
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [reportData, setReportData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDates = async () => {
      try {
        const response = await getReportList();
        setDates(response.data);
        if (response.data.length > 0) {
          setSelectedDate(response.data[0]);
        }
      } catch (error) {
        console.error('Error fetching report dates:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchDates();
  }, []);

  useEffect(() => {
    if (selectedDate) {
      const fetchReport = async () => {
        setLoading(true);
        try {
          const response = await getReportByDate(selectedDate);
          setReportData(response.data);
        } catch (error) {
          console.error('Error fetching report data:', error);
        } finally {
          setLoading(false);
        }
      };
      fetchReport();
    }
  }, [selectedDate]);

  return (
    <div className="reports-page">
      {/* Main Content */}
      <main className="reports-content">
        <header className="reports-header" style={{ marginBottom: '24px' }}>
          <div className="action-bar">
            <h2>Market Reports</h2>
          </div>
        </header>

        <div className="card" style={{ padding: '24px', marginBottom: '24px' }}>
          <h3 style={{ fontSize: '14px', marginBottom: '16px', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Available Report Dates ({dates.length})
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {dates.map((date) => (
              <button
                key={date}
                className={`filter-chip ${selectedDate === date ? 'active' : ''}`}
                onClick={() => setSelectedDate(date)}
                style={{ 
                  padding: '8px 16px', 
                  borderRadius: '20px', 
                  border: '1px solid var(--color-border)',
                  background: selectedDate === date ? 'var(--color-bullish)' : 'white',
                  color: selectedDate === date ? 'white' : 'var(--color-text)',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: '600'
                }}
              >
                {date}
              </button>
            ))}
          </div>
        </div>

        <div className="report-results">
          <div className="action-bar" style={{ marginBottom: '16px' }}>
            <h3>Showing results for: <span style={{ color: 'var(--color-bullish)' }}>{selectedDate || '...'}</span></h3>
          </div>
        
          {loading ? (
            <div className="dashboard-loading" style={{ minHeight: '200px' }}>
              <Loader2 className="animate-spin" size={40} />
              <p>Loading report data...</p>
            </div>
          ) : reportData.length === 0 ? (
            <div className="no-results">
              <p>No data available for this date.</p>
            </div>
          ) : (
            <div className="table-container">
              <table className="stocks-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Name</th>
                    <th>Confluence</th>
                    <th>Daily Score</th>
                    <th>RSI (D)</th>
                  </tr>
                </thead>
                <tbody>
                  {reportData.map((stock) => (
                    <tr key={stock.symbol}>
                      <td><strong>{stock.symbol}</strong></td>
                      <td>{stock.name}</td>
                      <td>
                        <span className={`status-badge ${stock.confluence_count >= 2 ? 'bullish' : 'neutral'}`}>
                          {stock.confluence}
                        </span>
                      </td>
                      <td>{stock.daily_score?.toFixed(1) || 'N/A'}</td>
                      <td>{stock.rsi?.toFixed(1) || 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default Reports;
