import React from 'react';
import './StaleBanner.css';
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
        <div className="stale-banner">
            <div className="stale-icon">
                <AlertTriangle size={20} />
            </div>
            <div className="stale-content">
                <strong>Data is {dataAgeHours} hours old.</strong>
                <span className="stale-subtext"> Last pipeline run: {dateStr}. Run pipeline to refresh scores.</span>
            </div>
            {onRunPipeline && (
                <button 
                    className="stale-run-btn" 
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
