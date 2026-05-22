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
  X,
  ArrowLeft,
  Play
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
    { to: '/paper', label: 'Paper', icon: <Play size={20} /> },
    { to: '/backtest', label: 'Backtest', icon: <FlaskConical size={20} /> },
    { to: '/intel', label: 'Intelligence', icon: <ShieldAlert size={20} /> },
    { to: '/system', label: 'System', icon: <Settings size={20} /> },
  ];

  return (
    <div className="flex min-h-screen w-full bg-bg">
      {/* Mobile Header */}
      <header className="flex fixed top-0 left-0 right-0 h-16 px-4 items-center justify-between z-50 border-b border-border bg-bg-secondary/80 backdrop-blur-lg lg:hidden">
        <div className="flex items-center gap-2">
          {location.pathname === '/' ? (
            <button 
              onClick={() => setIsSidebarOpen(true)}
              className="p-2 text-text-muted hover:text-text active:scale-95 transition-transform"
            >
              <Menu size={24} />
            </button>
          ) : (
            <NavLink 
              to="/"
              className="p-2 text-text-muted hover:text-text active:scale-95 transition-transform"
            >
              <ArrowLeft size={24} />
            </NavLink>
          )}
          <div className="flex items-center gap-2.5 font-black text-lg group">
            <div className="bg-green-500 p-1.5 rounded-lg shadow-lg shadow-green-500/20 group-hover:rotate-12 transition-transform">
                <Activity size={18} className="text-white" />
            </div>
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400 bg-clip-text text-transparent tracking-tighter">Screener AI</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <GlobalSearch />
          <ThemeToggle />
        </div>
      </header>

      {/* Sidebar (Mobile Overlay + Desktop Persistent) */}
      <aside className={`fixed inset-y-0 left-0 z-[100] w-[280px] bg-bg-secondary border-r border-border transition-transform duration-300 transform lg:translate-x-0 ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'} lg:flex lg:flex-col lg:p-6 lg:rounded-none lg:shadow-none p-6`}>
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3 font-black text-2xl text-text tracking-tighter group">
            <div className="bg-green-500 p-1.5 rounded-lg shadow-lg shadow-green-500/20 group-hover:rotate-12 transition-transform">
                <Activity size={24} className="text-white" />
            </div>
            <span className="bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-400 dark:to-indigo-400 bg-clip-text text-transparent">Screener AI</span>
          </div>
          <button 
            onClick={() => setIsSidebarOpen(false)}
            className="p-2 -mr-2 text-text-muted hover:text-text lg:hidden"
          >
            <X size={24} />
          </button>
        </div>

        <div className="mb-10">
          <GlobalSearch />
        </div>

        <nav className="flex flex-col gap-2.5 flex-1">
          {navItems.map((item) => (
            <NavLink 
              key={item.to} 
              to={item.to} 
              className={({ isActive }) => `flex items-center gap-4 px-5 py-3.5 rounded-xl font-bold transition-all duration-200 border-2 ${isActive ? 'bg-blue-600 text-white border-blue-600 shadow-lg shadow-blue-500/30' : 'text-slate-500 border-transparent hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'}`}
            >
              {item.icon}
              <span className="tracking-tight">{item.label}</span>
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
      <main className="flex-1 pt-20 px-4 pb-24 w-full max-w-[1440px] mx-auto lg:ml-[280px] lg:pt-10 lg:px-10 lg:pb-10">
        {children}
      </main>

      {/* Mobile Bottom Navigation */}
      <nav className="flex fixed bottom-0 left-0 right-0 h-[80px] justify-around items-center z-50 border-t border-border px-2 bg-bg-secondary/80 backdrop-blur-lg lg:hidden pb-safe">
        {navItems.map((item) => (
          <NavLink 
            key={item.to} 
            to={item.to} 
            className={({ isActive }) => `group flex flex-col items-center justify-center gap-1.5 transition-all flex-1 h-full ${isActive ? 'text-blue-600' : 'text-slate-500'}`}
          >
            {({ isActive }) => (
              <>
                <div className={`transition-all duration-300 ${isActive ? '-translate-y-1 scale-110' : 'group-active:scale-90'}`}>
                  {item.icon}
                </div>
                <span className={`text-[9px] font-black uppercase tracking-[0.15em] transition-opacity ${isActive ? 'opacity-100' : 'opacity-50'}`}>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
};

export default MainLayout;
