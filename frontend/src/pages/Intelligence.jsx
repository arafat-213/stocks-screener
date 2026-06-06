import { useState, useMemo, useCallback, lazy, Suspense } from 'react';
import {
  Calendar,
  Loader2,
  ChevronRight,
  ChevronDown,
  TrendingUp,
  AlertCircle,
  BarChart3,
  History,
  RefreshCcw,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  getReportList,
  getReportByDate,
  getSectorRotation,
} from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { ErrorBanner } from '../components/ui/ErrorBanner';

// Lazy load heavy tables
const DataTable = lazy(() =>
  import('../components/ui/DataTable').then((m) => ({ default: m.DataTable }))
);
const SectorRotationTable = lazy(() =>
  import('../components/SectorRotationTable').then((m) => ({
    default: m.SectorRotationTable,
  }))
);

const EMPTY_ARRAY = [];
const EMPTY_OBJECT = {};

// Group dates by month efficiently
const groupDatesByMonth = (dates) => {
  if (!dates || dates.length === 0) return EMPTY_ARRAY;

  const groups = dates.reduce((acc, date) => {
    const [year, month] = date.split('-');
    const monthKey = `${year}-${month}`;

    if (!acc[monthKey]) {
      const dateObj = new Date(parseInt(year), parseInt(month) - 1);
      acc[monthKey] = {
        key: monthKey,
        label: dateObj.toLocaleString('default', {
          month: 'long',
          year: 'numeric',
        }),
        dates: [],
      };
    }
    acc[monthKey].dates.push(date);
    return acc;
  }, {});

  return Object.values(groups).sort((a, b) => b.key.localeCompare(a.key));
};

