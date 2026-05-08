import { useState, useEffect } from 'react';
import { 
  Calendar, 
  Loader2, 
  ChevronRight,
  TrendingUp,
  AlertCircle
} from 'lucide-react';
import { getReportList, getReportByDate } from '../api/client';
import './Dashboard.css';

const Intelligence = () => {
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [reportData, setReportData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);

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
        setLoadingReport(true);
        try {
          const response = await getReportByDate(selectedDate);
          setReportData(response.data);
        } catch (error) {
          console.error('Error fetching report data:', error);
        } finally {
          setLoadingReport(false);
        }
      };
      fetchReport();
    }
  }, [selectedDate]);

  if (loading) {
    return (
      <div className="loading-state" style={{ height: '80vh' }}>
        <Loader2 className="animate-spin" size={40} />
        <p>Loading market intelligence...</p>
      </div>
    );
  }

  return (
    <div className="intelligence-page">
      <header className="page-header">
        <h1>Market Intelligence</h1>
        <p className="text-muted">Historical performance reports and deep-dive analysis.</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 3fr', gap: '32px' }}>
        {/* Date Selection Sidebar/List */}
        <aside className="card" style={{ height: 'fit-content', padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <Calendar size={18} className="text-primary" />
            <h2 style={{ fontSize: '1rem', fontWeight: 700 }}>Past Sessions</h2>
          </div>
          
          <div className="date-list" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {dates.map((date) => (
              <button
                key={date}
                className={`date-btn ${selectedDate === date ? 'active' : ''}`}
                onClick={() => setSelectedDate(date)}
                style={{
                  width: '100%',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  background: selectedDate === date ? 'var(--color-bg-elevated)' : 'transparent',
                  color: selectedDate === date ? 'var(--color-primary)' : 'var(--color-text)',
                  border: '1px solid',
                  borderColor: selectedDate === date ? 'var(--color-primary)' : 'transparent'
                }}
              >
                <span>{date}</span>
                <ChevronRight size={16} />
              </button>
            ))}
          </div>
        </aside>

        {/* Report Content Area */}
        <section className="report-content">
          {loadingReport ? (
            <div className="card loading-state" style={{ height: '400px' }}>
              <Loader2 className="animate-spin" size={32} />
              <p>Compiling report for {selectedDate}...</p>
            </div>
          ) : reportData.length === 0 ? (
            <div className="card no-results" style={{ padding: '64px' }}>
              <AlertCircle size={48} />
              <h3>No data found</h3>
              <p>We couldn't find any session data for {selectedDate}.</p>
            </div>
          ) : (
            <div className="card results-card">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <TrendingUp size={20} className="text-bullish" />
                  <h3 style={{ margin: 0 }}>Session Report: {selectedDate}</h3>
                </div>
                <span className="count-badge">{reportData.length} stocks tracked</span>
              </div>

              <div className="table-container" style={{ border: 'none', margin: 0 }}>
                <table className="stocks-table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Confluence</th>
                      <th>Daily Score</th>
                      <th>RSI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.map((stock) => (
                      <tr key={stock.symbol}>
                        <td className="mono" style={{ fontWeight: 700 }}>{stock.symbol}</td>
                        <td>
                          <span className={`status-badge ${stock.confluence_count >= 2 ? 'bullish' : 'neutral'}`}>
                            {stock.confluence}
                          </span>
                        </td>
                        <td className="mono">{stock.daily_score?.toFixed(1) || 'N/A'}</td>
                        <td className="mono">{stock.rsi?.toFixed(1) || 'N/A'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default Intelligence;
