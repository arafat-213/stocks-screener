import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Filter, 
  FileText, 
  Activity, 
  Play, 
  Loader2 
} from 'lucide-react';
import { fetchPipelineStatus, runScreener } from '../api/client';
import './Navigation.css';

const Navigation = ({ children }) => {
  const [pipeline, setPipeline] = useState(null);
  const [isRunning, setIsRunning] = useState(false);

  const getStatus = async () => {
    try {
      const response = await fetchPipelineStatus();
      setPipeline(response.data);
    } catch (error) {
      console.error('Failed to fetch pipeline status:', error);
    }
  };

  useEffect(() => {
    getStatus();
    const interval = setInterval(getStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleRunPipeline = async () => {
    setIsRunning(true);
    try {
      await runScreener();
      await getStatus();
    } catch (error) {
      console.error('Failed to run pipeline:', error);
    } finally {
      setIsRunning(false);
    }
  };

  const navItems = [
    { to: '/', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { to: '/screener', label: 'Screener', icon: <Filter size={20} /> },
    { to: '/reports', label: 'Reports', icon: <FileText size={20} /> },
  ];

  return (
    <div className="navigation-container">
      {/* Desktop/Tablet Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Activity color="var(--color-bullish)" size={28} />
          <span className="brand-text">Screener AI</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink 
              key={item.to} 
              to={item.to} 
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              title={item.label}
            >
              {item.icon}
              <span className="link-text">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="pipeline-health">
            <h3>Pipeline Health</h3>
            <div className="health-stat">
              <span>Fetched</span>
              <span className="stat-val">{pipeline?.stocks_fetched || 0}</span>
            </div>
            <div className="health-stat">
              <span>Scored</span>
              <span className="stat-val">{pipeline?.stocks_scored || 0}</span>
            </div>
          </div>

          <button 
            className="run-pipeline-btn" 
            onClick={handleRunPipeline}
            disabled={isRunning || pipeline?.status === 'running'}
          >
            {isRunning || pipeline?.status === 'running' ? (
              <Loader2 className="animate-spin" size={18} />
            ) : (
              <Play size={18} />
            )}
            <span className="btn-text">Run Pipeline</span>
          </button>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="bottom-nav">
        {navItems.map((item) => (
          <NavLink 
            key={item.to} 
            to={item.to} 
            className={({ isActive }) => `bottom-nav-link ${isActive ? 'active' : ''}`}
          >
            {item.icon}
            <span className="bottom-nav-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <main className="main-content">
        {children}
      </main>
    </div>
  );
};

export default Navigation;
