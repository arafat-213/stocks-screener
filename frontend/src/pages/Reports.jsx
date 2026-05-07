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
    <div className="dashboard-layout">
      {/* Sidebar */}
      <aside className="dashboard-sidebar">
        <div className="brand">
          <Activity color="#16a34a" size={28} />
          <h1>Stock AI</h1>
        </div>

        <nav className="filter-group">
          <h3>Navigation</h3>
          <div className="radio-group">
            <Link to="/" className="radio-label">Dashboard</Link>
            <Link to="/screener" className="radio-label">Screener</Link>
            <Link to="/reports" className="radio-label active">Reports</Link>
          </div>
        </nav>
        
        <div className="filter-group">
          <div className="filter-header">
            <h3>Available Dates</h3>
            <span className="count">{dates.length}</span>
          </div>
          <div className="radio-group" style={{ maxHeight: 'calc(100vh - 400px)', overflowY: 'auto' }}>
            {dates.map((date) => (
              <label
                key={date}
                className={`radio-label ${selectedDate === date ? 'active' : ''}`}
                onClick={() => setSelectedDate(date)}
                style={{ cursor: 'pointer' }}
              >
                {date}
              </label>
            ))}
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="dashboard-main">
        <header className="dashboard-header">
          <div className="action-bar">
            <h2>Report for {selectedDate || '...'}</h2>
          </div>
        </header>
        
        {loading ? (
          <div className="dashboard-loading">
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
      </main>
    </div>
  );
};

export default Reports;
