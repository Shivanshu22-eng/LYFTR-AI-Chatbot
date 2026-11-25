const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000'
).replace(/\/+$/, '');

/**
 * Check backend health.
 */
export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

/**
 * Send a chat message.
 */
export async function sendMessage(message, sessionId = null, model = null) {
  const body = { message };
  if (sessionId) body.session_id = sessionId;
  if (model) body.model = model;

  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Chat request failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch messages for a session.
 */
export async function fetchMessages(sessionId) {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(`Failed to load messages: ${res.status}`);
  return res.json();
}

/**
 * List all sessions.
 */
export async function fetchSessions() {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error(`Failed to load sessions: ${res.status}`);
  return res.json();
}

/**
 * Create a new session.
 */
export async function createSession() {
  const res = await fetch(`${API_BASE}/sessions`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return res.json();
}

/**
 * Analyze an uploaded image (JPG, JPEG, PNG, WEBP) via multimodal Gemini.
 */
export async function analyzeImage(file, prompt = '', sessionId = null) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('prompt', prompt || '');
  if (sessionId) formData.append('session_id', sessionId);

  const res = await fetch(`${API_BASE}/analyze-image`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Image analysis failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch live weather and 5-day forecast from Open-Meteo via backend.
 */
export async function fetchWeather(location, sessionId = null) {
  const params = new URLSearchParams({ location });
  if (sessionId) params.set('session_id', sessionId);
  const res = await fetch(`${API_BASE}/weather?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Weather lookup failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Request crop suitability recommendations.
 */
export async function recommendCrops(payload) {
  const res = await fetch(`${API_BASE}/crop-recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Crop recommendation failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Fetch persisted activity history (image analyses, weather queries, crop recommendations).
 */
export async function fetchActivityHistory(sessionId = null) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/history/activity${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(`Failed to load activity history: ${res.status}`);
  return res.json();
}
