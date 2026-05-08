import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import StockDetail from './pages/StockDetail';
import Reports from './pages/Reports';
import Screener from './pages/Screener';
import Screens from './pages/Screens';
import Navigation from './components/Navigation';
import { useTheme } from './hooks/useTheme';
import './App.css';

function App() {
  useTheme();

  return (
    <div className="app-container">
      <Navigation>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/stocks/:symbol" element={<StockDetail />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/screener" element={<Screener />} />
          <Route path="/screens" element={<Screens />} />
        </Routes>
      </Navigation>
    </div>
  );
}

export default App;
