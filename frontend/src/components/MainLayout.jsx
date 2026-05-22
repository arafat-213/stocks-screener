import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Search, 
  ShieldAlert, 
  Settings, 
  Activity,
  FlaskConical,
  Menu,
  X
} from 'lucide-react';
import ThemeToggle from './ThemeToggle';
import GlobalSearch from './GlobalSearch';

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
    { to: '/backtest', label: 'Backtest', icon: <FlaskConical size={20} /> },
    { to: '/system', label: 'System', icon: <Settings size={20} /> },
  ];

  return (
    <div className="flex min-h-screen w-full bg-bg">
      {/* Mobile Header */}
      <header className="flex fixed top-0 left-0 right-0 h-16 px-4 items-center justify-between z-50 border-b border-border bg-bg-secondary/70 backdrop-blur-md lg:hidden">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setIsSidebarOpen(true)}
            className="p-2 -ml-2 text-text-muted hover:text-text"
          >
            <Menu size={24} />
          </button>
          <div className="flex items-center gap-3 font-bold text-[1.1rem]">
            <Activity size={24} className="text-bullish" />
            <span>Screener AI</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <GlobalSearch />
          <ThemeToggle />
        </div>
      </header>

      {/* Sidebar (Mobile Overlay + Desktop Persistent) */}
      <aside className={`fixed inset-y-0 left-0 z-[100] w-[280px] bg-bg-secondary border-r border-border transition-transform duration-300 transform lg:translate-x-0 ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:flex lg:flex-col lg:p-6 lg:rounded-none lg:shadow-none p-6`}>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3 font-extrabold text-xl text-text">
            <Activity size={28} className="text-bullish" />
            <span>Screener AI</span>
          </div>
          <button 
            onClick={() => setIsSidebarOpen(false)}
            className="p-2 -mr-2 text-text-muted hover:text-text lg:hidden"
          >
            <X size={24} />
          </button>
        </div>

        <div className="mb-8">
          <GlobalSearch />
        </div>

        <nav className="flex flex-col gap-2 flex-1">
          {navItems.map((item) => (
            <NavLink 
              key={item.to} 
              to={item.to} 
              className={({ isActive }) => `flex items-center gap-3 px-4 py-3 rounded-md font-medium transition-all ${isActive ? 'bg-primary text-white shadow-[0_4px_12px_rgba(59,130,246,0.3)]' : 'text-text-muted hover:bg-bg-elevated hover:text-text'}`}
            >
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="pt-6 border-t border-border flex items-center justify-between">
          <ThemeToggle />
          <div className="text-text-muted text-xs">v2.1.0</div>
        </div>
      </aside>

      {/* Overlay for mobile sidebar */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 z-[90] bg-black/50 backdrop-blur-sm lg:hidden" 
          onClick={() => setIsSidebarOpen(false)} 
        />
      )}

      {/* Main Content Area */}
      <main className="flex-1 pt-20 px-4 pb-[100px] w-full max-w-[1440px] mx-auto lg:ml-[280px] lg:pt-10 lg:px-10 lg:pb-10">
        {children}
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="flex fixed bottom-0 left-0 right-0 h-[72px] justify-around items-center z-50 border-t border-border px-2 bg-bg-secondary/70 backdrop-blur-md lg:hidden">
        {navItems.map((item) => (
          <NavLink 
            key={item.to} 
            to={item.to} 
            className={({ isActive }) => `group flex flex-col items-center gap-1 text-[0.75rem] transition-all flex-1 ${isActive ? 'text-primary' : 'text-text-muted'}`}
          >
            {({ isActive }) => (
              <>
                <div className={`transition-transform duration-200 ${isActive ? '-translate-y-0.5' : ''}`}>
                  {item.icon}
                </div>
                <span>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
};

export default MainLayout;
