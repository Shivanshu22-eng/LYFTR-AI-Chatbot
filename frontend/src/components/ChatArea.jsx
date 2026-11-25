import React, { useEffect, useRef } from 'react';

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  const meta = msg.metadata || msg.meta;
  const resolutionSource = meta?.resolution_source;

  return (
    <div
      className={`message ${isUser ? 'message-user' : 'message-assistant'}`}
      data-testid={isUser ? undefined : 'assistant-message'}
    >
      <div className="message-avatar">{isUser ? '👤' : '🤖'}</div>
      <div className="message-body">
        <div className="message-content">{msg.content}</div>
        {meta && (
          <div className="message-meta">
            {resolutionSource && (
              <span
                className={`meta-tag ${resolutionSource === 'LLM_CACHE' ? 'meta-cache' : resolutionSource === 'LIVE_INFERENCE' ? 'meta-live' : ''}`}
                data-testid="meta-source"
              >
                {resolutionSource === 'LLM_CACHE' ? '⚡ Cache' : resolutionSource === 'LIVE_INFERENCE' ? '🔴 Live' : resolutionSource}
              </span>
            )}
            {meta.model && (
              <span className="meta-tag" data-testid="meta-model">
                🧠 {meta.model}
              </span>
            )}
            {meta.latency_ms != null && (
              <span className="meta-tag" data-testid="meta-latency">
                ⏱ {meta.latency_ms}ms
              </span>
            )}
            {meta.input_tokens != null && (
              <span className="meta-tag" data-testid="meta-input-tokens">
                📥 {meta.input_tokens}
              </span>
            )}
            {meta.output_tokens != null && (
              <span className="meta-tag" data-testid="meta-output-tokens">
                📤 {meta.output_tokens}
              </span>
            )}
            {meta.key_id && (
              <span className="meta-tag meta-key" data-testid="meta-key-id">
                🔑 {meta.key_id}
              </span>
            )}
            {meta.fallback_attempts != null && meta.fallback_attempts > 0 && (
              <span className="meta-tag meta-fallback" data-testid="meta-fallback">
                🔄 {meta.fallback_attempts} fallback{meta.fallback_attempts > 1 ? 's' : ''}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="message message-assistant">
      <div className="message-avatar">🤖</div>
      <div className="message-body">
        <div className="typing-indicator">
          <span className="dot"></span>
          <span className="dot"></span>
          <span className="dot"></span>
        </div>
      </div>
    </div>
  );
}

export default function ChatArea({ messages, loading }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  return (
    <div className="chat-area">
      {messages.length === 0 && !loading && (
        <div className="empty-state">
          <div className="empty-icon">💡</div>
          <h2>Welcome to LYFTR AI</h2>
          <p>Start a conversation by typing a message below.</p>
        </div>
      )}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} msg={msg} />
      ))}

      {loading && <TypingIndicator />}

      <div ref={endRef} />
    </div>
  );
}
