import React, { useState, useEffect, useRef, useMemo, useCallback, memo } from 'react';
import { Agent, ChatSession, Message, Memory, ApiKeyConfig } from '../types';
import { Send, Plus, MoreVertical, Bot, User, Trash2, Cpu, Mic, Brain, History, ChevronDown, ChevronRight, Search, Archive, Menu, X, Download, Volume2, PanelLeftClose, PanelLeftOpen, Upload, BarChart3, Copy, Check, Square, Pause, Play, Paperclip } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { generateSpeech } from '../services/api'; // kept for TTS
import { chatApi, ChatMessage as ApiChatMessage } from '../services/chatApi'; // New Chat API
import { ChatImportModal } from './ChatImportModal';
import { HarvestStatusIcon, HarvestState } from './HarvestStatusIcon';
import { VoiceMode } from './VoiceMode';

import { useAuth } from './AuthProvider';

const API_URL = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

interface ToolMediaAttachment {
    kind: 'image' | 'audio';
    relativePath: string;
    name: string;
}

function normalizeAgentRelativePath(pathValue: string): string | null {
    if (!pathValue) return null;
    const normalized = pathValue.replace(/\\/g, '/');
    const marker = 'data/agent/';
    const markerIndex = normalized.toLowerCase().indexOf(marker);
    if (markerIndex >= 0) {
        return normalized.slice(markerIndex + marker.length).replace(/^\/+/, '');
    }
    return normalized.replace(/^\/+/, '');
}

function parseMediaAttachmentFromToolResult(toolName?: string, rawResult?: string): ToolMediaAttachment | null {
    if (!rawResult) return null;

    let parsed: any;
    try {
        parsed = typeof rawResult === 'string' ? JSON.parse(rawResult) : rawResult;
    } catch {
        return null;
    }

    if (!parsed?.success || !parsed?.file_path) return null;

    const relativePath = normalizeAgentRelativePath(String(parsed.file_path));
    if (!relativePath) return null;

    const name = relativePath.split('/').pop() || relativePath;
    const ext = name.split('.').pop()?.toLowerCase() || '';
    const contentType = String(parsed.content_type || '').toLowerCase();
    const lowerToolName = String(toolName || '').toLowerCase();

    const isImage = lowerToolName.includes('generate_image') || contentType.startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext);
    const isAudio = lowerToolName.includes('generate_audio') || contentType.startsWith('audio/') || ['wav', 'mp3', 'ogg', 'm4a'].includes(ext);

    if (!isImage && !isAudio) return null;

    return {
        kind: isImage ? 'image' : 'audio',
        relativePath,
        name,
    };
}

const MediaAttachmentPreview = ({ attachment }: { attachment: ToolMediaAttachment }) => {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);

    useEffect(() => {
        const ctrl = new AbortController();
        let localBlobUrl: string | null = null;

        const loadMedia = async () => {
            try {
                const headers: Record<string, string> = API_KEY ? { 'X-API-Key': API_KEY } : {};
                const res = await fetch(
                    `${API_URL}/files/download?path=${encodeURIComponent(attachment.relativePath)}`,
                    { headers, signal: ctrl.signal }
                );
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }
                const blob = await res.blob();
                localBlobUrl = URL.createObjectURL(blob);
                setBlobUrl(localBlobUrl);
                setLoadError(null);
            } catch (err: any) {
                if (err?.name !== 'AbortError') {
                    setLoadError(err?.message || 'Failed to load media');
                }
            }
        };

        loadMedia();

        return () => {
            ctrl.abort();
            if (localBlobUrl) {
                URL.revokeObjectURL(localBlobUrl);
            }
        };
    }, [attachment.kind, attachment.relativePath]);

    return (
        <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-2">
            <div className="text-xs text-gray-400 mb-2 truncate">{attachment.name}</div>
            {loadError && <div className="text-xs text-red-400">Failed to load: {loadError}</div>}
            {!loadError && !blobUrl && <div className="text-xs text-gray-500">Loading media...</div>}
            {blobUrl && attachment.kind === 'image' && (
                <img src={blobUrl} alt={attachment.name} className="max-h-80 w-auto rounded-lg" />
            )}
            {blobUrl && attachment.kind === 'audio' && (
                <audio controls src={blobUrl} className="w-full" preload="metadata" />
            )}
        </div>
    );
};

interface ChatInterfaceProps {
    sessions: ChatSession[];
    currentSessionId: string | null;
    agents: Agent[];
    messages: Message[];
    memories: Memory[];
    apiKeys?: ApiKeyConfig[]; // Optional - keys handled server-side via vault
    onSendMessage: (sessionId: string, content: string) => void;
    onCreateSession: (name: string, participants: string[], isGroup: boolean) => void;
    onReceiveMessage: (msg: Message) => void;
    onSelectSession: (id: string) => void;
    onDeleteSession: (id: string) => void;
    onRefreshSessions?: () => void;
    onLoadConversation?: (sessionId: string, title: string, participants: string[], isGroup: boolean, messages: Message[]) => void;
}

// Memoized message bubble component to prevent ReactMarkdown re-rendering on input changes
interface MessageBubbleProps {
    msg: Message;
    isUser: boolean;
    agent?: Agent;
    onSpeak?: (text: string, voiceId: string, ttsProvider: 'google' | 'openai' | 'elevenlabs' | 'local') => void;
    onStopSpeaking?: () => void;
    isSpeaking?: boolean;
    isPaused?: boolean;
    isLoadingAudio?: boolean;
}

