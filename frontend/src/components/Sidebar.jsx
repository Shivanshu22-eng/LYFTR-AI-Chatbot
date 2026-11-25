import React from 'react';

export default function Sidebar({
  sessions,
  activeSession,
  onNewChat,
  onSelectSession,
  isOpen,
  onToggle,
}) {
  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
      <div className="sidebar-header">
        <div className="brand">
          <span className="brand-icon">L</span>
          <span className="brand-name">LYFTR AI</span>
        </div>
        <button className="sidebar-close" onClick={onToggle} aria-label="Close sidebar">
          ✕
        </button>
      </div>

      <button className="new-chat-btn" onClick={onNewChat}>
        <span className="plus-icon">＋</span> New Chat
      </button>

      <nav className="session-list">
        {sessions.map((s) => (
          <button
            key={s.id}
            className={`session-item ${s.id === activeSession ? 'active' : ''}`}
            onClick={() => onSelectSession(s.id)}
            title={s.title}
          >
            <span className="session-icon">💬</span>
            <span className="session-title">{s.title}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
