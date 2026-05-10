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
      <div className="data-table-container skeleton">
        <div className="table-header">
          {columns.map(col => <div key={col.key} className="header-cell">{col.label}</div>)}
        </div>
        {Array.from({ length: skeletonRows }).map((_, i) => (
          <div key={i} className="table-row">
            {columns.map(col => <div key={col.key} className="table-cell"><div className="skeleton-line" /></div>)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="data-table-container">
      <div className="data-table">
        <div className="table-header">
          {columns.map(col => (
            <div 
              key={col.key} 
              className={`header-cell ${col.sortable ? 'sortable' : ''}`}
              onClick={() => col.sortable && requestSort(col.key)}
            >
              {col.label}
              {col.sortable && (
                <span className="sort-icon">
                  {sortConfig.key === col.key 
                    ? (sortConfig.direction === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />)
                    : <ArrowUpDown size={14} className="opacity-20" />}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="table-body">
          {sortedData.map((row, i) => (
            <div key={row.symbol || i} className="table-row">
              {columns.map(col => {
                const val = col.accessor ? col.accessor(row) : row[col.key];
                return (
                  <div key={col.key} className="table-cell">
                    {col.render ? col.render(val, row) : val}
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