const MessageBubble = memo(({ msg, isUser, agent, onSpeak, onStopSpeaking, isSpeaking, isPaused, isLoadingAudio }: MessageBubbleProps) => {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(msg.content);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = msg.content;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    return (
        <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} w-full group/msg`}>
            <div className={`flex flex-col max-w-[90%] sm:max-w-[85%] md:max-w-[85%] min-w-0 ${isUser ? 'items-end' : 'items-start'}`}>
                {/* Avatar + Name row */}
                <div className={`flex items-center gap-2 mb-1 flex-wrap ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center border shrink-0 ${isUser ? 'bg-nexus-accent/20 border-nexus-accent' : 'bg-gray-800 border-gray-700'}`}>
                        {isUser ? <User className="w-3 h-3 text-nexus-accent" /> : <img src={agent?.avatar} className="w-full h-full rounded-full object-cover" />}
                    </div>
                    <span className="text-xs font-bold text-gray-400">{isUser ? 'You' : agent?.name}</span>
                    <span className="text-[10px] text-gray-600">{new Date(msg.timestamp).toLocaleTimeString()}</span>
                    {/* TTS Speaker Button - Only show for agent messages with voiceId */}
                    {!isUser && agent?.voiceId && onSpeak && (
                        <button
                            onClick={() => isSpeaking ? onStopSpeaking?.() : onSpeak(msg.content, agent.voiceId!, agent.ttsProvider || 'google')}
                            disabled={isLoadingAudio}
                            className={`p-1 rounded-lg transition-colors ${isSpeaking
                                ? 'text-amber-400 bg-amber-400/20 hover:bg-amber-400/30'
                                : isPaused
                                    ? 'text-nexus-accent bg-nexus-accent/20 hover:bg-nexus-accent/30'
                                    : 'text-gray-500 hover:text-white hover:bg-white/10'
                                } ${isLoadingAudio ? 'animate-pulse' : ''}`}
                            title={isSpeaking ? 'Pause' : isPaused ? 'Resume' : 'Read aloud'}
                        >
                            {isSpeaking ? <Pause className="w-3.5 h-3.5" /> : isPaused ? <Play className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                        </button>
                    )}
                </div>
                {/* Message bubble */}
                <div className={`relative p-3 rounded-2xl backdrop-blur-sm border break-words overflow-hidden min-w-0 ${isUser
                    ? 'bg-nexus-accent/10 border-nexus-accent/20 text-gray-100'
                    : 'bg-white/5 border-white/10 text-gray-200'
                    }`}>
                    {/* Copy button - appears on hover */}
                    <button
                        onClick={handleCopy}
                        className="absolute top-1.5 right-1.5 p-1 rounded-md bg-black/40 border border-white/10 text-gray-400 hover:text-white hover:bg-black/60 transition-all opacity-0 group-hover/msg:opacity-100 z-10"
                        title={copied ? 'Copied!' : 'Copy message'}
                    >
                        {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                    </button>
                    {/* User image attachments preview */}
                    {msg.imageDataUrls && msg.imageDataUrls.length > 0 && (
                        <div className="flex flex-wrap gap-2 mb-2">
                            {msg.imageDataUrls.map((url, i) => (
                                <img key={i} src={url} alt={`Attached ${i + 1}`} className="max-h-48 rounded-lg border border-white/10" />
                            ))}
                        </div>
                    )}
                    <div className="prose prose-invert prose-sm max-w-none break-words [overflow-wrap:anywhere] [word-break:break-word] overflow-x-auto">
                        <ReactMarkdown>
                            {msg.content}
                        </ReactMarkdown>
                    </div>
                    {msg.mediaAttachments?.map((attachment) => (
                        <MediaAttachmentPreview
                            key={`${attachment.kind}:${attachment.relativePath}`}
                            attachment={attachment}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
});

MessageBubble.displayName = 'MessageBubble';

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
    sessions,
    currentSessionId,
    agents,
    messages,
    memories,
    apiKeys = [], // Default to empty array
    onSendMessage,
    onCreateSession,
    onReceiveMessage,
    onSelectSession,
    onDeleteSession,
    onRefreshSessions,
    onLoadConversation
}) => {
    const { user } = useAuth();
    const [input, setInput] = useState('');
    const [isNewChatModalOpen, setIsNewChatModalOpen] = useState(false);
    const [isImportModalOpen, setIsImportModalOpen] = useState(false);
    const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
    const [newChatName, setNewChatName] = useState('');
    const [isProcessing, setIsProcessing] = useState(false);

    // Streaming state
    const [streamingContent, setStreamingContent] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [streamThinking, setStreamThinking] = useState('');
    const [currentStreamingAgentId, setCurrentStreamingAgentId] = useState<string | null>(null);

    // Token/budget display state
    const [showTokenInfo, setShowTokenInfo] = useState(false);
    const [lastContextMeta, setLastContextMeta] = useState<any>(null);
    const [lastUsageInfo, setLastUsageInfo] = useState<any>(null);
    const [lastCacheInfo, setLastCacheInfo] = useState<any>(null);

    const [searchQuery, setSearchQuery] = useState('');
    const [localMessages, setLocalMessages] = useState<Message[]>([]);
    const [showMobileSidebar, setShowMobileSidebar] = useState(false);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

    // TTS State
    const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);
    const [loadingAudioId, setLoadingAudioId] = useState<string | null>(null);
    const [pausedMessageId, setPausedMessageId] = useState<string | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    // Abort controller for stopping streaming
    const abortControllerRef = useRef<AbortController | null>(null);

    // Voice mode state
    const [showVoiceMode, setShowVoiceMode] = useState(false);

    // File/image attachment state
    const [pendingFiles, setPendingFiles] = useState<File[]>([]);
    const [pendingPreviews, setPendingPreviews] = useState<string[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const messagesContainerRef = useRef<HTMLDivElement>(null);
    const isNearBottomRef = useRef(true);
    const userJustSentRef = useRef(false);
    const [loadingOlder, setLoadingOlder] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const hasMoreRef = useRef(true);
    const offsetRef = useRef(0);
    const PAGE_SIZE = 50;
    const currentSession = useMemo(() => sessions.find(s => s.id === currentSessionId), [sessions, currentSessionId]);
    const sessionMessages = useMemo(() => messages.filter(m => m.chatId === currentSessionId), [messages, currentSessionId]);

    // Track whether user is scrolled near the bottom
    const handleMessagesScroll = useCallback(() => {
        const el = messagesContainerRef.current;
        if (!el) return;
        const threshold = 150; // px from bottom
        isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;

        // Load older messages when scrolled to the top
        if (el.scrollTop < 80 && hasMoreRef.current && !loadingOlder && currentSessionId) {
            setLoadingOlder(true);
            const prevHeight = el.scrollHeight;
            chatApi.fetchHistory(currentSessionId, PAGE_SIZE, offsetRef.current).then(({ messages: older }) => {
                if (older.length > 0) {
                    const olderMsgs: Message[] = older.map((m: any) => ({
                        id: m.id || Math.random().toString(),
                        chatId: m.chatId || currentSessionId,
                        senderId: m.senderId,
                        content: m.content,
                        timestamp: m.timestamp,
                    }));
                    // Prepend older messages, dedup by id
                    setLocalMessages(prev => {
                        const existingIds = new Set(prev.map(m => m.id));
                        const newOlder = olderMsgs.filter(m => !existingIds.has(m.id));
                        return [...newOlder, ...prev];
                    });
                    offsetRef.current += older.length;
                    // Restore scroll position after prepend
                    requestAnimationFrame(() => {
                        if (el) el.scrollTop = el.scrollHeight - prevHeight;
                    });
                }
                if (older.length < PAGE_SIZE) {
                    hasMoreRef.current = false;
                    setHasMore(false);
                }
                setLoadingOlder(false);
            }).catch(() => setLoadingOlder(false));
        }
    }, [loadingOlder, currentSessionId]);

    // Auto-scroll only when near bottom or user just sent a message
    useEffect(() => {
        if (!isNearBottomRef.current && !userJustSentRef.current) return;
        userJustSentRef.current = false;
        const timer = setTimeout(() => {
            const container = messagesContainerRef.current;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }, 150);
        return () => clearTimeout(timer);
    }, [sessionMessages, localMessages, isProcessing]);

    // Always scroll to bottom when switching conversations
    useEffect(() => {
        isNearBottomRef.current = true;
        hasMoreRef.current = true;
        setHasMore(true);
        offsetRef.current = 0;
    }, [currentSessionId]);

    // Fetch initial messages from PostgreSQL
    useEffect(() => {
        if (!currentSessionId) {
            setLocalMessages([]);
            return;
        }

        let mounted = true;
        hasMoreRef.current = true;
        setHasMore(true);
        offsetRef.current = 0;
        chatApi.fetchHistory(currentSessionId, PAGE_SIZE, 0).then(({ messages: history, total }) => {
            if (mounted) {
                setLocalMessages(history.map((m: any) => ({
                    id: m.id || Math.random().toString(),
                    chatId: m.chatId || currentSessionId,
                    senderId: m.senderId,
                    content: m.content,
                    timestamp: m.timestamp
                })));
                offsetRef.current = history.length;
                const more = history.length < total;
                hasMoreRef.current = more;
                setHasMore(more);
                // Scroll to bottom after initial load
                setTimeout(() => {
                    const container = messagesContainerRef.current;
                    if (container) container.scrollTop = container.scrollHeight;
                }, 100);
            }
        });

        return () => {
            mounted = false;
        };
    }, [currentSessionId]);

    // WebSocket connection for real-time agent push messages
    useEffect(() => {
        if (!currentSession) return;

        const participants = currentSession.participants || [];
        const agentIds = agents.filter(a => participants.includes(a.id)).map(a => a.id);
        if (agentIds.length === 0) return;

        const MEMORY_API = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
        const wsUrl = MEMORY_API.replace('http', 'ws');
        const sockets: WebSocket[] = [];

        for (const entityId of agentIds) {
            const ws = new WebSocket(`${wsUrl}/ws/${entityId}`);

            ws.onopen = () => {
                console.log(`🔌 WebSocket connected for entity ${entityId}`);
                // Keepalive ping every 30s
                const pingInterval = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) ws.send('ping');
                }, 30000);
                (ws as any)._pingInterval = pingInterval;
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'agent_push') {
                        console.log(`📡 Push message received from ${entityId}:`, data.content?.slice(0, 80));
                        const pushMsg: Message = {
                            id: data.message_id || Math.random().toString(),
                            chatId: currentSessionId!,
                            senderId: entityId,
                            content: data.content,
                            timestamp: Date.now(),
                        };
                        setLocalMessages(prev => [...prev, pushMsg]);
                        onReceiveMessage(pushMsg);
                    }
                } catch (e) {
                    // pong or non-JSON response
                }
            };

            ws.onclose = () => {
                console.log(`🔌 WebSocket disconnected for entity ${entityId}`);
                if ((ws as any)._pingInterval) clearInterval((ws as any)._pingInterval);
            };

            sockets.push(ws);
        }

        return () => {
            sockets.forEach(ws => {
                if ((ws as any)._pingInterval) clearInterval((ws as any)._pingInterval);
                ws.close();
            });
        };
    }, [currentSession?.id, agents]);

    // Filter conversations by search query (memoized to avoid recalculating on input)
    const filteredConversations = useMemo(() =>
        searchQuery
            ? sessions.filter(c =>
                c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                c.participants.some((p: string) => p.toLowerCase().includes(searchQuery.toLowerCase()))
            )
            : sessions,
        [sessions, searchQuery]
    );

    // Get messages from local state
    const currentMessages: Message[] = useMemo(() => localMessages, [localMessages]);

    // Handler to select a conversation (now just sets the ID - subscription handles the rest)
    const handleSelectConversation = (convId: string) => {
        onSelectSession(convId);
        setShowMobileSidebar(false); // Close mobile sidebar
    };

    // TTS Handler - Generate speech and play audio (all providers via /voice/synthesize)
    const handleSpeak = useCallback(async (text: string, voiceId: string, ttsProvider: 'google' | 'openai' | 'elevenlabs' | 'local') => {
        // Find the message ID for loading state (using content as key since we don't have ID in callback)
        const targetMsg = currentMessages.find(m => m.content === text);
        const msgId = targetMsg?.id || '';

        // Resume if same message was paused (audioRef still holds the element)
        if (audioRef.current && audioRef.current.paused && !audioRef.current.ended && pausedMessageId === msgId) {
            audioRef.current.play();
            setSpeakingMessageId(msgId);
            setPausedMessageId(null);
            return;
        }

        // Stop any currently playing or paused audio (different message or fresh play)
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
            setSpeakingMessageId(null);
            setPausedMessageId(null);
        }

        setLoadingAudioId(msgId);

        try {
            const result = await generateSpeech(text, voiceId, ttsProvider);
            const audioUrl = result.audio_url;
            console.log(`🎵 TTS(${result.provider}): ${result.cached ? 'Cache HIT' : 'Generated'}`);

            // Create and play audio
            const audio = new Audio(audioUrl);
            audioRef.current = audio;

            audio.onplay = () => {
                setSpeakingMessageId(msgId);
                setPausedMessageId(null);
                setLoadingAudioId(null);
            };

            audio.onended = () => {
                setSpeakingMessageId(null);
                setPausedMessageId(null);
                audioRef.current = null;
            };

            audio.onerror = () => {
                console.error('Audio playback error');
                setSpeakingMessageId(null);
                setPausedMessageId(null);
                setLoadingAudioId(null);
                audioRef.current = null;
            };

            await audio.play();
        } catch (error) {
            console.error('TTS Error:', error);
            setLoadingAudioId(null);
        }
    }, [currentMessages, pausedMessageId]);

    const handleStopSpeaking = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause();
        }
        const paused = speakingMessageId;
        setSpeakingMessageId(null);
        setPausedMessageId(paused);
        setLoadingAudioId(null);
    }, [speakingMessageId]);

    const handleStop = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsStreaming(false);
        setIsProcessing(false);
        setStreamingContent('');
        setStreamThinking('');
        setCurrentStreamingAgentId(null);
    }, []);

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        if (files.length === 0) return;

        const imageFiles = files.filter(f => f.type.startsWith('image/'));
        const otherFiles = files.filter(f => !f.type.startsWith('image/'));

        // Generate previews for images
        imageFiles.forEach(file => {
            const reader = new FileReader();
            reader.onload = (ev) => {
                setPendingPreviews(prev => [...prev, ev.target?.result as string]);
            };
            reader.readAsDataURL(file);
        });

        setPendingFiles(prev => [...prev, ...imageFiles, ...otherFiles]);

        // Reset input so re-selecting the same file works
        if (fileInputRef.current) fileInputRef.current.value = '';
    }, []);

    const removePendingFile = useCallback((index: number) => {
        setPendingFiles(prev => prev.filter((_, i) => i !== index));
        setPendingPreviews(prev => prev.filter((_, i) => i !== index));
    }, []);

    const handleSend = async () => {
        if ((!input.trim() && pendingFiles.length === 0) || !currentSessionId) return;

        const content = input;
        const attachedFiles = [...pendingFiles];
        const attachedPreviews = [...pendingPreviews];
        setInput('');
        setPendingFiles([]);
        setPendingPreviews([]);
        setIsProcessing(true);

        // Convert images to base64 data URLs for the API
        const imageDataUrls: string[] = [];
        for (const file of attachedFiles) {
            if (file.type.startsWith('image/')) {
                const dataUrl = await new Promise<string>((resolve) => {
                    const reader = new FileReader();
                    reader.onload = (e) => resolve(e.target?.result as string);
                    reader.readAsDataURL(file);
                });
                imageDataUrls.push(dataUrl);
            }
        }

        const newUserId = 'temp-user-' + Date.now();
        const userMsg: Message = {
            id: newUserId,
            chatId: currentSessionId,
            senderId: 'user',
            content: content || (imageDataUrls.length > 0 ? `[Sent ${imageDataUrls.length} image${imageDataUrls.length > 1 ? 's' : ''}]` : ''),
            timestamp: Date.now(),
            imageDataUrls: attachedPreviews.length > 0 ? attachedPreviews : undefined,
        };

        // Optimistic UI Update for User Message
        userJustSentRef.current = true;
        setLocalMessages(prev => [...prev, userMsg]);

        // Get agents
        const participants = currentSession?.participants || [];
        const agentsInChat = agents.filter(a => participants.includes(a.id));
        // const { user: authUser } = useAuth(); // REMOVED: Invalid hook call
        const authUser = user; // Use the user from component scope

        // Sequential processing for agents
        for (const agent of agentsInChat) {
            try {
                // Prepare History — send only the last 20 messages (rolling window)
                // Backend handles full history via PostgreSQL backfill
                const ROLLING_WINDOW = 20;
                const recentMessages = currentMessages.slice(-ROLLING_WINDOW);

                // Build multimodal content for user message if images are attached
                let userContent: string | { type: string; text?: string; image_url?: { url: string } }[];
                if (imageDataUrls.length > 0) {
                    const parts: { type: string; text?: string; image_url?: { url: string } }[] = [];
                    if (content) {
                        parts.push({ type: 'text', text: content });
                    }
                    for (const dataUrl of imageDataUrls) {
                        parts.push({ type: 'image_url', image_url: { url: dataUrl } });
                    }
                    userContent = parts;
                } else {
                    userContent = content;
                }

                const historyContext: ApiChatMessage[] = [
                    ...recentMessages.map(m => ({
                        role: (m.senderId === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
                        content: m.content,
                        timestamp: typeof m.timestamp === 'number' ? m.timestamp : Date.now()
                    })),
                    { role: 'user', content: userContent as any, timestamp: Date.now() }
                ];

                // Setup Streaming State + Abort Controller
                const abortController = new AbortController();
                abortControllerRef.current = abortController;
                setIsStreaming(true);
                setStreamingContent('');
                setStreamThinking('');
                setCurrentStreamingAgentId(agent.id);

                let fullContent = '';
                const mediaAttachments: ToolMediaAttachment[] = [];

                // Call Python Backend
                await chatApi.streamChat(
                    agent.id,
                    historyContext,
                    (event) => {
                        // Route events by type (backend sends typed SSE events)
                        switch (event.type) {
                            case 'content':
                                if (event.content) {
                                    fullContent += event.content;
                                    setStreamingContent(prev => prev + event.content);
                                }
                                break;
                            case 'thinking':
                                if (event.content) {
                                    setStreamThinking(prev => prev + event.content);
                                }
                                break;
                            case 'tool_call':
                                console.log('Tool Call:', event.name, event.arguments);
                                setStreamThinking(prev => prev + `\n🔧 [Tool: ${event.name}]`);
                                break;
                            case 'tool_result':
                                console.log('Tool Result:', event.name, event.result?.slice?.(0, 200));
                                setStreamThinking(prev => prev + ` ✅`);
                                {
                                    const media = parseMediaAttachmentFromToolResult(event.name, event.result);
                                    if (media && !mediaAttachments.some(m => m.relativePath === media.relativePath)) {
                                        mediaAttachments.push(media);
                                    }
                                }
                                break;
                            case 'done':
                                // Backend done event — fullContent from backend available in event.full_content
                                // Use it as fallback if our accumulated content is empty
                                if (!fullContent && event.full_content) {
                                    fullContent = event.full_content;
                                    setStreamingContent(event.full_content);
                                }
                                // Capture usage and cache info
                                if (event.usage) setLastUsageInfo(event.usage);
                                if (event.cache_info) setLastCacheInfo(event.cache_info);
                                break;
                            case 'error':
                                console.error('Stream error event:', event.error);
                                setStreamThinking(prev => prev + `\n❌ [Error: ${event.error}]`);
                                break;
                            case 'content_replace':
                                // Backend detected the model emitted a tool call as raw text.
                                // Clear the streamed content so the JSON doesn't show in the chat.
                                fullContent = event.content ?? '';
                                setStreamingContent(event.content ?? '');
                                break;
                            case 'start':
                                // Capture context metadata for token info display
                                if (event.context_metadata) {
                                    setLastContextMeta(event.context_metadata);
                                }
                                break;
                            default:
                                // Legacy fallback: handle events without type field
                                if (event.content) {
                                    fullContent += event.content;
                                    setStreamingContent(prev => prev + event.content);
                                }
                                if (event.done) {
                                    // Stream finished
                                }
                                break;
                        }
                    },
                    (error) => {
                        console.error('Stream error:', error);
                        setStreamThinking(prev => prev + `\n[Error: ${error}]`);
                    },
                    {
                        user_id: authUser?.uid, // Pass user ID for User Profile lookup
                        chat_id: currentSessionId, // Pass Chat ID for history backfill
                        abortController, // For stop button
                    }
                );

                // Clean up abort controller
                abortControllerRef.current = null;

                // Write final full response appropriately or optimistically update local messages
                if (fullContent) {
                    const agentMsg: Message = {
                        id: 'temp-agent-' + Date.now(),
                        chatId: currentSessionId,
                        senderId: agent.id,
                        content: fullContent,
                        timestamp: Date.now(),
                        mediaAttachments,
                    };
                    setLocalMessages(prev => [...prev, agentMsg]);
                    // Postgres update is handled automatically by the backend chat stream completion.
                }

            } catch (e) {
                console.error('Agent processing error:', e);
            } finally {
                // Reset streaming state for next agent (or end)
                setIsStreaming(false);
                setStreamingContent('');
                setStreamThinking('');
                setCurrentStreamingAgentId(null);
            }
        }

        setIsProcessing(false);
    };

    const createChat = async () => {
        if (!newChatName || selectedAgents.length === 0) return;

        try {
            // Create conversation via App.tsx prop, which creates it locally and selects it
            onCreateSession(newChatName, selectedAgents, selectedAgents.length > 1);
            console.log(`✅ Created new conversation: ${newChatName}`);
        } catch (error) {
            console.error('Failed to create conversation:', error);
        }

        setIsNewChatModalOpen(false);
        setSelectedAgents([]);
        setNewChatName('');
    };

    const toggleAgentSelection = (agentId: string) => {
        if (selectedAgents.includes(agentId)) {
            setSelectedAgents(selectedAgents.filter(id => id !== agentId));
        } else {
            setSelectedAgents([...selectedAgents, agentId]);
        }
    };

    return (
        <div className="flex h-full overflow-hidden relative">
            {/* Mobile Sidebar Toggle Button — only when sidebar is closed */}
            {!showMobileSidebar && (
                <button
                    onClick={() => setShowMobileSidebar(true)}
                    className="md:hidden fixed top-4 left-4 z-50 p-2 bg-nexus-800/90 border border-white/10 rounded-lg text-white shadow-lg backdrop-blur-sm"
                >
                    <Menu className="w-5 h-5" />
                </button>
            )}

            {/* Mobile Overlay */}
            {showMobileSidebar && (
                <div
                    className="md:hidden fixed inset-0 bg-black/50 z-30"
                    onClick={() => setShowMobileSidebar(false)}
                />
            )}

            {/* Unified Conversation List — collapsible */}
            <div className={`
                bg-nexus-900 border-r border-white/5 flex flex-col shrink-0
                transition-[width] duration-200 ease-in-out
                ${sidebarCollapsed ? 'w-0 overflow-hidden border-r-0' : 'w-64'}
                ${showMobileSidebar
                    ? 'fixed inset-y-0 left-0 z-40 !w-64 !overflow-visible flex'
                    : 'hidden md:flex'
                }
            `}>
                {/* Mobile close button inside sidebar */}
                {showMobileSidebar && (
                    <div className="md:hidden flex items-center justify-between p-3 border-b border-white/5">
                        <span className="text-sm font-semibold text-gray-400">Conversations</span>
                        <button
                            onClick={() => setShowMobileSidebar(false)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                )}
                {/* New Chat + Import Buttons */}
                <div className="p-4 border-b border-white/5 flex gap-2">
                    <button
                        onClick={() => {
                            setIsNewChatModalOpen(true);
                            setShowMobileSidebar(false);
                        }}
                        className="flex-1 flex items-center justify-center gap-2 bg-nexus-accent/10 text-nexus-accent border border-nexus-accent/20 p-3 rounded-xl hover:bg-nexus-accent/20 transition-all font-medium"
                    >
                        <Plus className="w-5 h-5" /> New Chat
                    </button>
                    <button
                        onClick={() => {
                            setIsImportModalOpen(true);
                            setShowMobileSidebar(false);
                        }}
                        className="flex items-center justify-center gap-1 bg-white/5 text-gray-400 border border-white/10 px-3 rounded-xl hover:bg-white/10 hover:text-white transition-all"
                        title="Import chat history"
                    >
                        <Upload className="w-4 h-4" />
                    </button>
                </div>

                {/* Search Input */}
                <div className="px-3 py-2 border-b border-white/5">
                    <div className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-2">
                        <Search className="w-4 h-4 text-gray-500" />
                        <input
                            type="text"
                            placeholder="Search conversations..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="flex-1 bg-transparent border-none outline-none text-white text-sm placeholder-gray-500"
                        />
                    </div>
                </div>

                {/* Conversation List */}
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                    {filteredConversations.length === 0 ? (
                        <div className="text-center py-8 text-gray-500 text-sm">
                            {searchQuery ? 'No conversations match your search' : 'No conversations yet'}
                        </div>
                    ) : (
                        filteredConversations.map((conv) => (
                            <div
                                key={conv.id}
                                onClick={() => onSelectSession(conv.id)}
                                className={`p-3 rounded-lg cursor-pointer transition-colors group relative ${conv.id === currentSessionId ? 'bg-white/10' : 'hover:bg-white/5'
                                    }`}
                            >
                                {/* Row 1: Title + delete */}
                                <div className="flex justify-between items-start">
                                    <h4 className="text-white font-medium truncate pr-2 flex-1 min-w-0">{conv.name}</h4>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onDeleteSession(conv.id);
                                        }}
                                        className="opacity-0 group-hover:opacity-100 hover:text-red-400 text-gray-500 transition-opacity flex-shrink-0"
                                        title="Delete conversation"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                                {/* Row 2: Avatar(s) + message count + harvest status */}
                                <div className="flex items-center gap-2 mt-1">
                                    <div className="flex -space-x-2">
                                        {conv.participants.slice(0, 3).map((pId: string) => {
                                            const agent = agents.find(a => a.id === pId);
                                            return agent ? (
                                                <img key={pId} src={agent.avatar} className="w-5 h-5 rounded-full border border-black" alt="" />
                                            ) : null;
                                        })}
                                    </div>
                                    {conv.isGroup && <span className="text-xs text-purple-400">👥</span>}
                                    <span className="text-xs text-gray-400">{conv.messageCount ?? 0} msgs</span>
                                    <HarvestStatusIcon status={conv.harvestState as HarvestState} className="w-3 h-3 flex-shrink-0" />
                                </div>
                            </div>
                        ))
                    )}
                </div>


            </div>

            {/* Desktop collapsed sidebar edge — click to expand */}
            {sidebarCollapsed && (
                <div
                    onClick={() => setSidebarCollapsed(false)}
                    className="hidden md:flex w-8 bg-nexus-900/50 border-r border-white/5 flex-col items-center pt-4 cursor-pointer hover:bg-nexus-900/80 transition-colors shrink-0"
                    title="Show conversations"
                >
                    <PanelLeftOpen className="w-4 h-4 text-gray-500 hover:text-white" />
                </div>
            )}

            {/* Main Chat Area */}
            <div className="flex-1 flex flex-col bg-nexus-900/50 backdrop-blur-sm relative min-w-0">
                {!currentSessionId ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-gray-500 relative">
                        <div className="w-24 h-24 rounded-full bg-white/5 flex items-center justify-center mb-6 animate-pulse-slow">
                            <Bot className="w-12 h-12 text-nexus-accent" />
                        </div>
                        <h2 className="text-2xl font-bold text-white mb-2">ClingySOCKs</h2>
                        <p>Select or create a neural session to begin.</p>
                    </div>
                ) : (
                    <>
                        {/* Header */}
                        <div className="h-16 border-b border-white/5 flex items-center justify-between px-6 pl-14 md:pl-6 bg-nexus-900/80 backdrop-blur-md z-10">
                            {/* Sidebar collapse/expand toggle (desktop only) */}
                            <button
                                onClick={() => setSidebarCollapsed(prev => !prev)}
                                className="hidden md:flex items-center justify-center p-1.5 mr-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors shrink-0"
                                title={sidebarCollapsed ? 'Show conversations' : 'Hide conversations'}
                            >
                                {sidebarCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
                            </button>
                            <div className="flex-1 min-w-0">
                                <h3 className="text-white font-bold flex items-center gap-2 truncate">
                                    {currentSession?.name}
                                    {currentSession?.isGroup && <span className="bg-nexus-cosy/10 text-nexus-cosy text-xs px-2 py-0.5 rounded shrink-0">Group</span>}
                                </h3>
                                <p className="text-xs text-gray-500 truncate">
                                    {currentSession?.participants.map(pid => agents.find(a => a.id === pid)?.name).join(', ')}
                                </p>
                            </div>                           
                        </div>

                        {/* Messages */}
                        <div ref={messagesContainerRef} onScroll={handleMessagesScroll} className="flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4 md:p-6 space-y-4 md:space-y-6">
                            {loadingOlder && (
                                <div className="flex justify-center py-3">
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                        <span className="w-3 h-3 border-2 border-gray-500 border-t-transparent rounded-full animate-spin" />
                                        Loading older messages…
                                    </div>
                                </div>
                            )}
                            {!hasMore && (currentMessages.length > 0 || sessionMessages.length > 0) && (
                                <div className="text-center text-xs text-gray-600 py-2">— Beginning of conversation —</div>
                            )}
                            {(currentMessages.length > 0 ? currentMessages : sessionMessages).map((msg) => {
                                const agent = agents.find(a => a.id === msg.senderId);
                                return (
                                    <MessageBubble
                                        key={msg.id}
                                        msg={msg}
                                        isUser={msg.senderId === 'user'}
                                        agent={agent}
                                        onSpeak={handleSpeak}
                                        onStopSpeaking={handleStopSpeaking}
                                        isSpeaking={speakingMessageId === msg.id}
                                        isPaused={pausedMessageId === msg.id}
                                        isLoadingAudio={loadingAudioId === msg.id}
                                    />
                                );
                            })}

                            {/* Streaming Message Bubble */}
                            {isStreaming && (
                                <MessageBubble
                                    msg={{
                                        id: 'streaming-temp',
                                        chatId: currentSessionId || '',
                                        senderId: currentStreamingAgentId || 'unknown',
                                        content: streamingContent + (streamThinking ? `\n\n*Thinking:*\n${streamThinking}` : '') || '...', // Show thinking too if debug needed, or just content
                                        timestamp: Date.now()
                                    }}
                                    isUser={false}
                                    agent={agents.find(a => a.id === currentStreamingAgentId)}
                                    isSpeaking={false}
                                    isLoadingAudio={false}
                                />
                            )}

                            {isProcessing && !isStreaming && (
                                <div className="flex justify-start">
                                    <div className="flex max-w-[80%] gap-4 flex-row">
                                        <div className="w-10 h-10 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center shrink-0">
                                            <Cpu className="w-5 h-5 text-nexus-cosy animate-spin" />
                                        </div>
                                        <div className="flex items-center gap-1 bg-white/5 px-4 py-3 rounded-2xl rounded-tl-none">
                                            <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                                            <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                                            <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Token Info Panel (collapsible) */}
                        {lastContextMeta && (
                            <div style={{
                                borderTop: '1px solid rgba(255,255,255,0.05)',
                                background: showTokenInfo ? 'rgba(0,0,0,0.3)' : 'transparent',
                            }}>
                                <button
                                    onClick={() => setShowTokenInfo(!showTokenInfo)}
                                    style={{
                                        width: '100%', display: 'flex', alignItems: 'center', gap: 6,
                                        padding: '4px 16px', fontSize: 10, color: 'rgba(255,255,255,0.35)',
                                        background: 'none', border: 'none', cursor: 'pointer',
                                        justifyContent: 'center',
                                    }}
                                >
                                    <BarChart3 size={10} />
                                    <span>
                                        {lastContextMeta.totalChars?.toLocaleString() || '—'} chars
                                        {lastUsageInfo ? ` · ${lastUsageInfo.prompt_tokens?.toLocaleString() || '?'}→${lastUsageInfo.completion_tokens?.toLocaleString() || '?'} tokens` : ''}
                                        {lastCacheInfo?.cache_pct ? ` · ${lastCacheInfo.cache_pct}% cached` : ''}
                                    </span>
                                    {showTokenInfo ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                                </button>
                                {showTokenInfo && (
                                    <div style={{
                                        padding: '8px 16px 10px', fontSize: 10,
                                        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px',
                                        color: 'rgba(255,255,255,0.45)', fontFamily: 'monospace',
                                    }}>
                                        {lastContextMeta.sectionChars && Object.entries(lastContextMeta.sectionChars as Record<string, number>).map(([key, val]) => (
                                            <div key={key} style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ color: 'rgba(255,255,255,0.3)' }}>{key.replace(/([A-Z])/g, ' $1').trim()}</span>
                                                <span>{(val as number).toLocaleString()}</span>
                                            </div>
                                        ))}
                                        {lastContextMeta.budgetLimits && (
                                            <>
                                                <div style={{ gridColumn: '1 / -1', borderTop: '1px solid rgba(255,255,255,0.05)', margin: '4px 0' }} />
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: 'rgba(255,255,255,0.3)' }}>Warm budget</span>
                                                    <span>{lastContextMeta.budgetLimits.maxWarmMemory?.toLocaleString()}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: 'rgba(255,255,255,0.3)' }}>Hist budget</span>
                                                    <span>{lastContextMeta.budgetLimits.maxHistoryChars?.toLocaleString()}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: 'rgba(255,255,255,0.3)' }}>History msgs</span>
                                                    <span>{lastContextMeta.historyMessageCount || '—'} / {lastContextMeta.budgetLimits.maxHistoryMessages}</span>
                                                </div>
                                                {lastContextMeta.budgetLimits.maxContextChars && (
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: 'rgba(255,255,255,0.3)' }}>Total budget</span>
                                                        <span>{lastContextMeta.budgetLimits.maxContextChars.toLocaleString()}</span>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                        {lastUsageInfo && (
                                            <>
                                                <div style={{ gridColumn: '1 / -1', borderTop: '1px solid rgba(255,255,255,0.05)', margin: '4px 0' }} />
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: 'rgba(255,255,255,0.3)' }}>Prompt tokens</span>
                                                    <span>{lastUsageInfo.prompt_tokens?.toLocaleString()}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                    <span style={{ color: 'rgba(255,255,255,0.3)' }}>Completion tokens</span>
                                                    <span>{lastUsageInfo.completion_tokens?.toLocaleString()}</span>
                                                </div>
                                                {lastCacheInfo?.cached_tokens && (
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#34d399' }}>
                                                        <span>Cached</span>
                                                        <span>{lastCacheInfo.cached_tokens.toLocaleString()} ({lastCacheInfo.cache_pct}%)</span>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                        <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'space-between', marginTop: 2, fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>
                                            <span>Level: {lastContextMeta.warmLevel}</span>
                                            <span>Total: {lastContextMeta.totalChars?.toLocaleString()} chars</span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Input */}
                        <div className="p-2 md:p-4 bg-nexus-900 border-t border-white/5">
                            {/* File attachment previews */}
                            {pendingPreviews.length > 0 && (
                                <div className="max-w-4xl mx-auto mb-2 flex flex-wrap gap-2 px-2">
                                    {pendingPreviews.map((preview, i) => (
                                        <div key={i} className="relative group/preview">
                                            <img src={preview} alt={`Attachment ${i + 1}`} className="h-16 w-16 object-cover rounded-lg border border-white/10" />
                                            <button
                                                onClick={() => removePendingFile(i)}
                                                className="absolute -top-1.5 -right-1.5 p-0.5 rounded-full bg-red-500/80 text-white opacity-0 group-hover/preview:opacity-100 transition-opacity"
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <div className="max-w-4xl mx-auto relative flex items-center gap-2 bg-white/5 rounded-xl border border-white/10 p-2 focus-within:border-nexus-accent/50 focus-within:bg-white/10 transition-all">
                                <button
                                    onClick={() => setShowVoiceMode(true)}
                                    className="p-2 text-gray-500 hover:text-nexus-accent transition-colors"
                                    title="Voice mode"
                                >
                                    <Mic className="w-5 h-5" />
                                </button>
                                {/* File attachment button */}
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="p-2 text-gray-500 hover:text-white transition-colors"
                                    title="Attach image"
                                >
                                    <Paperclip className="w-5 h-5" />
                                </button>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept="image/*"
                                    multiple
                                    onChange={handleFileSelect}
                                    className="hidden"
                                />
                                <textarea
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSend();
                                        }
                                    }}
                                    onPaste={(e) => {
                                        // Handle pasting images from clipboard
                                        const items = e.clipboardData?.items;
                                        if (!items) return;
                                        for (const item of Array.from(items)) {
                                            if (item.type.startsWith('image/')) {
                                                e.preventDefault();
                                                const file = item.getAsFile();
                                                if (file) {
                                                    const reader = new FileReader();
                                                    reader.onload = (ev) => {
                                                        setPendingPreviews(prev => [...prev, ev.target?.result as string]);
                                                    };
                                                    reader.readAsDataURL(file);
                                                    setPendingFiles(prev => [...prev, file]);
                                                }
                                            }
                                        }
                                    }}
                                    placeholder={`Message ${currentSession?.name || 'agent'}...`}
                                    className="flex-1 bg-transparent border-none outline-none text-white placeholder-gray-500 resize-none min-h-[24px] max-h-[120px]"
                                    rows={1}
                                />
                                {isStreaming || isProcessing ? (
                                    <button
                                        onClick={handleStop}
                                        className="p-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 hover:text-red-300 transition-all border border-red-500/30"
                                        title="Stop generating"
                                    >
                                        <Square className="w-5 h-5 fill-current" />
                                    </button>
                                ) : (
                                    <button
                                        onClick={handleSend}
                                        disabled={!input.trim() && pendingFiles.length === 0}
                                        className={`p-2 rounded-lg transition-all ${(input.trim() || pendingFiles.length > 0) ? 'bg-nexus-accent text-nexus-900 hover:shadow-[0_0_10px_#00f2ff]' : 'bg-white/10 text-gray-500 cursor-not-allowed'
                                            }`}
                                    >
                                        <Send className="w-5 h-5" />
                                    </button>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Import Chat Modal */}
            <ChatImportModal
                isOpen={isImportModalOpen}
                onClose={() => setIsImportModalOpen(false)}
                onImportComplete={() => onRefreshSessions?.()}
                agents={agents}
                userId={user?.uid || ''}
            />

            {/* New Chat Modal */}
            {isNewChatModalOpen && (
                <div className="absolute inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
                    <div className="bg-nexus-800 border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-2xl">
                        <h3 className="text-xl font-bold text-white mb-4">Initialize Session</h3>

                        <div className="mb-4">
                            <label className="block text-sm text-gray-400 mb-1">Session Name</label>
                            <input
                                type="text"
                                value={newChatName}
                                onChange={(e) => setNewChatName(e.target.value)}
                                className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 text-white focus:border-nexus-accent outline-none"
                                placeholder="e.g., Project Titan"
                            />
                        </div>

                        <div className="mb-6">
                            <label className="block text-sm text-gray-400 mb-2">Select Agents</label>
                            <div className="space-y-2 max-h-60 overflow-y-auto">
                                {agents.map(agent => (
                                    <div
                                        key={agent.id}
                                        onClick={() => toggleAgentSelection(agent.id)}
                                        className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${selectedAgents.includes(agent.id)
                                            ? 'bg-nexus-accent/10 border-nexus-accent'
                                            : 'bg-white/5 border-white/10 hover:border-white/30'
                                            }`}
                                    >
                                        <img src={agent.avatar} className="w-8 h-8 rounded-full" alt="" />
                                        <div>
                                            <div className="text-sm font-bold text-white">{agent.name}</div>
                                            <div className="text-xs text-gray-500">{agent.role}</div>
                                        </div>
                                        {selectedAgents.includes(agent.id) && <div className="ml-auto w-2 h-2 rounded-full bg-nexus-accent"></div>}
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="flex justify-end gap-3">
                            <button
                                onClick={() => setIsNewChatModalOpen(false)}
                                className="px-4 py-2 rounded-lg text-gray-400 hover:text-white"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={createChat}
                                disabled={!newChatName || selectedAgents.length === 0}
                                className="px-6 py-2 rounded-lg bg-nexus-accent text-nexus-900 font-bold disabled:opacity-50"
                            >
                                Initialize
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Voice Mode Overlay */}
            {showVoiceMode && currentSession && (() => {
                const agent = agents.find(a => currentSession.participants.includes(a.id));
                return (
                    <VoiceMode
                        entityId={agent?.id || currentSession.participants[0] || ''}
                        userId={user?.uid}
                        chatId={currentSession.id}
                        agentName={agent?.name}
                        agentAvatar={agent?.avatar}
                        onClose={() => setShowVoiceMode(false)}
                        onTranscript={(role, text) => {
                            // Show transcript in the chat window in real-time
                            if (text) {
                                const msg: Message = {
                                    id: `voice-${role}-${Date.now()}`,
                                    chatId: currentSession.id,
                                    senderId: role === 'user' ? 'user' : (agent?.id || 'assistant'),
                                    content: text,
                                    timestamp: Date.now(),
                                };
                                onReceiveMessage(msg);
                            }
                        }}
                    />
                );
            })()}
        </div>
    );
};
