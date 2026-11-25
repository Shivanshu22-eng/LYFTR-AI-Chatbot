const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000'
).replace(/\/+$/, '');

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

function getToken() {
  return localStorage.getItem('lyftr_token');
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...extra }
    : { 'Content-Type': 'application/json', ...extra };
}

function authHeadersNoContentType() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse(res) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

export function saveAuth(tokenData) {
  localStorage.setItem('lyftr_token', tokenData.access_token);
  localStorage.setItem('lyftr_user', JSON.stringify({
    id: tokenData.user_id,
    email: tokenData.email,
    role: tokenData.role,
  }));
}

export function clearAuth() {
  localStorage.removeItem('lyftr_token');
  localStorage.removeItem('lyftr_user');
}

export function getCurrentUser() {
  try {
    const u = localStorage.getItem('lyftr_user');
    return u ? JSON.parse(u) : null;
  } catch {
    return null;
  }
}

export async function register(email, password) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await handleResponse(res);
  saveAuth(data);
  return data;
}

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await handleResponse(res);
  saveAuth(data);
  return data;
}

export async function fetchMe() {
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Original Chat API (unchanged)
// ---------------------------------------------------------------------------

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

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

export async function fetchMessages(sessionId) {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(`Failed to load messages: ${res.status}`);
  return res.json();
}

export async function fetchSessions() {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error(`Failed to load sessions: ${res.status}`);
  return res.json();
}

export async function createSession() {
  const res = await fetch(`${API_BASE}/sessions`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return res.json();
}

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

export async function fetchActivityHistory(sessionId = null) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/history/activity${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(`Failed to load activity history: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Image Generation API
// ---------------------------------------------------------------------------

export async function generateImage(prompt, style = 'photorealistic', aspectRatio = '1:1', numImages = 1) {
  const res = await fetch(`${API_BASE}/images/generate`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      prompt,
      style,
      aspect_ratio: aspectRatio,
      num_images: numImages,
    }),
  });
  return handleResponse(res);
}

export async function fetchImageHistory(limit = 50, offset = 0) {
  const res = await fetch(`${API_BASE}/images/history?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function fetchImageRecord(imageId) {
  const res = await fetch(`${API_BASE}/images/${imageId}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export async function adminListUsers(limit = 100, offset = 0) {
  const res = await fetch(`${API_BASE}/admin/users?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function adminUpdateUserPermissions(userId, updates) {
  const res = await fetch(`${API_BASE}/admin/users/${userId}/permissions`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(updates),
  });
  return handleResponse(res);
}

export async function adminUpdateImageSettings(settings) {
  const res = await fetch(`${API_BASE}/admin/settings/image-generation`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(settings),
  });
  return handleResponse(res);
}

export async function adminGetSettings() {
  const res = await fetch(`${API_BASE}/admin/settings`, { headers: authHeaders() });
  return handleResponse(res);
}

export async function adminGetAuditLogs(limit = 100, offset = 0) {
  const res = await fetch(`${API_BASE}/admin/audit-logs?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function adminGetAllGenerations(limit = 100, offset = 0) {
  const res = await fetch(`${API_BASE}/admin/image-generations?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}
