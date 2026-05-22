import { useState, useMemo } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';

export const DataTable = ({ columns, data = [], initialSort, loading, skeletonRows = 10 }) => {
  const [sortConfig, setSortConfig] = useState(initialSort || { key: null, direction: 'asc' });

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return data;
    const col = columns.find(c => c.key === sortConfig.key);
    const accessor = col?.accessor || (row => row[sortConfig.key]);

    return [...data].sort((a, b) => {
      const aVal = accessor(a);
      const bVal = accessor(b);
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [data, sortConfig, columns]);

  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
    setSortConfig({ key, direction });
  };

  if (loading) {
    return (
      <div className="w-full overflow-hidden rounded-2xl border-2 border-border bg-bg-secondary shadow-sm">
        <div className="flex bg-slate-50 dark:bg-slate-900 border-b-2 border-border">
          {columns.map(col => (
            <div key={col.key} className="flex-1 px-6 py-4 text-left text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em]">
              {col.label}
            </div>
          ))}
        </div>
        {Array.from({ length: skeletonRows }).map((_, i) => (
          <div key={i} className="flex border-b border-border last:border-0">
            {columns.map(col => (
              <div key={col.key} className="flex-1 px-6 py-5">
                <div className="h-5 w-2/3 bg-slate-100 dark:bg-slate-800 rounded-lg animate-pulse" />
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto rounded-2xl border-2 border-border bg-bg-secondary shadow-sm">
      <div className="min-w-full inline-block align-middle">
        <div className="flex bg-slate-50 dark:bg-slate-900 border-b-2 border-border">
          {columns.map(col => (
            <div 
              key={col.key} 
              className={`flex-1 px-6 py-4 text-left text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2 transition-colors duration-200 group ${col.sortable ? 'cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-text' : ''}`}
              onClick={() => col.sortable && requestSort(col.key)}
            >
              {col.label}
              {col.sortable && (
                <span className="shrink-0 transition-transform group-hover:scale-110">
                  {sortConfig.key === col.key 
                    ? (sortConfig.direction === 'asc' ? <ArrowUp size={14} className="text-blue-600" /> : <ArrowDown size={14} className="text-blue-600" />)
                    : <ArrowUpDown size={14} className="opacity-20" />}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="flex flex-col">
          {sortedData.map((row, i) => (
            <div key={row.symbol || i} className="flex border-b border-border last:border-0 hover:bg-slate-50/50 dark:hover:bg-slate-900/50 transition-colors duration-150">
              {columns.map(col => {
                const val = col.accessor ? col.accessor(row) : row[col.key];
                return (
                  <div key={col.key} className="flex-1 px-6 py-4 text-sm text-text font-bold flex items-center overflow-hidden">
                    {col.render ? col.render(val, row) : (
                      <span className="truncate">{val}</span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
