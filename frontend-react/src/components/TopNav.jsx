import React from 'react';
import { Search } from 'lucide-react';
import './TopNav.css';

export default function TopNav({ activePage, setActivePage, searchQuery, onSearchChange, showSearch }) {
  return (
    <header className="topnav">
      <div className="topnav-left">
        <div className="topnav-brand">
          <div className="brand-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-dept">Sugama Sanchara</span>
            <span className="brand-name">Bengaluru</span>
          </div>
        </div>

        <nav className="topnav-links">
          <button className={`nav-link ${activePage === 'home'       ? 'active' : ''}`} onClick={() => setActivePage('home')}>Home</button>
          <button className={`nav-link ${activePage === 'prediction' ? 'active' : ''}`} onClick={() => setActivePage('prediction')}>Count Heatmap</button>
          <button className={`nav-link ${activePage === 'severity'   ? 'active' : ''}`} onClick={() => setActivePage('severity')}>Severity Heatmap</button>
          <button className={`nav-link ${activePage === 'pis'        ? 'active' : ''}`} onClick={() => setActivePage('pis')}>Impact Scores</button>
          <button className={`nav-link ${activePage === 'reports'    ? 'active' : ''}`} onClick={() => setActivePage('reports')}>Reports</button>
          <button className={`nav-link nav-link-deploy ${activePage === 'deployment' ? 'active' : ''}`} onClick={() => setActivePage('deployment')}>Deployment</button>
          <span className="nav-divider">|</span>
          <a href="http://127.0.0.1:8001/docs" target="_blank" rel="noreferrer" className="nav-link">API Docs ↗</a>
        </nav>
      </div>

      {showSearch && (
        <div className="topnav-right">
          <div className="search-bar">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Search junctions / stations…"
              value={searchQuery}
              onChange={e => onSearchChange(e.target.value)}
            />
            {searchQuery && (
              <button className="search-clear" onClick={() => onSearchChange('')}>×</button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
