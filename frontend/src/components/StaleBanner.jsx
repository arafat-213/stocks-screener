import React from 'react';
import { AlertTriangle, Play } from 'lucide-react';

export default function StaleBanner({ lastUpdated, dataAgeHours, onRunPipeline, isBusy }) {
    if (!lastUpdated) return null;
    
    const dateStr = new Date(lastUpdated).toLocaleString('en-IN', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
    
    return (
        <div className="flex flex-col md:flex-row items-start md:items-center gap-3 bg-warning/10 text-text border border-warning/40 p-3 md:px-4 md:py-3 rounded-md mb-6">
            <div className="shrink-0 text-warning flex">
                <AlertTriangle size={20} />
            </div>
            <div className="flex-1 text-sm leading-relaxed">
                <strong>Data is {dataAgeHours} hours old.</strong>
                <span className="ml-0 md:ml-2 opacity-80 block md:inline mt-0.5 md:mt-0"> Last pipeline run: {dateStr}. Run pipeline to refresh scores.</span>
            </div>
            {onRunPipeline && (
                <button 
                    className="shrink-0 bg-warning text-black px-3.5 py-1.5 rounded-sm cursor-pointer font-semibold text-[0.8rem] flex items-center gap-1.5 transition-opacity hover:opacity-85 disabled:opacity-50 disabled:cursor-not-allowed w-full md:w-auto justify-center" 
                    onClick={() => onRunPipeline()}
                    disabled={isBusy}
                >
                    <Play size={14} fill="currentColor" />
                    <span>Run Now</span>
                </button>
            )}
        </div>
    );
}
