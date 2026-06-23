import { Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeProvider';
import MainLayout from './components/MainLayout';

// Pages
import Dashboard from './pages/Dashboard';
import Watchlist from './pages/Watchlist';
import StockDetail from './pages/StockDetail';
import Discover from './pages/Discover';
import Intelligence from './pages/Intelligence';
import System from './pages/System';
import Backtest from './pages/Backtest';
import Portfolio from './pages/Portfolio';
import S3PaperBook from './pages/S3PaperBook';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <Routes>
          <Route path='/' element={<Dashboard />} />
          <Route path='/watchlist' element={<Watchlist />} />
          <Route path='/stocks/:symbol' element={<StockDetail />} />
          <Route path='/discover' element={<Discover />} />
          <Route path='/portfolio' element={<Portfolio />} />
          <Route path='/paper-v2' element={<S3PaperBook />} />
          <Route
            path='/journal'
            element={<Navigate to='/portfolio' replace />}
          />
          <Route path='/paper' element={<Navigate to='/portfolio' replace />} />
          <Route path='/intel' element={<Intelligence />} />
          <Route path='/system' element={<System />} />
          <Route path='/backtest' element={<Backtest />} />
        </Routes>
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
