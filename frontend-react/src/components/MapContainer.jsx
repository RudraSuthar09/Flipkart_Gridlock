import React from 'react';
import { MapContainer as LeafletMap, TileLayer, Polygon, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './MapContainer.css';

// Fix Leaflet's default icon paths
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Custom Icon for parking
const parkingIcon = new L.Icon({
  iconUrl: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%23854d0e" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" fill="%23facc15"/><circle cx="12" cy="10" r="3" fill="%23facc15" stroke="%23854d0e"/></svg>',
  iconSize: [32, 32],
  iconAnchor: [16, 32],
  popupAnchor: [0, -32]
});

// Helper to generate hexagon points
const createHexagon = (lat, lng, radius) => {
  const points = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    // approx adjustment for lat/lng projection distortion at this latitude
    const dLat = radius * Math.sin(angle);
    const dLng = (radius / Math.cos(lat * Math.PI / 180)) * Math.cos(angle);
    points.push([lat + dLat, lng + dLng]);
  }
  return points;
};

const MapContainer = ({ locations, predictions }) => {
  const defaultCenter = [12.9716, 77.5946]; // Bengaluru
  const zoom = 12;

  return (
    <div className="map-wrapper">
      <LeafletMap center={defaultCenter} zoom={zoom} style={{ height: '100%', width: '100%' }} zoomControl={false}>
        {/* Using a light basemap to match UI */}
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>'
        />
        
        {predictions.map((pred, idx) => {
          // Only show top 20 or so as hexbins
          if (idx >= 20) return null;
          
          const lat = parseFloat(pred.latitude);
          const lng = parseFloat(pred.longitude);
          if (isNaN(lat) || isNaN(lng)) return null;

          const hexRadius = 0.005; // ~500m
          const hexPoints = createHexagon(lat, lng, hexRadius);
          
          // opacity based on prediction score
          const opacity = Math.max(0.2, Math.min(0.8, pred.lightgbm_prediction * 10));

          return (
            <React.Fragment key={`pred-${pred.location_key}`}>
              <Polygon 
                positions={hexPoints} 
                pathOptions={{ 
                  color: 'transparent',
                  fillColor: '#facc15', 
                  fillOpacity: opacity 
                }} 
              />
              {/* Add a marker for the top 5 */}
              {idx < 5 && (
                <Marker position={[lat, lng]} icon={parkingIcon}>
                  <Popup>
                    <div className="custom-popup">
                      <strong>{pred.area || pred.location_key}</strong>
                      <br/>
                      Congestion Impact: {Math.round(pred.lightgbm_prediction * 1000)}%
                    </div>
                  </Popup>
                </Marker>
              )}
            </React.Fragment>
          );
        })}
      </LeafletMap>
      
      {/* Custom Zoom Controls to match UI placement */}
      <div className="custom-zoom-controls">
        <button className="zoom-btn">+</button>
        <button className="zoom-btn">-</button>
      </div>
    </div>
  );
};

export default MapContainer;
