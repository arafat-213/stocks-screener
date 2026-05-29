import { useState, useEffect, useMemo, useCallback } from 'react';
import { Calendar, Loader2, ChevronRight, ChevronDown, TrendingUp, AlertCircle, BarChart3, History, Activity, RefreshCcw, Star, Zap, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getReportList, getReportByDate, getSectorRotation, getLatestDigest } from '../api/client';
import { useFetch } from '../hooks/useFetch';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { DataTable } from '../components/ui/DataTable';
import { SectorRotationTable } from '../components/SectorRotationTable';

const Intelligence = () => {
  const [activeView, setActiveView] = useState('digest'); // 'digest' | 'rotation' | 'reports'
  const [selectedDate, setSelectedDate] = useState('');
  const [expandedMonths, setExpandedMonths] = useState({});
  const [showAllMonths, setShowAllMonths] = useState(false);

  // Fetch High Conviction Digest
  const {
    data: digestData,
    loading: loadingDigest,
    error: digestError
  } = useFetch(getLatestDigest, {
    autoFetch: activeView === 'digest'
  });

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

  const displayedMonths = showAllMonths ? groupedMonths : groupedMonths.slice(0, 3);
  const hasMoreMonths = groupedMonths.length > 3;

  const columns = useMemo(() => [
    { 
      key: 'symbol', 
      label: 'Symbol', 
      sortable: true,
      render: (val) => (
        <Link to={`/stocks/${val}`} className="text-blue-600 dark:text-blue-400 font-black no-underline hover:underline transition-all tracking-tighter">
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
        <span className={`py-1.5 px-3 rounded-lg text-[11px] font-black inline-flex items-center border ${row.confluence_count === 3 ? 'bg-green-500 text-white border-green-600 shadow-md' : row.confluence_count === 2 ? 'bg-amber-500 text-white border-amber-600 shadow-sm' : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'}`}>
          {row.confluence}
        </span>
      )
    },
    { 
      key: 'daily_score', 
      label: 'Score', 
      sortable: true,
      render: (val) => (
        <span className={`font-black font-mono text-sm ${val >= 70 ? 'text-green-500' : val >= 50 ? 'text-blue-500' : 'text-text'}`}>
          {val?.toFixed(1) || 'N/A'}
        </span>
      )
    },
    { 
      key: 'rsi', 
      label: 'RSI', 
      sortable: true,
      render: (val) => (
        <span className={`font-bold font-mono text-sm ${val <= 30 ? 'text-green-500' : val >= 70 ? 'text-red-500' : 'text-text'}`}>
          {val?.toFixed(1) || 'N/A'}
        </span>
      )
    }
  ], []);

  const digestColumns = useMemo(() => [
    { 
      key: 'symbol', 
      label: 'Symbol', 
      sortable: true,
      render: (val) => (
        <Link to={`/stocks/${val}`} className="text-blue-600 dark:text-blue-400 font-black no-underline hover:underline transition-all tracking-tighter">
          {val.replace('.NS', '')}
        </Link>
      )
    },
    {
      key: 'tier',
      label: 'Tier',
      sortable: true,
      render: (val) => (
        <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${val === 1 ? 'bg-bullish text-white' : 'bg-blue-500 text-white'}`}>
          Tier {val}
        </span>
      )
    },
    { 
      key: 'score', 
      label: 'Score', 
      sortable: true,
      render: (val) => (
        <span className="font-black font-mono text-sm text-text">{val?.toFixed(1)}</span>
      )
    },
    {
      key: 'pullback_entry_zone',
      label: 'Entry Zone',
      render: (val) => val ? (
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-bold text-text">₹{val.target}</span>
          <span className="text-[9px] text-text-muted">Limit: ₹{val.tolerance_high}</span>
        </div>
      ) : <span className="text-[10px] font-bold text-text-muted">Momentum</span>
    },
    {
      key: 'stop_reference',
      label: 'Stop Loss',
      render: (val) => (
        <span className="text-[10px] font-black text-bearish">₹{val?.toFixed(2)}</span>
      )
    },
    { 
      key: 'sector', 
      label: 'Sector', 
      sortable: true,
      render: (val) => <span className="text-[10px] font-bold text-text-muted uppercase tracking-tight">{val}</span>
    }
  ], []);

  if (loadingDates && !dates.length) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-slate-400 animate-fade-in">
        <Loader2 className="animate-spin mb-4" size={48} />
        <span className="font-black uppercase tracking-[0.2em] text-xs">Bootstrapping Intelligence Engine...</span>
      </div>
    );
  }

  return (
    <div className="max-w-[1500px] mx-auto p-6 animate-fade-in">
      <header className="mb-8 sm:mb-12 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-6">
        <div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tighter mb-2">Market Intelligence</h1>
          <p className="text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest text-xs">Analyze sector rotation and historical session logs.</p>
        </div>
        <div className="flex gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-border/50">
          <button
            className={`flex items-center gap-2.5 py-2.5 px-5 rounded-lg font-black text-[10px] uppercase tracking-widest transition-all cursor-pointer border-none shadow-sm ${activeView === 'digest' ? 'bg-bg-secondary text-blue-600 dark:text-blue-400 shadow-md border border-border/50' : 'text-slate-500 hover:text-text'}`}
            onClick={() => setActiveView('digest')}
          >
            <Zap size={16} />
            <span>High Conviction</span>
          </button>
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

      <div className="flex flex-col gap-4">
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
        {digestError && (
            <ErrorBanner message={`Failed to load digest: ${digestError}`} />
        )}
      </div>

      {activeView === 'digest' ? (
        <section className="flex flex-col gap-8 animate-fade-in">
          <div className="bg-bg-secondary border-2 border-border rounded-3xl overflow-hidden shadow-sm">
            <div className="px-8 py-6 border-b-2 border-border flex justify-between items-center bg-blue-600 text-white">
              <div className="flex items-center gap-4">
                <div className="bg-white/20 p-2 rounded-xl backdrop-blur-md">
                    <Star size={24} className="fill-white text-white" />
                </div>
                <div>
                  <h2 className="m-0 text-xl font-black uppercase tracking-tight">Today's High Conviction Digest</h2>
                  <p className="m-0 text-[10px] font-bold text-white/70 uppercase tracking-widest mt-1">Surgical entry zones for session: {digestData?.date}</p>
                </div>
              </div>
              <div className="flex gap-3">
                <span className="text-[10px] font-black py-1.5 px-4 bg-white/20 rounded-full uppercase tracking-[0.15em] backdrop-blur-md border border-white/20">
                  {digestData?.summary?.actionable || 0} ACTIONABLE
                </span>
                <span className={`text-[10px] font-black py-1.5 px-4 rounded-full uppercase tracking-[0.15em] border ${digestData?.regime_bullish ? 'bg-green-500 border-green-400' : 'bg-red-500 border-red-400'}`}>
                  {digestData?.regime_bullish ? 'BULL REGIME' : 'BEAR REGIME'}
                </span>
              </div>
            </div>

            <DataTable
              columns={digestColumns}
              data={digestData?.actionable || []}
              initialSort={{ key: 'score', direction: 'desc' }}
              loading={loadingDigest}
            />
          </div>

          <div className="bg-bg-secondary border-2 border-border rounded-3xl p-8 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
               <div className="bg-amber-500/10 p-2 rounded-xl">
                   <ShieldCheck className="text-amber-500" />
               </div>
               <h2 className="text-xl font-black uppercase tracking-tight">Secondary Watchlist</h2>
            </div>
            <DataTable
              columns={digestColumns}
              data={digestData?.watchlist || []}
              initialSort={{ key: 'score', direction: 'desc' }}
              loading={loadingDigest}
            />
          </div>
        </section>
      ) : activeView === 'rotation' ? (
        <section className="bg-bg-secondary border-2 border-border rounded-3xl p-5 sm:p-8 shadow-sm">
           <div className="flex items-center gap-3 mb-6 sm:mb-8">
              <div className="bg-indigo-500/10 p-2 rounded-xl">
                  <BarChart3 className="text-indigo-500" />
              </div>
              <h2 className="text-xl font-black uppercase tracking-tight">Active Sector Performance</h2>
           </div>
           <SectorRotationTable data={rotationData} loading={loadingRotation} />
        </section>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6 lg:gap-10 items-start">
          {/* Date Selection Sidebar/List */}
          <aside className="bg-bg-secondary border-2 border-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-6 lg:sticky lg:top-6">
            <div className="flex items-center gap-3">
                <div className="bg-blue-500/10 p-2 rounded-lg">
                    <Calendar size={18} className="text-blue-500" />
                </div>
                <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Available Sessions</h3>
            </div>

            <div className="flex flex-col gap-4 max-h-[600px] overflow-y-auto pr-2">
              {displayedMonths.map((month) => (
                <div key={month.key} className="flex flex-col">
                  <button
                    onClick={() => toggleMonth(month.key)}
                    className="flex items-center justify-between w-full py-3 bg-transparent border-0 border-b-2 border-border cursor-pointer mb-3 hover:border-blue-500 transition-colors"
                  >
                    <span className="text-[11px] font-black uppercase tracking-widest text-text">{month.label}</span>
                    {expandedMonths[month.key] ? (
                      <ChevronDown size={14} className="text-blue-500" />
                    ) : (
                      <ChevronRight size={14} className="text-slate-400" />
                    )}
                  </button>

                  {expandedMonths[month.key] && (
                    <div className="flex flex-col gap-2 animate-fade-in pl-2">
                      {month.dates.map((date) => (
                        <button
                          key={date}
                          className={`w-full flex justify-between p-3.5 px-5 rounded-xl text-sm font-black transition-all border-2 ${selectedDate === date ? 'bg-blue-600 text-white border-blue-600 shadow-lg shadow-blue-500/30' : 'bg-transparent border-transparent text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-900/50 hover:text-text'}`}
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
                  className="mt-2 text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-400 bg-slate-50 dark:bg-slate-900 p-3 rounded-xl border-2 border-transparent hover:border-blue-500 cursor-pointer transition-all"
                  onClick={() => setShowAllMonths(true)}
                >
                  Show More Months
                </button>
              )}
            </div>
          </aside>

          <section className="flex flex-col gap-8">
            {loadingReport ? (
              <div className="flex flex-col items-center justify-center py-40 text-slate-400 bg-bg-secondary border-2 border-border rounded-3xl border-dashed">
                <RefreshCcw className="animate-spin mb-4 text-blue-500" size={40} />
                <span className="font-black uppercase tracking-[0.2em] text-[10px]">Retrieving Session Data...</span>
              </div>
            ) : reportData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-40 text-center text-slate-400 bg-bg-secondary border-2 border-border rounded-3xl border-dashed">
                <AlertCircle size={48} className="mb-4 opacity-30" />
                <h3 className="text-text m-0 text-xl font-black uppercase tracking-tight">No Archive Found</h3>
                <p className="mt-2 font-bold uppercase tracking-widest text-[10px]">We couldn't find any session data for {selectedDate}.</p>
              </div>
            ) : (
              <div className="bg-bg-secondary border-2 border-border rounded-3xl shadow-sm overflow-hidden animate-fade-in">
                <div className="px-8 py-6 border-b-2 border-border flex justify-between items-center bg-slate-50 dark:bg-slate-900/50">
                  <div className="flex items-center gap-4">
                    <div className="bg-green-500/10 p-2 rounded-xl">
                        <TrendingUp size={24} className="text-green-500" />
                    </div>
                    <h3 className="m-0 text-xl font-black uppercase tracking-tight tracking-tight">Intelligence Report: {selectedDate}</h3>
                  </div>
                  <span className="text-[10px] font-black py-1.5 px-4 bg-blue-600 text-white rounded-full shadow-lg shadow-blue-500/20 uppercase tracking-[0.15em]">
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
    </div>
  );
};

export default Intelligence;
