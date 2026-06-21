import React, { useState, useEffect } from 'react';
import axios from 'axios';
import MapContainer from './MapContainer';
import SidePanel from './SidePanel';
import { ChevronDown, Layers } from 'lucide-react';
import './Dashboard.css';

const API_BASE = 'http://127.0.0.1:8001/api/v1';
const SEV_API = 'http://127.0.0.1:8001/api/v1/traffic-severity';

const Dashboard = () => {
  const [locations, setLocations] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [timestamp, setTimestamp] = useState('2024-03-26T14:00:00');
  
  useEffect(() => {
    // Load base locations
    const fetchLocations = async () => {
      try {
        const res = await axios.get(`${SEV_API}/locations`);
        setLocations(res.data);
        setLoading(false);
      } catch (err) {
        console.error("Failed to load locations", err);
        setLoading(false);
      }
    };
    fetchLocations();
  }, []);

  useEffect(() => {
    // Load predictions when timestamp changes
    const fetchPredictions = async () => {
      if (!timestamp) return;
      try {
        const res = await axios.get(`${SEV_API}/predict?timestamp=${timestamp}&top_n=20`);
        setPredictions(res.data);
      } catch (err) {
        console.error("Failed to load predictions", err);
      }
    };
    fetchPredictions();
  }, [timestamp]);

  return (
    <div className="dashboard-container">
      {/* Breadcrumb & Filter Bar overlay */}
      <div className="dashboard-header-overlay">
        <div className="breadcrumb">
          Home <span className="separator">&gt;</span> Urban Intel <span className="separator">&gt;</span> <strong>Map Dashboard</strong>
        </div>
        <div className="filter-controls">
          <button className="dropdown-btn">
            Precinct/District Selector <ChevronDown size={16} />
          </button>
        </div>
      </div>
      
      {/* Map Area */}
      <div className="map-area">
        <MapContainer locations={locations} predictions={predictions} />
        
        {/* Floating Legend */}
        <div className="map-legend">
          <h4 className="legend-title">MAP LEGEND</h4>
          <div className="legend-item">
            <span className="legend-color high-congestion"></span>
            <span className="legend-label">High Congestion</span>
          </div>
          <div className="legend-item">
            <span className="legend-icon bars"></span>
            <span className="legend-label">Parking Violations</span>
          </div>
          <div className="legend-item">
            <span className="legend-icon pin"></span>
            <span className="legend-label">Reported Illegal Parking</span>
          </div>
          <div className="legend-footer">
            <span className="badge traffic">Traffic</span>
            <span className="badge parking">Parking</span>
          </div>
        </div>
      </div>

      {/* Right Sidebar */}
      <SidePanel predictions={predictions} />
    </div>
  );
};

export default Dashboard;
