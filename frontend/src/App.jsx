import React from 'react';
import Dashboard from './pages/Dashboard';
import './App.css';

function App() {
  // In a real app, we might have a router here.
  // For now, we just render the Dashboard.
  return (
    <div className="app-container">
      <Dashboard />
    </div>
  );
}

export default App;
