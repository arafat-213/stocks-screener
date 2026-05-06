import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Screener from './pages/Screener';
import StockDetail from './pages/StockDetail';
import Reports from './pages/Reports';

function App() {
  return (
    <Router>
      <div>
        <nav style={{ padding: '1rem', borderBottom: '1px solid #ccc' }}>
          <Link to=\"/\" style={{ marginRight: '1rem' }}>Dashboard</Link>
          <Link to=\"/screener\" style={{ marginRight: '1rem' }}>Screener</Link>
          <Link to=\"/reports\">Reports</Link>
        </nav>
        
        <main style={{ padding: '1rem' }}>
          <Routes>
            <Route path=\"/\" element={<Dashboard />} />
            <Route path=\"/screener\" element={<Screener />} />
            <Route path=\"/stock/:symbol\" element={<StockDetail />} />
            <Route path=\"/reports\" element={<Reports />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
