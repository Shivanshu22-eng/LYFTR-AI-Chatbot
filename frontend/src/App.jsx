import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import MessageInput from './components/MessageInput';
import StatusBar from './components/StatusBar';
import ErrorNotification from './components/ErrorNotification';
import { sendMessage, fetchMessages, fetchSessions, createSession, checkHealth } from './api';
import './styles/App.css';

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const healthInterval = useRef(null);

  // ---- Health polling --------------------------------------------------
  const pollHealth = useCallback(async () => {
    try {
      await checkHealth();
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => {
    pollHealth();
    healthInterval.current = setInterval(pollHealth, 15000);
    return () => clearInterval(healthInterval.current);
  }, [pollHealth]);

  // ---- Load sessions & generate new session on page load ---------------
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const existing = await fetchSessions();
        const created = await createSession();
        if (mounted) {
          setSessions([created, ...existing]);
          setActiveSession(created.id);
        }
      } catch {
        // Backend offline; will create session on first message
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // ---- Load messages when session changes --------------------------------
  useEffect(() => {
    if (!activeSession) {
      setMessages([]);
      return;
    }
    fetchMessages(activeSession)
      .then(setMessages)
      .catch((e) => setError(e.message));
  }, [activeSession]);

  // ---- New chat ---------------------------------------------------------
  const handleNewChat = async () => {
    try {
      const created = await createSession();
      setSessions((prev) => [created, ...prev]);
      setActiveSession(created.id);
      setMessages([]);
    } catch {
      setActiveSession(null);
      setMessages([]);
    }
  };

  // ---- Select session ---------------------------------------------------
  const handleSelectSession = (id) => {
    setActiveSession(id);
  };

  // ---- Send message -----------------------------------------------------
  const handleSend = async (text) => {
    if (!text.trim() || loading) return;

    const isFirstMessage = messages.length === 0;

    // Optimistically add user message
    const userMsg = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError(null);

    try {
      const data = await sendMessage(text, activeSession);
      const { session_id, reply, metadata } = data;
      const aiMsg = {
        id: `assistant-${Date.now()}`,
        session_id,
        role: 'assistant',
        content: reply,
        meta: metadata,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, aiMsg]);

      if (!activeSession) {
        setActiveSession(session_id);
      }
      if (!activeSession || isFirstMessage) {
        fetchSessions().then(setSessions).catch(() => {});
      }
    } catch (e) {
      // Remove optimistic user message since failed requests are not stored
      setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeSession={activeSession}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((v) => !v)}
      />

      <main className={`main-panel ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
        <header className="topbar">
          <button
            className="topbar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            aria-label="Toggle sidebar"
          >
            ☰
          </button>
          <h1 className="topbar-title">LYFTR AI</h1>
          <StatusBar online={backendOnline} />
        </header>

        <ChatArea messages={messages} loading={loading} />

        {error && (
          <ErrorNotification message={error} onClose={() => setError(null)} />
        )}

        <MessageInput onSend={handleSend} disabled={loading} />
      </main>
    </div>
  );
}
