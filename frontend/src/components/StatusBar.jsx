import React from 'react';

export default function StatusBar({ online }) {
  return (
    <div className={`status-bar ${online ? 'online' : 'offline'}`}>
      <span className="status-dot" />
      <span className="status-text">{online ? 'Connected' : 'Offline'}</span>
    </div>
  );
}
