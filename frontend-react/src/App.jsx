import React, { useState, useEffect } from 'react';
import axios from 'axios';
import TopNav from './components/TopNav';
import HomePage from './pages/HomePage';
import PredictionPage from './pages/PredictionPage';
import SeverityPage from './pages/SeverityPage';
import PISPage from './pages/PISPage';
import ReportsPage from './pages/ReportsPage';
import RoutePage from './pages/RoutePage';
import DeploymentPage from './pages/DeploymentPage';
import Chatbot from './components/Chatbot';
import './App.css';

export default function App() {
  const [activePage, setActivePage]               = useState('home');
  const [sharedPredictions, setSharedPredictions] = useState([]);
  const [searchQuery, setSearchQuery]             = useState('');
  const [selectedStation, setSelectedStation]     = useState('');
  const [persistenceScores, setPersistenceScores] = useState({});

  useEffect(() => {
    axios.get('/api/v1/persistence', { timeout: 15000 })
      .then(r => setPersistenceScores(r.data || {}))
      .catch(() => {});
  }, []);

  const handlePageChange = page => {
    setActivePage(page);
    setSelectedStation('');
    setSearchQuery('');
  };

  const sharedProps = {
    onPredictionsLoaded: setSharedPredictions,
    searchQuery,
    selectedStation,
    onStationChange:     setSelectedStation,
    persistenceScores,
  };

  const showSearch = activePage === 'prediction' || activePage === 'severity';

  return (
    <div className="app-container">
      <TopNav
        activePage={activePage}
        setActivePage={handlePageChange}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        showSearch={showSearch}
      />
      <main className="main-content">
        {activePage === 'home'       && <HomePage       onNavigate={handlePageChange} />}
        {activePage === 'prediction' && <PredictionPage {...sharedProps} />}
        {activePage === 'severity'   && <SeverityPage   {...sharedProps} />}
        {activePage === 'pis'        && <PISPage />}
        {activePage === 'reports'    && <ReportsPage />}
        {activePage === 'route'      && <RoutePage />}
        {activePage === 'deployment' && <DeploymentPage onPredictionsLoaded={setSharedPredictions} />}
      </main>
      {activePage !== 'home' && (
        <Chatbot predictions={sharedPredictions} activePage={activePage} />
      )}
    </div>
  );
}
