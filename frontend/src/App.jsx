import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import MessageInput from './components/MessageInput';
import StatusBar from './components/StatusBar';
import ErrorNotification from './components/ErrorNotification';
import ImageAnalysisPanel from './components/ImageAnalysisPanel';
import WeatherPanel from './components/WeatherPanel';
import CropPanel from './components/CropPanel';
import HistoryPanel from './components/HistoryPanel';
import ImageGenerationPanel from './components/ImageGenerationPanel';
import AdminPanel from './components/AdminPanel';
import AuthModal from './components/AuthModal';
import {
  sendMessage,
  analyzeImage,
  fetchMessages,
  fetchSessions,
  createSession,
  checkHealth,
  getCurrentUser,
  clearAuth,
  fetchMe,
} from './api';
import './styles/App.css';

const buildTabs = (user) => {
  const tabs = [
    { id: 'chat', label: '💬 AI Chat' },
    { id: 'image', label: '🔍 Image Analysis' },
    { id: 'imagegen', label: '🎨 Image Studio' },
    { id: 'weather', label: '🌤️ Live Weather' },
    { id: 'crop', label: '🌾 Crop Guide' },
    { id: 'history', label: '📚 History' },
  ];
  if (user?.role === 'admin') {
    tabs.push({ id: 'admin', label: '🛡️ Admin' });
  }
  return tabs;
};

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [user, setUser] = useState(null);         // authenticated user
  const [showAuth, setShowAuth] = useState(false); // show auth modal
  const healthInterval = useRef(null);

  // ---- Auth init ----------------------------------------------------------
  useEffect(() => {
    const stored = getCurrentUser();
    if (stored) {
      setUser(stored);
      // Refresh profile from server
      fetchMe().then(setUser).catch(() => {});
    }
  }, []);

  // ---- Health polling -----------------------------------------------------
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

  // ---- Load sessions & generate new session on page load -----------------
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
    return () => { mounted = false; };
  }, []);

  // ---- Load messages when session changes --------------------------------
  useEffect(() => {
    if (!activeSession) { setMessages([]); return; }
    fetchMessages(activeSession)
      .then(setMessages)
      .catch(() => setMessages([]));
  }, [activeSession]);

  // ---- Handlers ----------------------------------------------------------
  const handleSend = useCallback(async (text, imageFile) => {
    if (!text.trim() && !imageFile) return;
    setLoading(true);
    setError(null);

    try {
      if (imageFile) {
        const userMsg = {
          id: `tmp-u-${Date.now()}`, role: 'user',
          content: `[Image: ${imageFile.name}] ${text || 'Analyze this image'}`,
          session_id: activeSession, created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, userMsg]);
        const result = await analyzeImage(imageFile, text, activeSession);
        const assistantMsg = {
          id: `tmp-a-${Date.now()}`, role: 'assistant',
          content: result.analysis, session_id: activeSession,
          created_at: new Date().toISOString(),
          meta: result.metadata,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else {
        const userMsg = {
          id: `tmp-u-${Date.now()}`, role: 'user',
          content: text, session_id: activeSession,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, userMsg]);
        const result = await sendMessage(text, activeSession);
        const assistantMsg = {
          id: `tmp-a-${Date.now()}`, role: 'assistant',
          content: result.reply, session_id: activeSession,
          created_at: new Date().toISOString(),
          meta: result.metadata,
        };
        setMessages((prev) => [...prev, assistantMsg]);

        // Update session title on first exchange
        if (messages.length === 0) {
          setSessions((prev) =>
            prev.map((s) =>
              s.id === activeSession
                ? { ...s, title: text.slice(0, 50) }
                : s
            )
          );
        }
      }
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }, [activeSession, messages.length]);

  const handleNewChat = useCallback(async () => {
    setActiveTab('chat');
    try {
      const created = await createSession();
      setSessions((prev) => [created, ...prev]);
      setActiveSession(created.id);
      setMessages([]);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const handleSelectSession = useCallback(async (sessionId) => {
    setActiveTab('chat');
    setActiveSession(sessionId);
  }, []);

  const handleAuth = useCallback((data) => {
    setUser({ id: data.user_id, email: data.email, role: data.role });
    setShowAuth(false);
  }, []);

  const handleLogout = useCallback(() => {
    clearAuth();
    setUser(null);
    setActiveTab('chat');
  }, []);

  const dismissError = useCallback(() => setError(null), []);

  const TOP_TABS = buildTabs(user);

  return (
    <div className="app-layout">
      {showAuth && <AuthModal onAuth={handleAuth} />}

      <Sidebar
        sessions={sessions}
        activeSession={activeSession}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        user={user}
        onShowAuth={() => setShowAuth(true)}
        onLogout={handleLogout}
      />

      <div className={`main-area ${sidebarOpen ? '' : 'sidebar-closed'}`}>
        {/* Top bar */}
        <div className="topbar">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? '◀' : '☰'}
          </button>
          <div className="topbar-tabs">
            {TOP_TABS.map((t) => (
              <button
                key={t.id}
                className={`topbar-tab ${activeTab === t.id ? 'active' : ''}`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="topbar-right">
            {user ? (
              <div className="user-menu">
                <span className={`role-pill role-${user.role}`}>{user.role}</span>
                <span className="user-email-short">{user.email}</span>
                <button className="btn-logout" onClick={handleLogout}>Sign Out</button>
              </div>
            ) : (
              <button className="btn-signin" onClick={() => setShowAuth(true)}>
                🔑 Sign In
              </button>
            )}
          </div>
        </div>

        <StatusBar online={backendOnline} />
        {error && <ErrorNotification message={error} onDismiss={dismissError} />}

        {/* Panels */}
        <div className="panel-container">
          {activeTab === 'chat' && (
            <div className="chat-wrapper">
              <ChatArea messages={messages} loading={loading} />
              <MessageInput onSend={handleSend} disabled={loading} />
            </div>
          )}
          {activeTab === 'image' && <ImageAnalysisPanel />}
          {activeTab === 'imagegen' && (
            user
              ? <ImageGenerationPanel user={user} />
              : (
                <div className="auth-required-panel">
                  <div className="auth-required-card">
                    <h2>🎨 Image Generation Studio</h2>
                    <p>Please sign in to generate AI images.</p>
                    <button className="btn-primary" onClick={() => setShowAuth(true)}>
                      🔑 Sign In to Access
                    </button>
                  </div>
                </div>
              )
          )}
          {activeTab === 'weather' && <WeatherPanel />}
          {activeTab === 'crop' && <CropPanel />}
          {activeTab === 'history' && <HistoryPanel />}
          {activeTab === 'admin' && user?.role === 'admin' && <AdminPanel user={user} />}
        </div>
      </div>
    </div>
  );
}
