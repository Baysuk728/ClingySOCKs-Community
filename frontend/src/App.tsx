import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatInterface } from './components/ChatInterface';
import { PersonaDeck } from './components/PersonaDeck';
import { MemoryDashboard } from './components/MemoryDashboard';
import { ContextBuilder } from './components/ContextBuilder';
import { GraphVisualizer } from './components/GraphVisualizer';
import { Settings } from './components/Settings';
import { UserProfile } from './components/UserProfile';
import { LoginScreen } from './components/LoginScreen';
import { useAuth } from './components/AuthProvider';
import { Agent, ChatSession, Message, Memory, ViewMode, ApiKeyConfig } from './types';
import { getPersonas, createPersona, updatePersona, deletePersona } from './services/api';
import { chatApi } from './services/chatApi';
import { Loader2, Bot } from 'lucide-react';

// Local storage keys
const STORAGE_KEYS = {
  API_KEYS: 'clingysocks-api-keys',
  AGENTS: 'clingysocks-agents',
  SESSIONS: 'clingysocks-sessions',
  MESSAGES: 'clingysocks-messages',
  MEMORIES: 'clingysocks-memories',
  CURRENT_SESSION: 'clingysocks-current-session',
};

// Simple obfuscation for localStorage (not true encryption, but better than plaintext)
const obfuscate = (str: string): string => btoa(encodeURIComponent(str));
const deobfuscate = (str: string): string => {
  try {
    return decodeURIComponent(atob(str));
  } catch {
    return str;
  }
};

