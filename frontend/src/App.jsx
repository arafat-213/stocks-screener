import { Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import StockDetail from './pages/StockDetail';
import Reports from './pages/Reports';
import Screener from './pages/Screener';
import './App.css';

function App() {
  return (
    <div className="app-container">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/stocks/:symbol" element={<StockDetail />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/screener" element={<Screener />} />
      </Routes>
    </div>
  );
}

export default App;
