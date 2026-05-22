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
        <Link to={`/stocks/${val}`} className="text-bullish font-bold no-underline hover:underline font-mono">
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
        <span className={`py-1 px-2 rounded-md text-[12px] font-semibold inline-flex items-center ${row.confluence_count >= 2 ? 'bg-bullish/10 text-bullish' : 'bg-bg-elevated text-text-muted'}`}>
          {row.confluence}
        </span>
      )
    },
    { 
      key: 'daily_score', 
      label: 'Daily Score', 
      sortable: true,
      render: (val) => <span className="font-mono">{val?.toFixed(1) || 'N/A'}</span>
    },
    { 
      key: 'rsi', 
      label: 'RSI', 
      sortable: true,
      render: (val) => <span className="font-mono">{val?.toFixed(1) || 'N/A'}</span>
    }
  ], []);

  if (loadingDates && !dates.length) {
    return (
      <div className="flex flex-col items-center justify-center p-16 gap-4 text-text-muted h-[80vh]">
        <Loader2 className="animate-spin" size={40} />
        <p>Loading market intelligence...</p>
      </div>
    );
  }

  const displayedMonths = showAllMonths ? groupedMonths : groupedMonths.slice(0, 3);
  const hasMoreMonths = groupedMonths.length > 3;

  return (
    <div className="w-full">
      <header className="mb-8">
        <div>
          <h1 className="text-2xl font-bold">Market Intelligence</h1>
          <p className="text-text-muted">
            Macro sector rotation and historical session reports.
          </p>
        </div>

        <div className="flex p-1 gap-1 mt-6 max-w-fit bg-bg-secondary border border-border rounded-lg shadow-sm">
          <button
            className={`flex items-center gap-2 py-2 px-4 rounded-md font-semibold text-text-muted text-[0.9rem] transition-colors ${activeView === 'rotation' ? 'bg-bg-elevated text-primary' : ''}`}
            onClick={() => setActiveView('rotation')}
          >
            <BarChart3 size={18} />
            <span>Sector Rotation</span>
          </button>
          <button
            className={`flex items-center gap-2 py-2 px-4 rounded-md font-semibold text-text-muted text-[0.9rem] transition-colors ${activeView === 'reports' ? 'bg-bg-elevated text-primary' : ''}`}
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
        <div className="animate-fade-in">
          <SectorRotationTable data={rotationData} loading={loadingRotation} />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_3fr] gap-8 animate-fade-in">
          {/* Date Selection Sidebar/List */}
          <aside className="bg-bg-secondary border border-border rounded-lg shadow-sm h-fit p-6">
            <div className="flex items-center gap-2 mb-3">
              <Calendar size={18} className="text-primary" />
              <h2 className="text-sm font-bold">Past Sessions</h2>
            </div>

            <div className="flex flex-col gap-3">
              {displayedMonths.map((month) => (
                <div key={month.key} className="flex flex-col">
                  <button
                    onClick={() => toggleMonth(month.key)}
                    className="flex items-center justify-between w-full py-2 bg-transparent border-0 border-b border-border cursor-pointer mb-2"
                  >
                    <span className="text-[0.85rem] font-bold text-text-muted">{month.label}</span>
                    {expandedMonths[month.key] ? (
                      <ChevronDown size={14} />
                    ) : (
                      <ChevronRight size={14} />
                    )}
                  </button>

                  {expandedMonths[month.key] && (
                    <div className="flex flex-col gap-1">
                      {month.dates.map((date) => (
                        <button
                          key={date}
                          className={`w-full flex justify-between p-2 px-3 rounded-sm text-[0.85rem] font-medium transition-all cursor-pointer border ${selectedDate === date ? 'font-bold bg-bg-elevated text-primary border-primary' : 'bg-transparent text-text border-transparent hover:bg-bg-elevated'}`}
                          onClick={() => setSelectedDate(date)}
                        >
                          <span>{date}</span>
                          <ChevronRight
                            size={14}
                            className={selectedDate === date ? 'opacity-100' : 'opacity-30'}
                          />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {hasMoreMonths && !showAllMonths && (
                <button
                  className="mt-2 text-[0.8rem] text-primary bg-transparent border-0 cursor-pointer text-left py-1 hover:underline"
                  onClick={() => setShowAllMonths(true)}
                >
                  Show older months
                </button>
              )}
            </div>
          </aside>

          {/* Report Content Area */}
          <section>
            {loadingReport ? (
              <div className="bg-bg-secondary border border-border rounded-lg shadow-sm flex flex-col items-center justify-center p-16 gap-4 text-text-muted mt-8">
                <Loader2 className="animate-spin" size={32} />
                <p>Compiling report for {selectedDate}...</p>
              </div>
            ) : reportData.length === 0 ? (
              <div className="bg-bg-secondary border border-border rounded-lg shadow-sm flex flex-col items-center justify-center py-16 text-center text-text-muted p-16">
                <AlertCircle size={48} />
                <h3 className="text-text my-4 text-lg font-bold">No data found</h3>
                <p>We couldn't find any session data for {selectedDate}.</p>
              </div>
            ) : (
              <div className="bg-bg-secondary border border-border rounded-lg shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-border flex justify-between items-center">
                  <div className="flex items-center gap-3">
                    <TrendingUp size={20} className="text-bullish" />
                    <h3 className="m-0 text-[1.1rem]">Session Report: {selectedDate}</h3>
                  </div>
                  <span className="text-[0.75rem] font-medium py-0.5 px-2 bg-bg-elevated rounded-full text-text-muted ml-3">
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
