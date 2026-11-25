import React, { useState } from 'react';
import { fetchWeather } from '../api';

export default function WeatherPanel({ activeSession, onError }) {
  const [location, setLocation] = useState('');
  const [loading, setLoading] = useState(false);
  const [weather, setWeather] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!location.trim() || loading) return;
    setLoading(true);
    try {
      const data = await fetchWeather(location.trim(), activeSession);
      setWeather(data);
    } catch (err) {
      onError?.(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="feature-panel" data-testid="weather-panel">
      <div className="panel-header">
        <h2>🌦️ Live Weather Information</h2>
        <p>Real-time conditions and 5-day forecast powered by Open-Meteo.</p>
      </div>

      <form className="panel-card" onSubmit={handleSearch}>
        <div className="form-row">
          <input
            type="text"
            className="text-input"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Enter city or location (e.g., Pune, London, Tokyo)…"
            aria-label="Weather location"
          />
          <button type="submit" className="btn-primary" disabled={!location.trim() || loading}>
            {loading ? 'Fetching…' : 'Get Weather'}
          </button>
        </div>
      </form>

      {weather && (
        <div className="panel-card result-card">
          <div className="result-header">
            <div>
              <h3>{weather.resolved_name}</h3>
              <small className="muted-text">
                Lat {weather.latitude}, Lon {weather.longitude} • {weather.timezone}
              </small>
            </div>
            <span className="badge badge-info">
              Source: {weather.source} • {weather.fetched_at}
            </span>
          </div>

          <div className="stats-grid">
            <div className="stat-box">
              <span className="stat-label">Temperature</span>
              <span className="stat-value">{weather.current.temperature_c} °C</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Humidity</span>
              <span className="stat-value">{weather.current.humidity_pct} %</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Rainfall</span>
              <span className="stat-value">{weather.current.rainfall_mm ?? 0} mm</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Wind Speed</span>
              <span className="stat-value">{weather.current.wind_speed_kmh} km/h</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Condition</span>
              <span className="stat-value">{weather.current.condition}</span>
            </div>
          </div>

          {weather.forecast?.length > 0 && (
            <>
              <h4 className="subsection-title">5-Day Forecast</h4>
              <div className="forecast-grid">
                {weather.forecast.map((day) => (
                  <div className="forecast-card" key={day.date}>
                    <div className="fc-date">{day.date}</div>
                    <div className="fc-cond">{day.condition}</div>
                    <div className="fc-temp">
                      {day.temp_min_c}° – {day.temp_max_c}°C
                    </div>
                    <div className="fc-rain">💧 {day.precipitation_mm ?? 0} mm</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