const Intelligence = () => {
  const [activeView, setActiveView] = useState('rotation'); // 'rotation' | 'reports'
  const [selectedDate, setSelectedDate] = useState('');
  const [expandedMonths, setExpandedMonths] = useState(null); // null = uninitialized
  const [showAllMonths, setShowAllMonths] = useState(false);

  // Fetch Sector Rotation Data
  const {
    data: rotationData = EMPTY_ARRAY,
    loading: loadingRotation,
    error: rotationError,
  } = useFetch(getSectorRotation, {
    autoFetch: activeView === 'rotation',
  });

  // Fetch report list
  const {
    data: dates = EMPTY_ARRAY,
    loading: loadingDates,
    error: datesError,
  } = useFetch(getReportList, {
    onSuccess: (data) => {
      if (data && data.length > 0 && !selectedDate) {
        setSelectedDate(data[0]);
      }
    },
  });

  // Stable report fetch function
  const fetchReport = useCallback(
    () => getReportByDate(selectedDate),
    [selectedDate]
  );

  // Fetch specific report content
  const {
    data: reportData = EMPTY_ARRAY,
    loading: loadingReport,
    error: reportError,
  } = useFetch(fetchReport, {
    autoFetch: !!selectedDate,
  });

  // Group dates by month efficiently
  const groupedMonths = useMemo(() => groupDatesByMonth(dates), [dates]);

  // Derive the expansion state during render to avoid useEffect cascading renders
  const effectiveExpandedMonths = useMemo(() => {
    if (expandedMonths !== null) return expandedMonths;
    if (groupedMonths.length > 0) {
      return { [groupedMonths[0].key]: true };
    }
    return EMPTY_OBJECT;
  }, [expandedMonths, groupedMonths]);

  const toggleMonth = (key) => {
    setExpandedMonths((prev) => {
      const base =
        prev === null
          ? groupedMonths.length > 0
            ? { [groupedMonths[0].key]: true }
            : EMPTY_OBJECT
          : prev;
      return {
        ...base,
        [key]: !base[key],
      };
    });
  };

  const displayedMonths = showAllMonths
    ? groupedMonths
    : groupedMonths.slice(0, 3);
  const hasMoreMonths = groupedMonths.length > 3;

  const columns = useMemo(
    () => [
      {
        key: 'symbol',
        label: 'Symbol',
        sortable: true,
        render: (val) => (
          <Link
            to={`/stocks/${val}`}
            className='text-blue-600 dark:text-blue-400 font-black no-underline hover:underline transition-all tracking-tighter'
          >
            {val.replace('.NS', '')}
          </Link>
        ),
      },
      {
        key: 'confluence',
        label: 'Confluence',
        sortable: true,
        accessor: (row) => row.confluence_count,
        render: (val, row) => (
          <span
            className={`py-1.5 px-3 rounded-lg text-[11px] font-black inline-flex items-center border ${row.confluence_count === 3 ? 'bg-green-500 text-white border-green-600 shadow-md' : row.confluence_count === 2 ? 'bg-amber-500 text-white border-amber-600 shadow-sm' : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'}`}
          >
            {row.confluence}
          </span>
        ),
      },
      {
        key: 'daily_score',
        label: 'Score',
        sortable: true,
        render: (val) => (
          <span
            className={`font-black font-mono text-sm ${val >= 70 ? 'text-green-500' : val >= 50 ? 'text-blue-500' : 'text-text'}`}
          >
            {val?.toFixed(1) || 'N/A'}
          </span>
        ),
      },
      {
        key: 'rsi',
        label: 'RSI',
        sortable: true,
        render: (val) => (
          <span
            className={`font-bold font-mono text-sm ${val <= 30 ? 'text-green-500' : val >= 70 ? 'text-red-500' : 'text-text'}`}
          >
            {val?.toFixed(1) || 'N/A'}
          </span>
        ),
      },
    ],
    []
  );

  if (loadingDates && !dates.length) {
    return (
      <div className='flex flex-col items-center justify-center py-24 text-slate-400 animate-fade-in'>
        <Loader2 className='animate-spin mb-4' size={48} />
        <span className='font-black uppercase tracking-[0.2em] text-xs'>
          Bootstrapping Intelligence Engine...
        </span>
      </div>
    );
  }

  return (
    <div className='w-full animate-fade-in'>
      <header className='mb-8 sm:mb-12 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6'>
        <div>
          <h1 className='text-3xl sm:text-4xl font-black tracking-tighter mb-2'>
            Market Intelligence
          </h1>
          <p className='text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-xs'>
            Analyze sector rotation and historical session logs.
          </p>
        </div>
        <div className='flex gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-border/50'>
          <button
            className={`flex items-center gap-2.5 py-2.5 px-5 rounded-lg font-black text-[10px] uppercase tracking-widest transition-all cursor-pointer border-none shadow-sm ${activeView === 'rotation' ? 'bg-bg-secondary text-blue-600 dark:text-blue-400 shadow-md border border-border/50' : 'text-slate-500 hover:text-text'}`}
            onClick={() => setActiveView('rotation')}
          >
            <BarChart3 size={16} />
            <span>Sector Rotation</span>
          </button>
          <button
            className={`flex items-center gap-2.5 py-2.5 px-5 rounded-lg font-black text-[10px] uppercase tracking-widest transition-all cursor-pointer border-none shadow-sm ${activeView === 'reports' ? 'bg-bg-secondary text-blue-600 dark:text-blue-400 shadow-md border border-border/50' : 'text-slate-500 hover:text-text'}`}
            onClick={() => setActiveView('reports')}
          >
            <History size={16} />
            <span>Session Logs</span>
          </button>
        </div>
      </header>

      <div className='flex flex-col gap-4'>
        {datesError ? (
          <ErrorBanner message={`Failed to load report list: ${datesError}`} />
        ) : null}
        {reportError ? (
          <ErrorBanner message={`Failed to load report: ${reportError}`} />
        ) : null}
        {rotationError ? (
          <ErrorBanner
            message={`Failed to load rotation data: ${rotationError}`}
          />
        ) : null}
      </div>

      <Suspense
        fallback={
          <div className='flex justify-center py-20'>
            <Loader2 className='animate-spin text-blue-500' size={40} />
          </div>
        }
      >
        {activeView === 'rotation' ? (
          <section className='bg-bg-secondary border-2 border-border rounded-3xl p-5 sm:p-8 shadow-sm'>
            <div className='flex items-center gap-3 mb-6 sm:mb-8'>
              <div className='bg-indigo-500/10 p-2 rounded-xl'>
                <BarChart3 className='text-indigo-500' />
              </div>
              <h2 className='text-xl font-black uppercase tracking-tight'>
                Active Sector Performance
              </h2>
            </div>
            <SectorRotationTable
              data={rotationData}
              loading={loadingRotation}
            />
          </section>
        ) : (
          <div className='grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 lg:gap-10 items-start'>
            {/* Date Selection Sidebar/List */}
            <aside className='bg-bg-secondary border-2 border-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-6 lg:sticky lg:top-6'>
              <div className='flex items-center gap-3'>
                <div className='bg-blue-500/10 p-2 rounded-lg'>
                  <Calendar size={18} className='text-blue-500' />
                </div>
                <h3 className='text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400'>
                  Available Sessions
                </h3>
              </div>

              <div className='flex flex-col gap-4 max-h-[600px] overflow-y-auto pr-2'>
                {displayedMonths.map((month) => (
                  <div key={month.key} className='flex flex-col'>
                    <button
                      onClick={() => toggleMonth(month.key)}
                      className='flex items-center justify-between w-full py-3 bg-transparent border-0 border-b-2 border-border cursor-pointer mb-3 hover:border-blue-500 transition-colors'
                    >
                      <span className='text-[11px] font-black uppercase tracking-widest text-text'>
                        {month.label}
                      </span>
                      {effectiveExpandedMonths[month.key] ? (
                        <ChevronDown size={14} className='text-blue-500' />
                      ) : (
                        <ChevronRight size={14} className='text-slate-400' />
                      )}
                    </button>

                    {effectiveExpandedMonths[month.key] ? (
                      <div className='flex flex-col gap-2 animate-fade-in pl-2'>
                        {month.dates.map((date) => (
                          <button
                            key={date}
                            className={`w-full flex justify-between p-3.5 px-5 rounded-xl text-sm font-black transition-all border-2 ${selectedDate === date ? 'bg-blue-600 text-white border-blue-600 shadow-lg shadow-blue-500/30' : 'bg-transparent border-transparent text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-900/50 hover:text-text'}`}
                            onClick={() => setSelectedDate(date)}
                          >
                            <span>{date}</span>
                            <ChevronRight
                              size={14}
                              className={
                                selectedDate === date
                                  ? 'opacity-100'
                                  : 'opacity-30'
                              }
                            />
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}

                {hasMoreMonths && !showAllMonths ? (
                  <button
                    className='mt-2 text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-400 bg-slate-50 dark:bg-slate-900 p-3 rounded-xl border-2 border-transparent hover:border-blue-500 cursor-pointer transition-all'
                    onClick={() => setShowAllMonths(true)}
                  >
                    Show More Months
                  </button>
                ) : null}
              </div>
            </aside>

            <section className='flex flex-col gap-8'>
              {loadingReport ? (
                <div className='flex flex-col items-center justify-center py-40 text-slate-400 bg-bg-secondary border-2 border-border rounded-3xl border-dashed'>
                  <RefreshCcw
                    className='animate-spin mb-4 text-blue-500'
                    size={40}
                  />
                  <span className='font-black uppercase tracking-[0.2em] text-[10px]'>
                    Retrieving Session Data...
                  </span>
                </div>
              ) : reportData.length === 0 ? (
                <div className='flex flex-col items-center justify-center py-40 text-center text-slate-400 bg-bg-secondary border-2 border-border rounded-3xl border-dashed'>
                  <AlertCircle size={48} className='mb-4 opacity-30' />
                  <h3 className='text-text m-0 text-xl font-black uppercase tracking-tight'>
                    No Archive Found
                  </h3>
                  <p className='mt-2 font-bold uppercase tracking-widest text-[10px]'>
                    We couldn't find any session data for {selectedDate}.
                  </p>
                </div>
              ) : (
                <div className='bg-bg-secondary border-2 border-border rounded-3xl shadow-sm overflow-hidden animate-fade-in'>
                  <div className='px-8 py-6 border-b-2 border-border flex justify-between items-center bg-slate-50 dark:bg-slate-900/50'>
                    <div className='flex items-center gap-4'>
                      <div className='bg-green-500/10 p-2 rounded-xl'>
                        <TrendingUp size={24} className='text-green-500' />
                      </div>
                      <h3 className='m-0 text-xl font-black uppercase tracking-tight'>
                        Intelligence Report: {selectedDate}
                      </h3>
                    </div>
                    <span className='text-[10px] font-black py-1.5 px-4 bg-blue-600 text-white rounded-full shadow-lg shadow-blue-500/20 uppercase tracking-[0.15em]'>
                      {reportData.length} ASSETS LOGGED
                    </span>
                  </div>

                  <DataTable
                    columns={columns}
                    data={reportData}
                    initialSort={{ key: 'daily_score', direction: 'desc' }}
                  />
                </div>
              )}
            </section>
          </div>
        )}
      </Suspense>
    </div>
  );
};

export default Intelligence;
