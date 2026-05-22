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
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[0.8rem] font-semibold border border-border bg-transparent text-text-muted cursor-pointer transition-all duration-200 hover:enabled:border-primary hover:enabled:text-primary hover:enabled:bg-primary/5 disabled:opacity-40 disabled:not-allowed" 
      onClick={handleExport}
      disabled={disabled || data.length === 0}
      title="Export to CSV"
    >
      <Download size={14} />
      <span className="leading-none">CSV</span>
    </button>
  );
};
