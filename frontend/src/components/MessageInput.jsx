import React, { useState, useRef, useEffect } from 'react';
import { validateImageFile } from './ImageAnalysisPanel';

export default function MessageInput({ onSend, disabled, onError }) {
  const [text, setText] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  }, [text]);

  const handleAttach = (file) => {
    if (!file) return;
    const err = validateImageFile(file);
    if (err) {
      onError?.(err);
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setAttachedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const handleRemoveImage = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setAttachedFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if ((!text.trim() && !attachedFile) || disabled) return;
    onSend(text.trim(), attachedFile);
    setText('');
    handleRemoveImage();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div
      className={`input-wrapper ${dragOver ? 'drag-over' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleAttach(e.dataTransfer.files?.[0]);
      }}
    >
      {previewUrl && (
        <div className="chat-attachment-preview" data-testid="chat-image-preview">
          <img src={previewUrl} alt="Attachment preview" />
          <div className="chat-attachment-meta">
            <span>{attachedFile?.name}</span>
            <button
              type="button"
              className="attachment-remove-btn"
              onClick={handleRemoveImage}
              aria-label="Remove attached image"
            >
              ✕ Remove
            </button>
          </div>
        </div>
      )}

      <form className="input-area" onSubmit={handleSubmit}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
          hidden
          data-testid="chat-file-input"
          onChange={(e) => handleAttach(e.target.files?.[0])}
        />
        <button
          type="button"
          className="attach-btn"
          data-testid="attach-image-button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title="Attach image (JPG, JPEG, PNG, WEBP)"
          aria-label="Attach image"
        >
          📎
        </button>

        <textarea
          ref={textareaRef}
          data-testid="chat-input"
          className="chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={attachedFile ? 'Ask about this image (optional)…' : 'Type your message or drop an image…'}
          rows={1}
          disabled={disabled}
          aria-label="Chat message input"
        />
        <button
          data-testid="send-button"
          className="send-btn"
          type="submit"
          disabled={disabled || (!text.trim() && !attachedFile)}
          aria-label="Send message"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </form>
    </div>
  );
}
