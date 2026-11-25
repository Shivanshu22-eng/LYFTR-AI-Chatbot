import React, { useState } from 'react';
import { recommendCrops } from '../api';

export default function CropPanel({ activeSession, onError }) {
  const [location, setLocation] = useState('');
  const [soilType, setSoilType] = useState('');
  const [soilPh, setSoilPh] = useState('');
  const [season, setSeason] = useState('');
  const [temperatureC, setTemperatureC] = useState('');
  const [rainfallMm, setRainfallMm] = useState('');
  const [irrigation, setIrrigation] = useState('moderate');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      const payload = {
        session_id: activeSession || null,
        location: location.trim() || null,
        soil_type: soilType || null,
        soil_ph: soilPh !== '' ? parseFloat(soilPh) : null,
        season: season || null,
        temperature_c: temperatureC !== '' ? parseFloat(temperatureC) : null,
        rainfall_mm: rainfallMm !== '' ? parseFloat(rainfallMm) : null,
        irrigation: irrigation || null,
      };
      const data = await recommendCrops(payload);
      setResult(data);
    } catch (err) {
      onError?.(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="feature-panel" data-testid="crop-panel">
      <div className="panel-header">
        <h2>🌱 Crop Recommendation Engine</h2>
        <p>Transparent suitability scoring using live Open-Meteo weather and soil/irrigation parameters.</p>
      </div>

      <form className="panel-card" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label className="field">
            <span>Location (auto-fetches weather)</span>
            <input
              type="text"
              className="text-input"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g., Nashik, Punjab, Iowa"
            />
          </label>

          <label className="field">
            <span>Soil Type</span>
            <select className="text-input" value={soilType} onChange={(e) => setSoilType(e.target.value)}>
              <option value="">Unknown / Not sure</option>
              <option value="loamy">Loamy</option>
              <option value="alluvial">Alluvial</option>
              <option value="clay">Clay</option>
              <option value="sandy">Sandy</option>
              <option value="black">Black (Regur)</option>
              <option value="red">Red</option>
              <option value="silt">Silt</option>
            </select>
          </label>

          <label className="field">
            <span>Soil pH (optional, 0–14)</span>
            <input
              type="number"
              step="0.1"
              min="0"
              max="14"
              className="text-input"
              value={soilPh}
              onChange={(e) => setSoilPh(e.target.value)}
              placeholder="e.g., 6.5"
            />
          </label>

          <label className="field">
            <span>Season</span>
            <select className="text-input" value={season} onChange={(e) => setSeason(e.target.value)}>
              <option value="">Any / Unspecified</option>
              <option value="Kharif">Kharif (Monsoon / Summer)</option>
              <option value="Rabi">Rabi (Winter)</option>
              <option value="Zaid">Zaid (Spring / Dry Summer)</option>
            </select>
          </label>

          <label className="field">
            <span>Irrigation / Water Availability</span>
            <select className="text-input" value={irrigation} onChange={(e) => setIrrigation(e.target.value)}>
              <option value="rainfed">Rainfed / None</option>
              <option value="moderate">Moderate / Supplemental</option>
              <option value="high">High / Canal / Drip</option>
            </select>
          </label>

          <label className="field">
            <span>Temperature Override (°C, optional)</span>
            <input
              type="number"
              step="0.5"
              className="text-input"
              value={temperatureC}
              onChange={(e) => setTemperatureC(e.target.value)}
              placeholder="Auto from location"
            />
          </label>

          <label className="field">
            <span>Rainfall Override (mm, optional)</span>
            <input
              type="number"
              step="1"
              min="0"
              className="text-input"
              value={rainfallMm}
              onChange={(e) => setRainfallMm(e.target.value)}
              placeholder="Auto from location"
            />
          </label>
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Evaluating…' : 'Recommend Crops'}
          </button>
        </div>
      </form>

      {result && (
        <div className="panel-card result-card">
          <div className="result-header">
            <h3>Top Crop Recommendations {result.location ? `for ${result.location}` : ''}</h3>
            {result.weather_used && (
              <span className="badge badge-info">
                Live Weather: {result.weather_used.current.temperature_c}°C ({result.weather_used.source})
              </span>
            )}
          </div>

          <p className="methodology-box">{result.scoring_methodology}</p>

          {result.assumptions?.length > 0 && (
            <div className="assumptions-box">
              <strong>Assumptions & Missing Info:</strong>
              <ul>
                {result.assumptions.map((a, idx) => (
                  <li key={idx}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="crop-list">
            {result.recommendations.map((rec) => (
              <div className="crop-card" key={rec.crop}>
                <div className="crop-card-top">
                  <h4>{rec.crop}</h4>
                  <div className="score-pill">
                    <span>{rec.suitability_score}/100</span>
                    <small>{rec.confidence} Confidence</small>
                  </div>
                </div>
                <div className="score-breakdown">
                  Temp {rec.score_breakdown.temperature_pts}/30 • Soil {rec.score_breakdown.soil_pts}/25 • Water {rec.score_breakdown.water_pts}/20 • Season {rec.score_breakdown.season_pts}/15 • pH {rec.score_breakdown.ph_pts}/10
                </div>
                <ul className="reasons-list">
                  {rec.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <div className="crop-meta">
                  <span><strong>Ideal:</strong> {rec.suitable_conditions.temperature_c}, pH {rec.suitable_conditions.soil_ph}, {rec.suitable_conditions.soil_types.join('/')}</span>
                  <span><strong>Limitations:</strong> {rec.limitations}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
