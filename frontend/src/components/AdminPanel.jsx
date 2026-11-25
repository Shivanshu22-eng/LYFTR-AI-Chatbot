import React, { useState, useEffect } from 'react';
import {
  adminListUsers, adminUpdateUserPermissions,
  adminUpdateImageSettings, adminGetSettings,
  adminGetAuditLogs, adminGetAllGenerations,
} from '../api.js';

const ROLES = ['user', 'authorized_creator', 'admin'];
const CATEGORIES = ['safe', 'adult', 'violent', 'disturbing'];

export default function AdminPanel({ user }) {
  const [tab, setTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [settings, setSettings] = useState({});
  const [auditLogs, setAuditLogs] = useState([]);
  const [allGenerations, setAllGenerations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({});

  const showMessage = (msg, isError = false) => {
    if (isError) { setError(msg); setSuccess(''); }
    else { setSuccess(msg); setError(''); }
    setTimeout(() => { setError(''); setSuccess(''); }, 4000);
  };

  useEffect(() => {
    if (tab === 'users') loadUsers();
    else if (tab === 'settings') loadSettings();
    else if (tab === 'audit') loadAuditLogs();
    else if (tab === 'generations') loadGenerations();
  }, [tab]);

  const loadUsers = async () => {
    setLoading(true);
    try { setUsers(await adminListUsers()); }
    catch (e) { showMessage(e.message, true); }
    finally { setLoading(false); }
  };

  const loadSettings = async () => {
    setLoading(true);
    try { setSettings(await adminGetSettings()); }
    catch (e) { showMessage(e.message, true); }
    finally { setLoading(false); }
  };

  const loadAuditLogs = async () => {
    setLoading(true);
    try { setAuditLogs(await adminGetAuditLogs(100)); }
    catch (e) { showMessage(e.message, true); }
    finally { setLoading(false); }
  };

  const loadGenerations = async () => {
    setLoading(true);
    try { setAllGenerations(await adminGetAllGenerations(100)); }
    catch (e) { showMessage(e.message, true); }
    finally { setLoading(false); }
  };

  const startEdit = (u) => {
    setEditingUser(u.id);
    const cats = Array.isArray(u.allowed_categories) ? u.allowed_categories : ['safe'];
    setEditForm({
      role: u.role,
      is_active: u.is_active,
      daily_gen_limit: u.daily_gen_limit,
      allowed_categories: cats,
    });
  };

  const saveUserEdit = async (userId) => {
    setLoading(true);
    try {
      await adminUpdateUserPermissions(userId, editForm);
      showMessage('User updated successfully.');
      setEditingUser(null);
      await loadUsers();
    } catch (e) {
      showMessage(e.message, true);
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (cat) => {
    const current = editForm.allowed_categories || ['safe'];
    setEditForm({
      ...editForm,
      allowed_categories: current.includes(cat)
        ? current.filter((c) => c !== cat)
        : [...current, cat],
    });
  };

  const updateGlobalSetting = async (key, value) => {
    setLoading(true);
    try {
      const payload = {};
      if (key === 'image_generation_enabled') payload.image_generation_enabled = value === 'true';
      if (key === 'image_generation_default_daily_limit') payload.image_generation_default_daily_limit = parseInt(value);
      await adminUpdateImageSettings(payload);
      showMessage('Setting updated.');
      await loadSettings();
    } catch (e) {
      showMessage(e.message, true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="feature-panel admin-panel">
      <div className="panel-header">
        <h2>🛡️ Administrator Dashboard</h2>
        <p className="panel-subtitle">Signed in as <strong>{user?.email}</strong> · Admin</p>
      </div>

      {error && <div className="error-banner">⚠️ {error}</div>}
      {success && <div className="success-banner">✅ {success}</div>}

      {/* Tabs */}
      <div className="admin-tabs">
        {[
          { key: 'users', label: '👥 Users' },
          { key: 'settings', label: '⚙️ Settings' },
          { key: 'generations', label: '🎨 All Generations' },
          { key: 'audit', label: '📋 Audit Log' },
        ].map((t) => (
          <button
            key={t.key}
            className={`admin-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="loading-state">⏳ Loading…</div>}

      {/* Users Tab */}
      {tab === 'users' && !loading && (
        <div className="admin-section">
          <div className="section-header">
            <h3>User Management ({users.length} users)</h3>
            <button className="btn-refresh" onClick={loadUsers}>↻ Refresh</button>
          </div>
          <div className="users-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Active</th>
                  <th>Daily Limit</th>
                  <th>Categories</th>
                  <th>Joined</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <React.Fragment key={u.id}>
                    <tr className={!u.is_active ? 'suspended-row' : ''}>
                      <td>
                        <span className="user-email">{u.email}</span>
                        {u.id === user?.id && <span className="you-badge">You</span>}
                      </td>
                      <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                      <td><span className={u.is_active ? 'status-active' : 'status-suspended'}>
                        {u.is_active ? '✓ Active' : '✗ Suspended'}
                      </span></td>
                      <td>{u.daily_gen_limit === 0 ? 'Blocked' : u.daily_gen_limit + '/day'}</td>
                      <td>{(u.allowed_categories || ['safe']).join(', ')}</td>
                      <td>{new Date(u.created_at).toLocaleDateString()}</td>
                      <td>
                        <button className="btn-edit" onClick={() => startEdit(u)}>
                          ✏️ Edit
                        </button>
                      </td>
                    </tr>
                    {editingUser === u.id && (
                      <tr className="edit-row">
                        <td colSpan={7}>
                          <div className="edit-form">
                            <div className="edit-row-fields">
                              <div className="edit-field">
                                <label>Role</label>
                                <select
                                  value={editForm.role}
                                  onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                                  disabled={u.id === user?.id}
                                >
                                  {ROLES.map((r) => (
                                    <option key={r} value={r}>{r}</option>
                                  ))}
                                </select>
                              </div>
                              <div className="edit-field">
                                <label>Status</label>
                                <select
                                  value={editForm.is_active ? 'true' : 'false'}
                                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.value === 'true' })}
                                  disabled={u.id === user?.id}
                                >
                                  <option value="true">Active</option>
                                  <option value="false">Suspended</option>
                                </select>
                              </div>
                              <div className="edit-field">
                                <label>Daily Limit (0=blocked)</label>
                                <input
                                  type="number"
                                  min={0}
                                  max={1000}
                                  value={editForm.daily_gen_limit}
                                  onChange={(e) => setEditForm({ ...editForm, daily_gen_limit: parseInt(e.target.value) || 0 })}
                                />
                              </div>
                            </div>
                            <div className="edit-field">
                              <label>Allowed Content Categories</label>
                              <div className="category-checkboxes">
                                {CATEGORIES.map((cat) => (
                                  <label key={cat} className="cat-check">
                                    <input
                                      type="checkbox"
                                      checked={(editForm.allowed_categories || []).includes(cat)}
                                      onChange={() => toggleCategory(cat)}
                                      disabled={cat === 'safe'} // 'safe' always required
                                    />
                                    {cat}
                                    {cat === 'safe' && <span className="required-badge">required</span>}
                                  </label>
                                ))}
                              </div>
                            </div>
                            <div className="edit-actions">
                              <button className="btn-save" onClick={() => saveUserEdit(u.id)}>
                                💾 Save Changes
                              </button>
                              <button className="btn-cancel" onClick={() => setEditingUser(null)}>
                                Cancel
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Settings Tab */}
      {tab === 'settings' && !loading && (
        <div className="admin-section">
          <h3>⚙️ Global Image Generation Settings</h3>
          <div className="settings-grid">
            <div className="setting-card">
              <label className="setting-label">Image Generation Enabled</label>
              <div className="toggle-row">
                <span className={settings.image_generation_enabled === 'true' ? 'status-on' : 'status-off'}>
                  {settings.image_generation_enabled === 'true' ? '🟢 Enabled' : '🔴 Disabled'}
                </span>
                <button
                  className={`toggle-btn ${settings.image_generation_enabled === 'true' ? 'toggle-on' : 'toggle-off'}`}
                  onClick={() => updateGlobalSetting(
                    'image_generation_enabled',
                    settings.image_generation_enabled === 'true' ? 'false' : 'true'
                  )}
                >
                  {settings.image_generation_enabled === 'true' ? 'Disable' : 'Enable'}
                </button>
              </div>
            </div>
            <div className="setting-card">
              <label className="setting-label">Default Daily Limit (new users)</label>
              <div className="number-row">
                <input
                  type="number"
                  min={0}
                  max={1000}
                  defaultValue={settings.image_generation_default_daily_limit || 10}
                  id="daily-limit-input"
                  className="setting-input"
                />
                <button
                  className="btn-primary"
                  onClick={() => {
                    const val = document.getElementById('daily-limit-input').value;
                    updateGlobalSetting('image_generation_default_daily_limit', val);
                  }}
                >
                  Apply
                </button>
              </div>
            </div>
          </div>

          <h3 style={{ marginTop: '1.5rem' }}>All Application Settings</h3>
          <div className="settings-raw">
            {Object.entries(settings).map(([k, v]) => (
              <div key={k} className="setting-row">
                <span className="setting-key">{k}</span>
                <span className="setting-value">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Generations Tab */}
      {tab === 'generations' && !loading && (
        <div className="admin-section">
          <div className="section-header">
            <h3>All Generations ({allGenerations.length})</h3>
            <button className="btn-refresh" onClick={loadGenerations}>↻ Refresh</button>
          </div>
          {allGenerations.length === 0 ? (
            <p className="empty-state">No image generations yet.</p>
          ) : (
            <div className="gen-history-list">
              {allGenerations.map((rec) => (
                <div key={rec.id} className={`gen-history-item status-${rec.status}`}>
                  <div className="gen-info">
                    <span className="gen-email">{rec.user_email || rec.user_id}</span>
                    <span className="gen-prompt">{rec.prompt.slice(0, 80)}…</span>
                  </div>
                  <div className="gen-meta">
                    <span className={`status-badge ${rec.status}`}>{rec.status}</span>
                    <span>{rec.style}</span>
                    <span>{rec.aspect_ratio}</span>
                    <span>{new Date(rec.created_at).toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Audit Log Tab */}
      {tab === 'audit' && !loading && (
        <div className="admin-section">
          <div className="section-header">
            <h3>Audit Log ({auditLogs.length} entries)</h3>
            <button className="btn-refresh" onClick={loadAuditLogs}>↻ Refresh</button>
          </div>
          {auditLogs.length === 0 ? (
            <p className="empty-state">No audit events recorded yet.</p>
          ) : (
            <div className="audit-list">
              {auditLogs.map((log) => (
                <div key={log.id} className="audit-entry">
                  <div className="audit-action">
                    <span className="audit-time">{new Date(log.created_at).toLocaleString()}</span>
                    <span className="audit-actor">{log.admin_email || log.admin_id}</span>
                    <span className="audit-verb">{log.action}</span>
                  </div>
                  {log.target_user_id && (
                    <div className="audit-target">Target: {log.target_user_id}</div>
                  )}
                  {log.details && (
                    <div className="audit-details">{log.details}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
