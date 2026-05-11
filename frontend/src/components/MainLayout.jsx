import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Search, 
  ShieldAlert, 
  Settings, 
  Activity
} from 'lucide-react';
import ThemeToggle from './ThemeToggle';
import GlobalSearch from './GlobalSearch';
import './MainLayout.css';

const MainLayout = ({ children }) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const location = useLocation();

  // Close sidebar on route change (mobile)
  useEffect(() => {
    if (isSidebarOpen) {
      const timer = setTimeout(() => setIsSidebarOpen(false), 0);
      return () => clearTimeout(timer);
    }
  }, [location, isSidebarOpen]);

  const navItems = [
    { to: '/', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { to: '/discover', label: 'Discover', icon: <Search size={20} /> },
    { to: '/intel', label: 'Intelligence', icon: <ShieldAlert size={20} /> },
    { to: '/system', label: 'System', icon: <Settings size={20} /> },
  ];

  return (
    <div className="main-layout">
      {/* Mobile Header */}
      <header className="mobile-header glass">
        <div className="brand">
          <Activity size={24} className="text-bullish" />
          <span>Screener AI</span>
        </div>
        <div className="mobile-header-actions">
          <GlobalSearch />
          <ThemeToggle />
        </div>
      </header>

      {/* Desktop Sidebar */}
      <aside className={`sidebar card ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="brand">
            <Activity size={28} className="text-bullish" />
            <span>Screener AI</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <NavLink 
              key={item.to} 
              to={item.to} 
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <ThemeToggle />
          <div className="version-info text-muted">v2.1.0</div>
        </div>
      </aside>

      {/* Overlay for mobile sidebar */}
      {isSidebarOpen && <div className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)} />}

      {/* Main Content Area */}
      <main className="content-area">
        {children}
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="bottom-nav glass">
        {navItems.map((item) => (
          <NavLink 
            key={item.to} 
            to={item.to} 
            className={({ isActive }) => `bottom-nav-item ${isActive ? 'active' : ''}`}
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
};

export default MainLayout;
