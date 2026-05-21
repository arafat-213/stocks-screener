import { useState, useEffect, useMemo, useCallback } from 'react';
import { 
  Calendar, 
  Loader2, 
  ChevronRight,
  ChevronDown,
  TrendingUp,
  AlertCircle,
  BarChart3,
  History
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { getReportList, getReportByDate, getSectorRotation } from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { DataTable } from '../components/ui/DataTable';
import { SectorRotationTable } from '../components/SectorRotationTable';
import './Dashboard.css';

const Intelligence = () => {
  const [activeView, setActiveView] = useState('rotation'); // 'rotation' | 'reports'
  const [selectedDate, setSelectedDate] = useState('');
  const [expandedMonths, setExpandedMonths] = useState({});
  const [showAllMonths, setShowAllMonths] = useState(false);

  // Fetch Sector Rotation Data
  const { 
    data: rotationData = [], 
    loading: loadingRotation, 
    error: rotationError 
  } = useFetch(getSectorRotation, {
    autoFetch: activeView === 'rotation'
  });

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

  // Stable report fetch function
  const fetchReport = useCallback(() => getReportByDate(selectedDate), [selectedDate]);

  // Fetch specific report content
  const {
    data: reportData = [],
    loading: loadingReport,
    error: reportError
  } = useFetch(fetchReport, {
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
      const timer = setTimeout(() => {
        setExpandedMonths({ [groupedMonths[0].key]: true });
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [groupedMonths, expandedMonths]);

  const toggleMonth = (key) => {
    setExpandedMonths(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const columns = useMemo(() => [
    { 
      key: 'symbol', 
      label: 'Symbol', 
      sortable: true,
      render: (val) => (
        <Link to={`/stocks/${val}`} className="table-link mono bold">
          {val.replace('.NS', '')}
        </Link>
      )
    },
    { 
      key: 'confluence', 
      label: 'Confluence', 
      sortable: true,
      accessor: (row) => row.confluence_count,
      render: (val, row) => (
        <span className={`status-badge ${row.confluence_count >= 2 ? 'bullish' : 'neutral'}`}>
          {row.confluence}
        </span>
      )
    },
    { 
      key: 'daily_score', 
      label: 'Daily Score', 
      sortable: true,
      render: (val) => <span className="mono">{val?.toFixed(1) || 'N/A'}</span>
    },
    { 
      key: 'rsi', 
      label: 'RSI', 
      sortable: true,
      render: (val) => <span className="mono">{val?.toFixed(1) || 'N/A'}</span>
    }
  ], []);

  if (loadingDates && !dates.length) {
    return (
      <div className="loading-state h-80vh">
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
        <div className="header-content">
          <h1>Market Intelligence</h1>
          <p className="text-muted">
            Macro sector rotation and historical session reports.
          </p>
        </div>

        <div className="tabs-container card">
          <button
            className={`tab-btn ${activeView === 'rotation' ? 'active' : ''}`}
            onClick={() => setActiveView('rotation')}
          >
            <BarChart3 size={18} />
            <span>Sector Rotation</span>
          </button>
          <button
            className={`tab-btn ${activeView === 'reports' ? 'active' : ''}`}
            onClick={() => setActiveView('reports')}
          >
            <History size={18} />
            <span>Historical Reports</span>
          </button>
        </div>
      </header>

      {datesError && (
        <ErrorBanner message={`Failed to load report list: ${datesError}`} />
      )}
      {reportError && (
        <ErrorBanner message={`Failed to load report: ${reportError}`} />
      )}
      {rotationError && (
        <ErrorBanner
          message={`Failed to load rotation data: ${rotationError}`}
        />
      )}

      {activeView === 'rotation' ? (
        <div className="rotation-view fade-in">
          <SectorRotationTable data={rotationData} loading={loadingRotation} />
        </div>
      ) : (
        <div className="intelligence-grid fade-in">
          {/* Date Selection Sidebar/List */}
          <aside className="card h-fit p-24">
            <div className="flex-center-gap-8 mb-12">
              <Calendar size={18} className="text-primary" />
              <h2 className="fs-14 bold">Past Sessions</h2>
            </div>

            <div className="month-groups flex-col-gap-12">
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
                      marginBottom: '8px',
                    }}
                  >
                    <span className="month-section-label">{month.label}</span>
                    {expandedMonths[month.key] ? (
                      <ChevronDown size={14} />
                    ) : (
                      <ChevronRight size={14} />
                    )}
                  </button>

                  {expandedMonths[month.key] && (
                    <div className="date-list flex-col-gap-4">
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
                            background:
                              selectedDate === date
                                ? 'var(--color-bg-elevated)'
                                : 'transparent',
                            color:
                              selectedDate === date
                                ? 'var(--color-primary)'
                                : 'var(--color-text)',
                            border: '1px solid',
                            borderColor:
                              selectedDate === date
                                ? 'var(--color-primary)'
                                : 'transparent',
                            cursor: 'pointer',
                          }}
                        >
                          <span>{date}</span>
                          <ChevronRight
                            size={14}
                            opacity={selectedDate === date ? 1 : 0.3}
                          />
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
                    padding: '4px 0',
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
              <div className="card loading-state mt-32">
                <Loader2 className="animate-spin" size={32} />
                <p>Compiling report for {selectedDate}...</p>
              </div>
            ) : reportData.length === 0 ? (
              <div className="card no-results p-64">
                <AlertCircle size={48} />
                <h3>No data found</h3>
                <p>We couldn't find any session data for {selectedDate}.</p>
              </div>
            ) : (
              <div className="card results-card">
                <div className="card-header">
                  <div className="report-header-flex">
                    <TrendingUp size={20} className="text-bullish" />
                    <h3 className="m-0">Session Report: {selectedDate}</h3>
                  </div>
                  <span className="count-badge">
                    {reportData.length} stocks tracked
                  </span>
                </div>

                <DataTable
                  columns={columns}
                  data={reportData}
                  initialSort={{ key: 'confluence', direction: 'desc' }}
                />
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
};

export default Intelligence;
