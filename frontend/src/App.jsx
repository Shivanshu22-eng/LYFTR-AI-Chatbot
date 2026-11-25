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
import {
  sendMessage,
  analyzeImage,
  fetchMessages,
  fetchSessions,
  createSession,
  checkHealth,
} from './api';
import './styles/App.css';

const TOP_TABS = [
  { id: 'chat', label: 'AI Chat' },
  { id: 'image', label: 'Image Analysis' },
  { id: 'weather', label: 'Live Weather' },
  { id: 'crop', label: 'Crop Recommendations' },
  { id: 'history', label: 'Chat History' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
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

  // ---- Send message (text or image + text) ------------------------------
  const handleSend = async (text, imageFile = null) => {
    if ((!text.trim() && !imageFile) || loading) return;

    const isFirstMessage = messages.length === 0;
    const displayContent = imageFile
      ? `[Image: ${imageFile.name}] ${text || 'Analyze attached image'}`
      : text;

    const userMsg = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: displayContent,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError(null);

    try {
      let targetSessionId = activeSession;
      if (imageFile && !targetSessionId) {
        const created = await createSession();
        targetSessionId = created.id;
        setActiveSession(created.id);
      }

      if (imageFile) {
        const data = await analyzeImage(imageFile, text, targetSessionId);
        const aiMsg = {
          id: `assistant-${Date.now()}`,
          session_id: targetSessionId,
          role: 'assistant',
          content: data.analysis,
          meta: data.metadata,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, aiMsg]);
        fetchSessions().then(setSessions).catch(() => {});
      } else {
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
      }
    } catch (e) {
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
        activeTab={activeTab}
        onSelectTab={setActiveTab}
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
          <div className="topbar-tabs" role="tablist" aria-label="Workspace sections">
            {TOP_TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={activeTab === t.id}
                className={`topbar-tab ${activeTab === t.id ? 'active' : ''}`}
                data-testid={`tab-${t.id}`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <StatusBar online={backendOnline} />
        </header>

        {error && (
          <ErrorNotification message={error} onClose={() => setError(null)} />
        )}

        {activeTab === 'chat' && (
          <>
            <ChatArea messages={messages} loading={loading} />
            <MessageInput
              onSend={handleSend}
              disabled={loading}
              onError={(msg) => setError(msg)}
            />
          </>
        )}

        {activeTab === 'image' && (
          <ImageAnalysisPanel
            activeSession={activeSession}
            onError={(msg) => setError(msg)}
          />
        )}

        {activeTab === 'weather' && (
          <WeatherPanel
            activeSession={activeSession}
            onError={(msg) => setError(msg)}
          />
        )}

        {activeTab === 'crop' && (
          <CropPanel
            activeSession={activeSession}
            onError={(msg) => setError(msg)}
          />
        )}

        {activeTab === 'history' && (
          <HistoryPanel
            sessions={sessions}
            activeSession={activeSession}
            onSelectSession={handleSelectSession}
            onOpenChat={() => setActiveTab('chat')}
            onError={(msg) => setError(msg)}
          />
        )}
      </main>
    </div>
  );
}
