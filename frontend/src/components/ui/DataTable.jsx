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
      <div className="w-full overflow-hidden rounded-lg border border-border bg-bg-secondary shadow-sm">
        <div className="flex bg-bg-elevated border-b border-border">
          {columns.map(col => (
            <div key={col.key} className="flex-1 px-4 py-3 text-left text-[11px] font-bold text-text-muted uppercase tracking-wider">
              {col.label}
            </div>
          ))}
        </div>
        {Array.from({ length: skeletonRows }).map((_, i) => (
          <div key={i} className="flex border-b border-border last:border-0">
            {columns.map(col => (
              <div key={col.key} className="flex-1 px-4 py-4">
                <div className="h-4 w-2/3 bg-bg-elevated rounded animate-pulse" />
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border bg-bg-secondary shadow-sm">
      <div className="min-w-full inline-block align-middle">
        <div className="flex bg-bg-elevated border-b border-border">
          {columns.map(col => (
            <div 
              key={col.key} 
              className={`flex-1 px-4 py-3 text-left text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center gap-1.5 transition-colors duration-200 ${col.sortable ? 'cursor-pointer hover:bg-black/5 hover:text-text dark:hover:bg-white/5' : ''}`}
              onClick={() => col.sortable && requestSort(col.key)}
            >
              {col.label}
              {col.sortable && (
                <span className="shrink-0">
                  {sortConfig.key === col.key 
                    ? (sortConfig.direction === 'asc' ? <ArrowUp size={14} className="text-primary" /> : <ArrowDown size={14} className="text-primary" />)
                    : <ArrowUpDown size={14} className="opacity-20" />}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="flex flex-col">
          {sortedData.map((row, i) => (
            <div key={row.symbol || i} className="flex border-b border-border last:border-0 hover:bg-bg-elevated/30 transition-colors duration-150">
              {columns.map(col => {
                const val = col.accessor ? col.accessor(row) : row[col.key];
                return (
                  <div key={col.key} className="flex-1 px-4 py-3.5 text-sm text-text font-medium flex items-center overflow-hidden">
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
