import { Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeProvider';
import MainLayout from './components/MainLayout';

// Pages
import Dashboard from './pages/Dashboard';
import StockDetail from './pages/StockDetail';
import Discover from './pages/Discover';
import Intelligence from './pages/Intelligence';
import System from './pages/System';
import Backtest from './pages/Backtest';

import './App.css';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/stocks/:symbol" element={<StockDetail />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/intel" element={<Intelligence />} />
          <Route path="/system" element={<System />} />
          <Route path="/backtest" element={<Backtest />} />
        </Routes>
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