const App: React.FC = () => {
  const { user, loading: authLoading } = useAuth();

  // Global State
  const [currentView, setCurrentView] = useState<ViewMode>('chat');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyConfig[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);

  // Load all data from localStorage on mount
  useEffect(() => {
    try {
      // Load API keys
      const storedKeys = localStorage.getItem(STORAGE_KEYS.API_KEYS);
      if (storedKeys) {
        setApiKeys(JSON.parse(deobfuscate(storedKeys)));
      }

      // Agents are loaded from Memory API in a separate effect (after auth resolves)
      // Load localStorage fallback immediately for fast paint
      const storedAgents = localStorage.getItem(STORAGE_KEYS.AGENTS);
      if (storedAgents) {
        setAgents(JSON.parse(storedAgents));
      } else {
        setAgents([]);
      }


      // Load sessions locally first (as fallback/initial state)
      const storedSessions = localStorage.getItem(STORAGE_KEYS.SESSIONS);
      if (storedSessions) {
        setSessions(JSON.parse(storedSessions));
      }

      // Messages are loaded from PostgreSQL on-demand, not from localStorage
      // (eliminates unbounded localStorage growth)

      // Load memories
      const storedMemories = localStorage.getItem(STORAGE_KEYS.MEMORIES);
      if (storedMemories) {
        setMemories(JSON.parse(storedMemories));
      }

      // Load current session ID
      const storedCurrentSession = localStorage.getItem(STORAGE_KEYS.CURRENT_SESSION);
      if (storedCurrentSession) {
        setCurrentSessionId(storedCurrentSession);
      }

      setIsLoaded(true);
    } catch (e) {
      console.error('Failed to load data from localStorage:', e);
      // Fall back to empty state
      setAgents([]);
      setIsLoaded(true);
    }
  }, []);

  // Load personas from Memory API once auth resolves
  useEffect(() => {
    if (!user || authLoading) return;

    const loadPersonas = async () => {
      try {
        console.log('Loading personas from Memory API...');
        const personas = await getPersonas();

        if (personas && personas.length > 0) {
          console.log(`✅ Loaded ${personas.length} personas from Memory API`);
          setAgents(personas);
          localStorage.setItem(STORAGE_KEYS.AGENTS, JSON.stringify(personas));
        } else {
          console.log('No personas found in Memory API, keeping current agents');
        }
      } catch (error) {
        console.error('Failed to load personas from Memory API:', error);
        // Keep whatever was loaded from localStorage
      }
    };

    loadPersonas();
  }, [user, authLoading]);

  // Fetch true canonical sessions from PostgreSQL
  useEffect(() => {
    if (user?.uid) {
      chatApi.fetchConversations(user.uid).then(convos => {
        if (convos && convos.length > 0) {
          const mappedSessions: ChatSession[] = convos.map(c => ({
            id: c.id,
            name: c.title,
            participants: c.participants,
            isGroup: c.isGroup,
            lastMessageAt: c.updatedAt,
            preview: 'Loaded from history',
            harvestState: c.harvestState || 'not_harvested',
            messageCount: c.messageCount || 0,
            entityId: c.entityId,
            source: c.source,
          }));
          setSessions(mappedSessions);
        }
      }).catch(err => console.error('Failed to fetch sessions from Postgres:', err));
    }
  }, [user]);

  // Demo session was removed to avoid ghost agent references.
  // The system now waits for the user to create their first persona and start a real chat.

  // Save API keys to localStorage when changed
  useEffect(() => {
    if (isLoaded && apiKeys.length >= 0) {
      localStorage.setItem(STORAGE_KEYS.API_KEYS, obfuscate(JSON.stringify(apiKeys)));
    }
  }, [apiKeys, isLoaded]);

  // Save agents to localStorage when changed
  useEffect(() => {
    if (isLoaded && agents.length > 0) {
      localStorage.setItem(STORAGE_KEYS.AGENTS, JSON.stringify(agents));
    }
  }, [agents, isLoaded]);

  // Sessions and messages are NOT persisted to localStorage
  // PostgreSQL is the canonical source of truth for both

  // Save memories to localStorage when changed
  useEffect(() => {
    if (isLoaded && memories.length >= 0) {
      localStorage.setItem(STORAGE_KEYS.MEMORIES, JSON.stringify(memories));
    }
  }, [memories, isLoaded]);

  // Save current session ID to localStorage when changed
  useEffect(() => {
    if (isLoaded && currentSessionId) {
      localStorage.setItem(STORAGE_KEYS.CURRENT_SESSION, currentSessionId);
    }
  }, [currentSessionId, isLoaded]);

  // API Key Handlers
  const handleAddApiKey = (key: ApiKeyConfig) => {
    // If this key is set as default, unset other defaults for same provider
    let updatedKeys = apiKeys;
    if (key.isDefault) {
      updatedKeys = apiKeys.map(k =>
        k.provider === key.provider ? { ...k, isDefault: false } : k
      );
    }
    setApiKeys([...updatedKeys, key]);
  };

  const handleUpdateApiKey = (key: ApiKeyConfig) => {
    let updatedKeys = apiKeys.map(k => k.id === key.id ? key : k);
    // If this key is set as default, unset other defaults for same provider
    if (key.isDefault) {
      updatedKeys = updatedKeys.map(k =>
        k.id !== key.id && k.provider === key.provider ? { ...k, isDefault: false } : k
      );
    }
    setApiKeys(updatedKeys);
  };

  const handleDeleteApiKey = (id: string) => {
    setApiKeys(apiKeys.filter(k => k.id !== id));
  };

  // Message Handlers
  const handleSendMessage = async (sessionId: string, content: string) => {
    const newMsg: Message = {
      id: `msg-${Date.now()}`,
      chatId: sessionId,
      senderId: 'user',
      content,
      timestamp: Date.now()
    };
    setMessages(prev => [...prev, newMsg]);

    // Update session preview
    setSessions(prev => prev.map(s =>
      s.id === sessionId ? { ...s, lastMessageAt: Date.now(), preview: content } : s
    ));
  };

  const handleReceiveMessage = async (msg: Message) => {
    setMessages(prev => [...prev, msg]);
    setSessions(prev => prev.map(s =>
      s.id === msg.chatId ? { ...s, lastMessageAt: Date.now(), preview: msg.content } : s
    ));
  };

  const handleCreateSession = async (name: string, participants: string[], isGroup: boolean) => {
    try {
      // The first participant is the agent entity — create conversation in PostgreSQL
      const entityId = participants[0];
      const result = await chatApi.createConversation(entityId, name);
      console.log(`✅ Created conversation in PostgreSQL: ${result.id}`);

      const newSession: ChatSession = {
        id: result.id,        // Use server-generated UUID
        name: result.title,
        participants,
        isGroup,
        lastMessageAt: Date.now(),
        preview: 'Session initialized.'
      };
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      setCurrentView('chat');
    } catch (error) {
      console.error('Failed to create conversation:', error);
      // Fallback: create locally so user isn't stuck
      const localId = `session-${Date.now()}`;
      const fallbackSession: ChatSession = {
        id: localId,
        name,
        participants,
        isGroup,
        lastMessageAt: Date.now(),
        preview: 'Session initialized (offline).'
      };
      setSessions(prev => [fallbackSession, ...prev]);
      setCurrentSessionId(fallbackSession.id);
      setCurrentView('chat');
    }
  };

  const handleDeleteSession = async (id: string) => {
    // Optimistic UI: remove immediately
    setSessions(prev => prev.filter(s => s.id !== id));
    setMessages(prev => prev.filter(m => m.chatId !== id));
    if (currentSessionId === id) setCurrentSessionId(null);

    // Delete from PostgreSQL
    try {
      await chatApi.deleteConversation(id);
      console.log(`✅ Deleted conversation from PostgreSQL: ${id}`);
    } catch (error) {
      console.error('Failed to delete conversation from PostgreSQL:', error);
      // Session is already removed from UI; backend cleanup can be retried
    }
  };

  // Handler for loading a stored conversation into the chat
  const handleLoadConversation = (
    sessionId: string,
    title: string,
    participants: string[],
    isGroup: boolean,
    loadedMessages: Message[]
  ) => {
    // Create new session
    const newSession: ChatSession = {
      id: sessionId,
      name: title,
      participants,
      isGroup,
      lastMessageAt: Date.now(),
      preview: loadedMessages[loadedMessages.length - 1]?.content || 'Loaded from history'
    };

    // Add session (check for duplicates)
    setSessions(prev => {
      if (prev.some(s => s.id === sessionId)) {
        return prev; // Already exists
      }
      return [newSession, ...prev];
    });

    // Add messages (merge, don't duplicate)
    setMessages(prev => {
      const existingMsgIds = new Set(prev.filter(m => m.chatId === sessionId).map(m => m.id));
      const newMsgs = loadedMessages.filter(m => !existingMsgIds.has(m.id));
      return [...prev, ...newMsgs];
    });

    // Select this session
    setCurrentSessionId(sessionId);
    console.log(`✅ Loaded ${loadedMessages.length} messages from "${title}"`);
  };

  // Refresh sessions from PostgreSQL (called after imports, etc.)
  const refreshSessions = async () => {
    if (!user?.uid) return;
    try {
      const convos = await chatApi.fetchConversations(user.uid);
      if (convos && convos.length > 0) {
        const mappedSessions: ChatSession[] = convos.map(c => ({
          id: c.id,
          name: c.title,
          participants: c.participants,
          isGroup: c.isGroup,
          lastMessageAt: c.updatedAt,
          preview: 'Loaded from history',
          harvestState: c.harvestState || 'not_harvested',
          messageCount: c.messageCount || 0,
          entityId: c.entityId,
          source: c.source,
        }));
        setSessions(mappedSessions);
      }
    } catch (err) {
      console.error('Failed to refresh sessions:', err);
    }
  };

  // Render View
  const renderView = () => {
    switch (currentView) {
      case 'chat':
        if (agents.length === 0) {
          return (
            <div className="flex-1 flex items-center justify-center bg-nexus-900 p-8 text-center">
              <div className="max-w-md animate-in fade-in slide-in-from-bottom-4 duration-1000">
                <div className="w-24 h-24 bg-nexus-accent/10 rounded-full flex items-center justify-center mx-auto mb-6 shadow-[0_0_30px_rgba(0,242,255,0.2)]">
                  <Bot className="w-12 h-12 text-nexus-accent" />
                </div>
                <h2 className="text-3xl font-bold text-white mb-4">Welcome to ClingySOCKs</h2>
                <p className="text-gray-400 mb-8 leading-relaxed">
                  Your Relational Memory Engine is ready, but you don't have any agents yet. 
                  Create your first persona to start chatting and building your knowledge graph.
                </p>
                <button
                  onClick={() => setCurrentView('personas')}
                  className="bg-nexus-accent text-nexus-900 px-8 py-3 rounded-xl font-bold hover:scale-105 active:scale-95 transition-all shadow-[0_0_20px_rgba(0,242,255,0.3)]"
                >
                  Create Your First Agent
                </button>
              </div>
            </div>
          );
        }
        return (
          <ChatInterface
            sessions={sessions}
            currentSessionId={currentSessionId}
            agents={agents}
            messages={messages}
            memories={memories}
            apiKeys={apiKeys}
            onSendMessage={handleSendMessage}
            onCreateSession={handleCreateSession}
            onReceiveMessage={handleReceiveMessage}
            onSelectSession={setCurrentSessionId}
            onDeleteSession={handleDeleteSession}
            onRefreshSessions={refreshSessions}
            onLoadConversation={handleLoadConversation}
          />
        );
      case 'personas':
        return (
          <PersonaDeck
            agents={agents}
            apiKeys={apiKeys}
            onAddAgent={async (a) => {
              try {
                const newPersona = await createPersona(a);
                const updatedAgents = [...agents, newPersona];
                setAgents(updatedAgents);
                localStorage.setItem(STORAGE_KEYS.AGENTS, JSON.stringify(updatedAgents));
              } catch (error) {
                console.error('Failed to create persona:', error);
                alert('Failed to create agent. Please try again.');
              }
            }}
            onUpdateAgent={async (a) => {
              try {
                const updatedPersona = await updatePersona(a);
                const updatedAgents = agents.map(ag => ag.id === a.id ? updatedPersona : ag);
                setAgents(updatedAgents);
                localStorage.setItem(STORAGE_KEYS.AGENTS, JSON.stringify(updatedAgents));
              } catch (error) {
                console.error('Failed to update persona:', error);
                alert('Failed to update agent. Please try again.');
              }
            }}
            onDeleteAgent={async (id) => {
              try {
                await deletePersona(id);
                const updatedAgents = agents.filter(a => a.id !== id);
                setAgents(updatedAgents);
                localStorage.setItem(STORAGE_KEYS.AGENTS, JSON.stringify(updatedAgents));
              } catch (error) {
                console.error('Failed to delete persona:', error);
                alert('Failed to delete agent. Please try again.');
              }
            }}
          />
        );
      case 'memory':
        return (
          <MemoryDashboard
            agents={agents}
            currentUserId={user?.uid}
          />
        );
      case 'context':
        return (
          <ContextBuilder agents={agents} />
        );
      case 'graph':
        return (
          <GraphVisualizer agents={agents} />
        );      case 'settings':
        return (
          <Settings />
        );
      case 'profile':
        return (
          <UserProfile />
        );
      default:
        return null;
    }
  };

  // Show loading spinner while checking auth
  if (authLoading) {
    return (
      <div className="min-h-screen bg-nexus-900 flex items-center justify-center">
        <Loader2 className="w-12 h-12 text-nexus-accent animate-spin" />
      </div>
    );
  }

  // Show login screen if not authenticated
  if (!user) {
    return <LoginScreen />;
  }

  // Main app (authenticated)
  return (
    <div className="flex h-screen w-full bg-nexus-900 text-gray-200 font-sans overflow-hidden">
      <Sidebar currentView={currentView} onViewChange={setCurrentView} />
      <main className="flex-1 relative overflow-hidden">
        {/* Background Ambient Effects */}
        <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
          <div className="absolute top-[-10%] right-[-10%] w-[500px] h-[500px] bg-nexus-accent/5 rounded-full blur-[120px]"></div>
          <div className="absolute bottom-[-10%] left-[-10%] w-[500px] h-[500px] bg-purple-900/10 rounded-full blur-[120px]"></div>
        </div>

        <div className="relative z-10 h-full pb-20 md:pb-0">
          {renderView()}
        </div>
      </main>
    </div>
  );
};

export default App;
