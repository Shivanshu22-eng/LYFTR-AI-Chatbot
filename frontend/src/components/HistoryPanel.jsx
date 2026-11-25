import React, { useEffect, useState } from 'react';
import { fetchActivityHistory } from '../api';

export default function HistoryPanel({
  sessions,
  activeSession,
  onSelectSession,
  onOpenChat,
  onError,
}) {
  const [activity, setActivity] = useState({
    image_analyses: [],
    weather_queries: [],
    crop_recommendations: [],
  });
  const [loading, setLoading] = useState(false);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await fetchActivityHistory();
      setActivity(data);
    } catch (err) {
      onError?.(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  return (
    <section className="feature-panel" data-testid="history-panel">
      <div className="panel-header">
        <div className="history-header-row">
          <div>
            <h2>🗂️ Chat & Activity History</h2>
            <p>All sessions, image analyses, weather lookups, and crop recommendations persisted in SQLite.</p>
          </div>
          <button type="button" className="btn-secondary" onClick={loadHistory} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="panel-card">
        <h3 className="subsection-title">Chat Sessions ({sessions.length})</h3>
        {sessions.length === 0 ? (
          <p className="muted-text">No chat sessions yet.</p>
        ) : (
          <div className="history-list">
            {sessions.map((s) => (
              <button
                key={s.id}
                className={`history-item ${s.id === activeSession ? 'active' : ''}`}
                onClick={() => {
                  onSelectSession(s.id);
                  onOpenChat();
                }}
              >
                <span className="history-title">💬 {s.title}</span>
                <small className="muted-text">{s.updated_at}</small>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="panel-card">
        <h3 className="subsection-title">Recent Image Analyses ({activity.image_analyses?.length || 0})</h3>
        {activity.image_analyses?.length === 0 ? (
          <p className="muted-text">No image analyses recorded yet.</p>
        ) : (
          <div className="history-list">
            {activity.image_analyses.map((item) => (
              <div className="history-record" key={item.id}>
                <div className="record-top">
                  <strong>🖼️ {item.filename}</strong>
                  <small className="muted-text">{item.created_at}</small>
                </div>
                <p className="record-sub">Prompt: {item.prompt}</p>
                <p className="record-body">{item.analysis.slice(0, 220)}{item.analysis.length > 220 ? '…' : ''}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel-card">
        <h3 className="subsection-title">Recent Weather Queries ({activity.weather_queries?.length || 0})</h3>
        {activity.weather_queries?.length === 0 ? (
          <p className="muted-text">No weather queries recorded yet.</p>
        ) : (
          <div className="history-list">
            {activity.weather_queries.map((w) => (
              <div className="history-record" key={w.id}>
                <div className="record-top">
                  <strong>🌦️ {w.resolved_name}</strong>
                  <small className="muted-text">{w.source} • {w.fetched_at}</small>
                </div>
                <p className="record-sub">
                  {w.temperature_c}°C • Humidity {w.humidity_pct}% • Wind {w.wind_speed_kmh} km/h • {w.condition}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel-card">
        <h3 className="subsection-title">Recent Crop Recommendations ({activity.crop_recommendations?.length || 0})</h3>
        {activity.crop_recommendations?.length === 0 ? (
          <p className="muted-text">No crop recommendations recorded yet.</p>
        ) : (
          <div className="history-list">
            {activity.crop_recommendations.map((c) => {
              let topCrop = '';
              try {
                const parsed = JSON.parse(c.recommendations_json || '[]');
                topCrop = parsed[0] ? `${parsed[0].crop} (${parsed[0].suitability_score}/100)` : '';
              } catch {
                topCrop = '';
              }
              return (
                <div className="history-record" key={c.id}>
                  <div className="record-top">
                    <strong>🌱 {c.location || 'Custom Inputs'} — {c.soil_type || 'Neutral soil'}</strong>
                    <small className="muted-text">{c.created_at}</small>
                  </div>
                  <p className="record-sub">
                    Temp {c.temperature_c}°C • Rain {c.rainfall_mm} mm • Season {c.season || 'Any'} {topCrop ? `• Top: ${topCrop}` : ''}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
