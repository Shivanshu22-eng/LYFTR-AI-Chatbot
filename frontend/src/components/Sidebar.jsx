import React from 'react';

export default function Sidebar({
  sessions = [],
  activeSession,
  onSelectSession,
  onNewChat,
  isOpen,
  onClose,
  activeTab,
  onSelectTab,
  user,
  onShowAuth,
  onLogout,
}) {
  const navItems = [
    { id: 'chat', label: '💬 AI Chat' },
    { id: 'image', label: '🔍 Image Analysis' },
    { id: 'imagegen', label: '🎨 Image Studio' },
    { id: 'weather', label: '🌤️ Live Weather' },
    { id: 'crop', label: '🌾 Crop Guide' },
    { id: 'history', label: '📚 History' },
  ];
  if (user?.role === 'admin') {
    navItems.push({ id: 'admin', label: '🛡️ Admin' });
  }

  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="brand-icon">🌿</span>
          <span className="brand-name">LYFTR AI</span>
        </div>
        <button className="sidebar-close" onClick={onClose} aria-label="Close sidebar">✕</button>
      </div>

      {/* Auth section */}
      <div className="sidebar-auth">
        {user ? (
          <div className="sidebar-user">
            <div className="sidebar-user-info">
              <span className="user-avatar">👤</span>
              <div>
                <div className="sidebar-email">{user.email}</div>
                <span className={`role-badge role-${user.role}`}>{user.role}</span>
              </div>
            </div>
            <button className="btn-signout-sm" onClick={onLogout}>Sign Out</button>
          </div>
        ) : (
          <button className="btn-signin-sidebar" onClick={onShowAuth}>
            🔑 Sign In / Register
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => onSelectTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {/* Chat sessions */}
      <div className="sidebar-sessions">
        <div className="sessions-header">
          <span>Recent Chats</span>
          <button className="new-chat-btn" onClick={onNewChat}>+ New</button>
        </div>
        <ul className="sessions-list">
          {sessions.map((s) => (
            <li
              key={s.id}
              className={`session-item ${activeSession === s.id ? 'active' : ''}`}
              onClick={() => onSelectSession(s.id)}
            >
              <span className="session-title">{s.title || 'New Chat'}</span>
              <span className="session-date">
                {new Date(s.updated_at).toLocaleDateString()}
              </span>
            </li>
          ))}
          {sessions.length === 0 && (
            <li className="session-empty">No chats yet</li>
          )}
        </ul>
      </div>
    </aside>
  );
}
