import { useState, useEffect, useMemo } from 'react';
import { 
  Calendar, 
  Loader2, 
  ChevronRight,
  ChevronDown,
  TrendingUp,
  AlertCircle
} from 'lucide-react';
import { getReportList, getReportByDate } from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import './Dashboard.css';

const Intelligence = () => {
  const [selectedDate, setSelectedDate] = useState('');
  const [expandedMonths, setExpandedMonths] = useState({});
  const [showAllMonths, setShowAllMonths] = useState(false);

  // Fetch report list
  const { 
    data: dates = [], 
    loading: loadingDates, 
    error: datesError 
  } = useFetch(getReportList, {
    onSuccess: (data) => {
      if (data && data.length > 0 && !selectedDate) {
        setSelectedDate(data[0]);
      }
    }
  });

  // Fetch specific report content
  const {
    data: reportData = [],
    loading: loadingReport,
    error: reportError
  } = useFetch(() => getReportByDate(selectedDate), {
    deps: [selectedDate],
    autoFetch: !!selectedDate
  });

  // Group dates by month
  const groupedMonths = useMemo(() => {
    if (!dates || dates.length === 0) return [];
    
    const groups = {};
    dates.forEach(date => {
      const [year, month] = date.split('-');
      const monthKey = `${year}-${month}`;
      if (!groups[monthKey]) {
        // Create a date object to get localized month name
        const dateObj = new Date(year, parseInt(month) - 1);
        groups[monthKey] = {
          label: dateObj.toLocaleString('default', { month: 'long', year: 'numeric' }),
          dates: []
        };
      }
      groups[monthKey].dates.push(date);
    });

    return Object.keys(groups)
      .sort((a, b) => b.localeCompare(a))
      .map(key => ({
        key,
        ...groups[key]
      }));
  }, [dates]);

  // Expand the latest month by default once loaded
  useEffect(() => {
    if (groupedMonths.length > 0 && Object.keys(expandedMonths).length === 0) {
      setExpandedMonths({ [groupedMonths[0].key]: true });
    }
  }, [groupedMonths]);

  const toggleMonth = (key) => {
    setExpandedMonths(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  if (loadingDates && !dates.length) {
    return (
      <div className="loading-state" style={{ height: '80vh' }}>
        <Loader2 className="animate-spin" size={40} />
        <p>Loading market intelligence...</p>
      </div>
    );
  }

  const displayedMonths = showAllMonths ? groupedMonths : groupedMonths.slice(0, 3);
  const hasMoreMonths = groupedMonths.length > 3;

  return (
    <div className="intelligence-page">
      <header className="page-header">
        <h1>Market Intelligence</h1>
        <p className="text-muted">Historical performance reports and deep-dive analysis.</p>
      </header>

      {datesError && <ErrorBanner message={`Failed to load report list: ${datesError}`} />}
      {reportError && <ErrorBanner message={`Failed to load report: ${reportError}`} />}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 3fr', gap: '32px' }}>
        {/* Date Selection Sidebar/List */}
        <aside className="card" style={{ height: 'fit-content', padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <Calendar size={18} className="text-primary" />
            <h2 style={{ fontSize: '1rem', fontWeight: 700 }}>Past Sessions</h2>
          </div>
          
          <div className="month-groups" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {displayedMonths.map((month) => (
              <div key={month.key} className="month-section">
                <button
                  onClick={() => toggleMonth(month.key)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    padding: '8px 0',
                    background: 'none',
                    border: 'none',
                    borderBottom: '1px solid var(--color-border)',
                    cursor: 'pointer',
                    marginBottom: '8px'
                  }}
                >
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--color-text-muted)' }}>
                    {month.label}
                  </span>
                  {expandedMonths[month.key] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>

                {expandedMonths[month.key] && (
                  <div className="date-list" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {month.dates.map((date) => (
                      <button
                        key={date}
                        className={`date-btn ${selectedDate === date ? 'active' : ''}`}
                        onClick={() => setSelectedDate(date)}
                        style={{
                          width: '100%',
                          display: 'flex',
                          justifyContent: 'space-between',
                          padding: '8px 12px',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.85rem',
                          fontWeight: selectedDate === date ? 700 : 500,
                          background: selectedDate === date ? 'var(--color-bg-elevated)' : 'transparent',
                          color: selectedDate === date ? 'var(--color-primary)' : 'var(--color-text)',
                          border: '1px solid',
                          borderColor: selectedDate === date ? 'var(--color-primary)' : 'transparent',
                          cursor: 'pointer'
                        }}
                      >
                        <span>{date}</span>
                        <ChevronRight size={14} opacity={selectedDate === date ? 1 : 0.3} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {hasMoreMonths && !showAllMonths && (
              <button 
                className="btn-link" 
                onClick={() => setShowAllMonths(true)}
                style={{ 
                  marginTop: '8px', 
                  fontSize: '0.8rem', 
                  color: 'var(--color-primary)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  padding: '4px 0'
                }}
              >
                Show older months
              </button>
            )}
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
