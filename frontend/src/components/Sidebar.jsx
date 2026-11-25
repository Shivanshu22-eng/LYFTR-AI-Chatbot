import React from 'react';

const NAV_ITEMS = [
  { id: 'chat', label: 'AI Chat', icon: '💬' },
  { id: 'image', label: 'Image Analysis', icon: '🖼️' },
  { id: 'weather', label: 'Live Weather', icon: '🌦️' },
  { id: 'crop', label: 'Crop Recommendations', icon: '🌱' },
  { id: 'history', label: 'Chat History', icon: '🗂️' },
];

export default function Sidebar({
  sessions,
  activeSession,
  activeTab,
  onSelectTab,
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

      <nav className="sidebar-nav" aria-label="Primary sections">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            data-testid={`nav-${item.id}`}
            onClick={() => onSelectTab(item.id)}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <button className="new-chat-btn" onClick={() => { onSelectTab('chat'); onNewChat(); }}>
        <span className="plus-icon">＋</span> New Chat
      </button>

      <div className="sidebar-section-label">Recent Sessions</div>
      <nav className="session-list">
        {sessions.map((s) => (
          <button
            key={s.id}
            className={`session-item ${s.id === activeSession && activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => {
              onSelectSession(s.id);
              onSelectTab('chat');
            }}
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
