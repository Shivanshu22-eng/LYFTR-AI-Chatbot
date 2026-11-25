import React, { useEffect } from 'react';

export default function ErrorNotification({ message, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 8000);
    return () => clearTimeout(timer);
  }, [message, onClose]);

  return (
    <div className="error-notification" role="alert">
      <span className="error-icon">⚠️</span>
      <span className="error-text">{message}</span>
      <button className="error-close" onClick={onClose} aria-label="Dismiss error">
        ✕
      </button>
    </div>
  );
}
