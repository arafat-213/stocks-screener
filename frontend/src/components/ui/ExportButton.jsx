import Papa from 'papaparse';
import { Download } from 'lucide-react';

export const ExportButton = ({ data = [], columns = [], filename = 'export.csv', disabled = false }) => {
  const handleExport = () => {
    if (data.length === 0) return;

    // Flatten data based on column keys or accessors
    const flatRows = data.map(row => {
      const flat = {};
      columns.forEach(col => {
        // Use accessor if available, otherwise raw key
        const rawVal = col.accessor ? col.accessor(row) : row[col.key];
        // Ensure we don't export JSX if someone accidentally passed it
        flat[col.label] = (typeof rawVal === 'object' && rawVal !== null && !Array.isArray(rawVal)) 
          ? '' 
          : rawVal ?? '';
      });
      return flat;
    });

    const csv = Papa.unparse(flatRows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <button 
      className="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest border-2 border-border bg-transparent text-slate-500 cursor-pointer transition-all duration-300 hover:enabled:border-blue-500 hover:enabled:text-blue-600 dark:hover:enabled:text-blue-400 hover:enabled:bg-blue-50 dark:hover:enabled:bg-blue-900/10 disabled:opacity-30 disabled:not-allowed shadow-sm active:scale-95" 
      onClick={handleExport}
      disabled={disabled || data.length === 0}
      title="Export to CSV"
    >
      <Download size={14} />
      <span className="leading-none">Export CSV</span>
    </button>
  );
};
