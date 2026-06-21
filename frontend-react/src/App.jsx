import React, { useState } from 'react';
import TopNav from './components/TopNav';
import PredictionPage from './pages/PredictionPage';
import SeverityPage from './pages/SeverityPage';
import Chatbot from './components/Chatbot';
import './App.css';

function App() {
  const [activePage, setActivePage] = useState('prediction');
  // Lift predictions up so chatbot can read them
  const [sharedPredictions, setSharedPredictions] = useState([]);

  return (
    <div className="app-container">
      <TopNav activePage={activePage} setActivePage={setActivePage} />
      <main className="main-content">
        {activePage === 'prediction' ? (
          <PredictionPage onPredictionsLoaded={setSharedPredictions} />
        ) : (
          <SeverityPage onPredictionsLoaded={setSharedPredictions} />
        )}
      </main>
      {/* Global sticky chatbot */}
      <Chatbot predictions={sharedPredictions} activePage={activePage} />
    </div>
  );
}

export default App;
