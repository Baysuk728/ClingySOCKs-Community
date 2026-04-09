import React, { useState, useEffect } from 'react';
import { Agent } from '../types';
import { getApiUrlSync, API_KEY } from '../services/apiConfig';
import {
    getWarmMemory,
    getEntityMeta,
    updateMemoryDocument,
    initializeEntityMemory,
    createCustomMemoryType,
    resolveProposal,
    MemoryMeta,
    WarmMemory,
    EntityType,
    compressMemoryOnDemand,
    getCompressedMemory
} from '../services/memoryServiceV2';
import {
    subscribeToConversations,
    deleteConversation,
    deleteConversations,
    updateConversationTitle,
    ConversationSummary,
    HarvestStatus
} from '../services/conversationService';
import { getToken, getCurrentUser } from '../auth';
import {
    SupportNeedsForm,
    LifeStatesForm,
    AttachmentForm
} from './HumanMemoryForms';
import { ChatImportModal } from './ChatImportModal';
import { ConversationHarvestView } from './ConversationHarvestView';
import {
    Brain,
    Save,
    Plus,
    Activity,
    Database,
    RefreshCw,
    Edit3,
    Sparkles,
    User,
    Heart,
    Clock,
    Target,
    Users,
    ChevronDown,
    ChevronRight,
    Check,
    X,
    AlertCircle,
    FileText,
    Upload,
    Trash2,
    MoreVertical,
    Loader2,
    MessageSquare,
    Eye,
    Zap
} from 'lucide-react';

interface MemoryManagerV2Props {
    agents: Agent[];
    currentUserId?: string;
}

type EntitySelection = {
    id: string;
    type: EntityType;
    name: string;
};

const BANK_ICONS: Record<string, React.ReactNode> = {
    persona: <User className="w-4 h-4" />,
    history: <Clock className="w-4 h-4" />,
    emotional: <Heart className="w-4 h-4" />,
    self: <User className="w-4 h-4" />,
    lifestyle: <Target className="w-4 h-4" />,
    life_states: <AlertCircle className="w-4 h-4" />,
    relationships: <Users className="w-4 h-4" />
};

const BANK_COLORS: Record<string, string> = {
    persona: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    history: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    emotional: 'text-pink-400 bg-pink-500/10 border-pink-500/20',
    self: 'text-green-400 bg-green-500/10 border-green-500/20',
    lifestyle: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
    life_states: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
    relationships: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20'
};

export const MemoryManagerV2: React.FC<MemoryManagerV2Props> = ({ agents, currentUserId }) => {
    const [selectedEntity, setSelectedEntity] = useState<EntitySelection | null>(null);
    const [meta, setMeta] = useState<MemoryMeta | null>(null);
    const [warmMemory, setWarmMemory] = useState<WarmMemory | null>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [activeTab, setActiveTab] = useState<'warm' | 'proposals' | 'cold'>('warm');

    // Editing state
    const [editingPath, setEditingPath] = useState<string | null>(null); // "bank/doc"
    const [editContent, setEditContent] = useState<string>('');

    // Expanded banks
    const [expandedBanks, setExpandedBanks] = useState<Set<string>>(new Set(['persona', 'self']));

    // New type creation
    const [isCreatingType, setIsCreatingType] = useState(false);
    const [newBankName, setNewBankName] = useState('');
    const [newDocName, setNewDocName] = useState('');
    const [newDocDesc, setNewDocDesc] = useState('');

    // Chat import modal
    const [showImportModal, setShowImportModal] = useState(false);

    // Conversations state
    const [conversations, setConversations] = useState<ConversationSummary[]>([]);
    const [selectedConvIds, setSelectedConvIds] = useState<Set<string>>(new Set());
    const [editingConvId, setEditingConvId] = useState<string | null>(null);
    const [editingConvTitle, setEditingConvTitle] = useState('');
    const [harvestingConvs, setHarvestingConvs] = useState(false);
    const [harvestAbortController, setHarvestAbortController] = useState<AbortController | null>(null);

    // New tabs for per-conv results
    const [viewMode, setViewMode] = useState<'memory' | 'conversations'>('conversations');

    // Viewing per-conversation harvest results
    const [viewingConvId, setViewingConvId] = useState<string | null>(null);

    // Harvest options
    const [focusArea, setFocusArea] = useState<'full' | 'inside_jokes' | 'artifacts' | 'patterns' | 'relationships'>('full');
    const [llmChoice, setLlmChoice] = useState<'auto' | 'gemini' | 'openai'>('auto');
    const [forceFullHarvest, setForceFullHarvest] = useState(false);  // NEW: Ignore lastHarvestedMessageIndex
    const [showHarvestOptions, setShowHarvestOptions] = useState(false);

    // Compression state
    const [showCompressionPanel, setShowCompressionPanel] = useState(false);
    const [compressionLimit, setCompressionLimit] = useState(30000);
    const [compressionModel, setCompressionModel] = useState<'gemini' | 'openai'>('gemini');
    const [isCompressing, setIsCompressing] = useState(false);
    const [compressionResult, setCompressionResult] = useState<{ success: boolean; characterCount: number; error?: string } | null>(null);
    const [lastCompressed, setLastCompressed] = useState<Date | null>(null);

    // Manual Dev Triggers
    const [userHarvestingConvId, setUserHarvestingConvId] = useState<string | null>(null);
    const [isBridging, setIsBridging] = useState(false);

    // Build entity list (agents + current user as human)
    const entities: EntitySelection[] = [
        ...(currentUserId ? [{ id: `human-${currentUserId}`, type: 'human' as EntityType, name: 'You (Human)' }] : []),
        ...agents.map(a => ({ id: a.id, type: 'agent' as EntityType, name: a.name }))
    ];

    useEffect(() => {
        if (entities.length > 0 && !selectedEntity) {
            // Default to first agent
            const firstAgent = entities.find(e => e.type === 'agent');
            if (firstAgent) setSelectedEntity(firstAgent);
        }
    }, [entities, selectedEntity]);

    useEffect(() => {
        if (!selectedEntity) return;
        loadMemoryData(selectedEntity.id);
    }, [selectedEntity]);

    // Subscribe to conversations for selected agent
    useEffect(() => {
        if (!selectedEntity || selectedEntity.type !== 'agent') {
            setConversations([]);
            return;
        }

        const unsubscribe = subscribeToConversations(selectedEntity.id, (convs) => {
            setConversations(convs.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()));
        });

        return unsubscribe;
    }, [selectedEntity]);

    // Conversation action handlers
    const handleDeleteConversation = async (id: string) => {
        if (!confirm('Delete this conversation?')) return;
        try {
            await deleteConversation(id);
        } catch (error) {
            console.error('Failed to delete:', error);
        }
    };

    const handleDeleteSelected = async () => {
        if (selectedConvIds.size === 0) return;
        if (!confirm(`Delete ${selectedConvIds.size} conversations?`)) return;
        try {
            await deleteConversations(Array.from(selectedConvIds));
            setSelectedConvIds(new Set());
        } catch (error) {
            console.error('Failed to delete:', error);
        }
    };

    const handleRenameConversation = async (id: string, newTitle: string) => {
        try {
            await updateConversationTitle(id, newTitle);
            setEditingConvId(null);
        } catch (error) {
            console.error('Failed to rename:', error);
        }
    };

    const handleHarvestConversations = async (convIds: string[]) => {
        if (!selectedEntity) return;

        // Create new AbortController for this harvest
        const abortController = new AbortController();
        setHarvestAbortController(abortController);
        setHarvestingConvs(true);

        const apiUrl = getApiUrlSync();

        try {
            const res = await fetch(`${apiUrl}/harvest/conversations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${getToken()}`,
                    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
                },
                body: JSON.stringify({
                    conversationIds: convIds,
                    agentId: selectedEntity.id,
                    focusArea,
                    llmChoice,
                    forceFullHarvest,
                }),
                signal: abortController.signal,
            });
            if (!res.ok) throw new Error(`Harvest failed: ${res.status}`);
        } catch (error: any) {
            if (error.name === 'AbortError' || abortController.signal.aborted) {
                console.log('Harvest cancelled by user');
            } else {
                console.error('Harvest failed:', error);
                alert('Harvest failed. Check console.');
            }
        } finally {
            setHarvestingConvs(false);
            setHarvestAbortController(null);
        }
    };

    const handleCancelHarvest = () => {
        if (harvestAbortController) {
            harvestAbortController.abort();
            setHarvestingConvs(false);
            setHarvestAbortController(null);
            console.log('🛑 Harvest cancelled');
        }
    };

    const toggleConvSelection = (id: string) => {
        setSelectedConvIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const toggleSelectAll = () => {
        if (selectedConvIds.size === conversations.length) {
            setSelectedConvIds(new Set());
        } else {
            setSelectedConvIds(new Set(conversations.map(c => c.id)));
        }
    };

    const getHarvestStatusColor = (status: HarvestStatus) => {
        switch (status) {
            case 'harvested': return 'text-green-400';
            case 'partially_harvested': return 'text-yellow-400';
            default: return 'text-gray-500';
        }
    };

    const getHarvestStatusIcon = (status: HarvestStatus) => {
        switch (status) {
            case 'harvested': return '🟢';
            case 'partially_harvested': return '🟡';
            default: return '⚪';
        }
    };

    const loadMemoryData = async (entityId: string) => {
        setLoading(true);
        try {
            const [metaData, warmData] = await Promise.all([
                getEntityMeta(entityId),
                getWarmMemory(entityId)
            ]);
            setMeta(metaData);
            setWarmMemory(warmData);
        } catch (error) {
            console.error("Failed to load memory data:", error);
            setMeta(null);
            setWarmMemory(null);
        } finally {
            setLoading(false);
        }
    };

    const handleInitialize = async () => {
        if (!selectedEntity) return;
        setSaving(true);
        try {
            await initializeEntityMemory(selectedEntity.id, selectedEntity.type, selectedEntity.name);
            await loadMemoryData(selectedEntity.id);
        } catch (error) {
            console.error("Failed to initialize memory:", error);
            alert("Failed to initialize memory.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveDocument = async (bankName: string, docName: string) => {
        if (!selectedEntity) return;
        setSaving(true);
        try {
            let contentParsed;
            try {
                contentParsed = JSON.parse(editContent);
            } catch (e) {
                alert("Invalid JSON format");
                setSaving(false);
                return;
            }

            await updateMemoryDocument(selectedEntity.id, bankName, docName, contentParsed, false);

            // Update local state
            setWarmMemory(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    [bankName]: {
                        ...prev[bankName],
                        [docName]: contentParsed
                    }
                };
            });
            setEditingPath(null);
        } catch (error) {
            console.error("Failed to save:", error);
            alert("Failed to save. Check console.");
        } finally {
            setSaving(false);
        }
    };

    const handleCreateType = async () => {
        if (!selectedEntity || !newBankName || !newDocName) return;
        setSaving(true);
        try {
            await createCustomMemoryType(selectedEntity.id, {
                bankName: newBankName,
                docName: newDocName.toLowerCase().replace(/\s+/g, '_'),
                description: newDocDesc,
                initialContent: {},
                addedBy: 'user'
            });
            setIsCreatingType(false);
            setNewBankName('');
            setNewDocName('');
            setNewDocDesc('');
            loadMemoryData(selectedEntity.id);
        } catch (error) {
            console.error("Failed to create type:", error);
            alert("Failed to create memory type.");
        } finally {
            setSaving(false);
        }
    };

    const handleResolveProposal = async (proposalId: string, approved: boolean) => {
        if (!selectedEntity) return;
        setSaving(true);
        try {
            await resolveProposal(selectedEntity.id, proposalId, approved);
            loadMemoryData(selectedEntity.id);
        } catch (error) {
            console.error("Failed to resolve proposal:", error);
        } finally {
            setSaving(false);
        }
    };

    // On-demand memory compression handler
    const handleCompressMemory = async () => {
        if (!selectedEntity) return;
        setIsCompressing(true);
        setCompressionResult(null);

        try {
            const result = await compressMemoryOnDemand(selectedEntity.id, {
                characterLimit: compressionLimit,
                model: compressionModel
            });

            setCompressionResult(result);
            if (result.success) {
                setLastCompressed(new Date());
            }
        } catch (error) {
            setCompressionResult({
                success: false,
                characterCount: 0,
                error: (error as Error).message
            });
        } finally {
            setIsCompressing(false);
        }
    };

    // Load compression status when entity changes
    const loadCompressionStatus = async (entityId: string) => {
        try {
            const result = await getCompressedMemory(entityId);
            if (result.exists && result.lastCompressed) {
                setLastCompressed(new Date(result.lastCompressed.seconds * 1000));
            } else {
                setLastCompressed(null);
            }
        } catch {
            setLastCompressed(null);
        }
    };

    useEffect(() => {
        if (selectedEntity) {
            loadCompressionStatus(selectedEntity.id);
        }
    }, [selectedEntity]);

    const toggleBank = (bankName: string) => {
        setExpandedBanks(prev => {
            const next = new Set(prev);
            if (next.has(bankName)) {
                next.delete(bankName);
            } else {
                next.add(bankName);
            }
            return next;
        });
    };

    // Manual Trigger Handlers
    const handleUserHarvest = async (conversationId: string) => {
        setUserHarvestingConvId(conversationId);
        const apiUrl = getApiUrlSync();
        try {
            const user = getCurrentUser();
            if (!user) throw new Error("Not authenticated");

            const res = await fetch(`${apiUrl}/harvest/user`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${getToken()}`,
                    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
                },
                body: JSON.stringify({ userId: user.uid, conversationId }),
            });
            if (!res.ok) throw new Error(`User harvest failed: ${res.status}`);

            alert("✅ User Twin Harvest Complete!");
        } catch (err) {
            console.error(err);
            alert(`User Harvest Failed: ${(err as Error).message}`);
        } finally {
            setUserHarvestingConvId(null);
        }
    };

    const handleBridge = async () => {
        if (!selectedEntity) return;
        setIsBridging(true);
        const apiUrl = getApiUrlSync();
        try {
            const user = getCurrentUser();
            if (!user) throw new Error("Not authenticated");

            const res = await fetch(`${apiUrl}/harvest/bridge`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${getToken()}`,
                    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
                },
                body: JSON.stringify({
                    userId: user.uid,
                    agentId: selectedEntity.id,
                    agentName: selectedEntity.name,
                }),
            });
            if (!res.ok) throw new Error(`Bridge generation failed: ${res.status}`);

            alert("✅ Session Bridge Generated!");
        } catch (err) {
            console.error(err);
            alert(`Bridge Failed: ${(err as Error).message}`);
        } finally {
            setIsBridging(false);
        }
    };

    const formatJSON = (data: any) => JSON.stringify(data, null, 2);

    const isInitialized = meta !== null && warmMemory !== null;

    return (
        <div className="flex h-full bg-nexus-900/50 text-gray-200">
            {/* Sidebar - Agent Dropdown + Conversations */}
            <div className="w-80 border-r border-white/5 bg-nexus-900/80 p-4 flex flex-col gap-3 overflow-hidden">
                <h2 className="text-nexus-accent font-bold flex items-center gap-2">
                    <Brain className="w-5 h-5" /> Memory Bank
                </h2>

                {/* Agent Dropdown */}
                <select
                    value={selectedEntity?.id || ''}
                    onChange={(e) => {
                        const entity = entities.find(ent => ent.id === e.target.value);
                        if (entity) setSelectedEntity(entity);
                    }}
                    className="w-full bg-nexus-700 border border-white/10 rounded-lg px-3 py-2 text-white"
                >
                    {agents.map(agent => (
                        <option key={agent.id} value={agent.id}>{agent.name}</option>
                    ))}
                </select>

                {/* Action Bar */}
                <div className="flex gap-2">
                    <button
                        onClick={() => setShowImportModal(true)}
                        className="flex-1 py-2 bg-nexus-accent/20 text-nexus-accent rounded-lg text-sm hover:bg-nexus-accent/30 flex items-center justify-center gap-1"
                    >
                        <Upload className="w-4 h-4" /> Import
                    </button>
                    {selectedConvIds.size > 0 && (
                        <>
                            {!harvestingConvs ? (
                                <button
                                    onClick={() => handleHarvestConversations(Array.from(selectedConvIds))}
                                    className="px-3 py-2 bg-purple-600/30 text-purple-300 rounded-lg text-sm hover:bg-purple-600/50"
                                >
                                    🌾 Harvest
                                </button>
                            ) : (
                                <>
                                    <button
                                        disabled
                                        className="px-3 py-2 bg-purple-600/30 text-purple-300 rounded-lg text-sm opacity-50 flex items-center gap-2"
                                    >
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Harvesting...
                                    </button>
                                    <button
                                        onClick={handleCancelHarvest}
                                        className="px-3 py-2 bg-red-600/30 text-red-300 rounded-lg text-sm hover:bg-red-600/50 flex items-center gap-1"
                                    >
                                        <span>✖</span> Cancel
                                    </button>
                                </>
                            )}
                            {!harvestingConvs && (
                                <button
                                    onClick={handleDeleteSelected}
                                    className="px-3 py-2 bg-red-600/30 text-red-300 rounded-lg text-sm hover:bg-red-600/50"
                                >
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            )}
                        </>
                    )}
                </div>

                {/* Harvest Options (collapsible) */}
                <div className="border border-white/10 rounded-lg overflow-hidden">
                    <button
                        onClick={() => setShowHarvestOptions(!showHarvestOptions)}
                        className="w-full flex items-center justify-between p-2 bg-purple-900/20 hover:bg-purple-900/30 text-sm"
                    >
                        <span className="text-purple-300 flex items-center gap-2">
                            🌾 Harvest Options
                        </span>
                        {showHarvestOptions ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                    {showHarvestOptions && (
                        <div className="p-2 space-y-2 bg-nexus-800/30">
                            <div>
                                <label className="text-xs text-gray-500 mb-1 block">Focus Area</label>
                                <select
                                    value={focusArea}
                                    onChange={(e) => setFocusArea(e.target.value as typeof focusArea)}
                                    className="w-full bg-nexus-700 border border-white/10 rounded px-2 py-1.5 text-xs text-white"
                                >
                                    <option value="full">Full Harvest</option>
                                    <option value="inside_jokes">Inside Jokes</option>
                                    <option value="artifacts">Poems & Artifacts</option>
                                    <option value="patterns">Emotional Patterns</option>
                                    <option value="relationships">Relationships</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-xs text-gray-500 mb-1 block">LLM Model</label>
                                <select
                                    value={llmChoice}
                                    onChange={(e) => setLlmChoice(e.target.value as typeof llmChoice)}
                                    className="w-full bg-nexus-700 border border-white/10 rounded px-2 py-1.5 text-xs text-white"
                                >
                                    <option value="auto">Auto (Gemini → OpenAI)</option>
                                    <option value="gemini">Gemini Only</option>
                                    <option value="openai">OpenAI Only</option>
                                </select>
                            </div>
                            {/* Force Full Harvest Toggle */}
                            <label className="flex items-center gap-2 text-xs cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={forceFullHarvest}
                                    onChange={(e) => setForceFullHarvest(e.target.checked)}
                                    className="rounded border-white/20 bg-nexus-700"
                                />
                                <span className="text-yellow-400">🔄 Force Re-Harvest</span>
                                <span className="text-gray-500">(ignore previous)</span>
                            </label>
                        </div>
                    )}
                </div>

                {/* Memory Compression Panel */}
                <div className="border border-white/10 rounded-lg overflow-hidden">
                    <button
                        onClick={() => setShowCompressionPanel(!showCompressionPanel)}
                        className="w-full flex items-center justify-between p-2 bg-cyan-900/20 hover:bg-cyan-900/30 text-sm"
                    >
                        <span className="text-cyan-300 flex items-center gap-2">
                            <Zap className="w-4 h-4" /> Memory Compression
                            {lastCompressed && (
                                <span className="text-xs text-gray-500">
                                    (Last: {lastCompressed.toLocaleDateString()})
                                </span>
                            )}
                        </span>
                        {showCompressionPanel ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                    {showCompressionPanel && (
                        <div className="p-3 space-y-3 bg-nexus-800/30">
                            <p className="text-xs text-gray-400">
                                Compress warm memory into a Markdown character sheet for efficient chat context.
                            </p>

                            {/* Character Limit Slider */}
                            <div>
                                <label className="text-xs text-gray-500 mb-1 flex justify-between">
                                    <span>Character Limit</span>
                                    <span className="text-cyan-400">{compressionLimit.toLocaleString()}</span>
                                </label>
                                <input
                                    type="range"
                                    min="10000"
                                    max="40000"
                                    step="1000"
                                    value={compressionLimit}
                                    onChange={(e) => setCompressionLimit(parseInt(e.target.value))}
                                    className="w-full accent-cyan-500"
                                />
                                <div className="flex justify-between text-xs text-gray-600">
                                    <span>10k (compact)</span>
                                    <span>30k (target)</span>
                                    <span>40k (max)</span>
                                </div>
                            </div>

                            {/* Model Selector */}
                            <div>
                                <label className="text-xs text-gray-500 mb-1 block">Compression Model</label>
                                <select
                                    value={compressionModel}
                                    onChange={(e) => setCompressionModel(e.target.value as 'gemini' | 'openai')}
                                    className="w-full bg-nexus-700 border border-white/10 rounded px-2 py-1.5 text-xs text-white"
                                >
                                    <option value="gemini">Gemini 1.5 Flash</option>
                                    <option value="openai">GPT-4o-mini</option>
                                </select>
                            </div>

                            {/* Compress Button */}
                            <button
                                onClick={handleCompressMemory}
                                disabled={isCompressing || !selectedEntity}
                                className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-cyan-600 text-white rounded-lg text-sm hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isCompressing ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Compressing...
                                    </>
                                ) : (
                                    <>
                                        <Zap className="w-4 h-4" />
                                        Compress Now
                                    </>
                                )}
                            </button>

                            {/* Result Display */}
                            {compressionResult && (
                                <div className={`p-2 rounded text-xs ${compressionResult.success
                                    ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                                    : 'bg-red-500/20 text-red-300 border border-red-500/30'
                                    }`}>
                                    {compressionResult.success ? (
                                        <span>✅ Compressed to {compressionResult.characterCount.toLocaleString()} characters</span>
                                    ) : (
                                        <span>❌ {compressionResult.error}</span>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                </div>

                {/* Dev Tools Panel */}
                <div className="border border-white/10 rounded-lg overflow-hidden mt-2">
                    <div className="p-2 bg-nexus-800/30">
                        <span className="text-xs text-gray-500 font-bold mb-2 block">Dev Tools</span>
                        <div className="grid grid-cols-1 gap-2">
                            <button
                                onClick={handleBridge}
                                disabled={isBridging || !selectedEntity}
                                className="flex flex-col items-center justify-center p-2 bg-nexus-700/50 hover:bg-nexus-700 rounded-lg border border-white/5 text-xs text-amber-300"
                            >
                                {isBridging ? <Loader2 className="w-4 h-4 animate-spin mb-1" /> : <Zap className="w-4 h-4 mb-1" />}
                                Run Bridge
                            </button>
                        </div>
                    </div>
                </div>
                {/* Conversations List Header */}
                <div className="flex items-center justify-between text-xs text-gray-500">
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={selectedConvIds.size === conversations.length && conversations.length > 0}
                            onChange={toggleSelectAll}
                            className="rounded"
                        />
                        Select All ({conversations.length})
                    </label>
                    <span>{selectedConvIds.size} selected</span>
                </div>

                {/* Conversations List */}
                <div className="flex-1 overflow-y-auto space-y-1">
                    {conversations.length === 0 ? (
                        <div className="text-center text-gray-500 py-8">
                            <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
                            <p className="text-sm">No conversations yet</p>
                            <p className="text-xs">Import chat history to get started</p>
                        </div>
                    ) : (
                        conversations.map(conv => (
                            <div
                                key={conv.id}
                                className={`p-2 rounded-lg transition-all border ${selectedConvIds.has(conv.id)
                                    ? 'bg-nexus-accent/10 border-nexus-accent/30'
                                    : 'bg-white/5 border-transparent hover:bg-white/10'
                                    }`}
                            >
                                <div className="flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        checked={selectedConvIds.has(conv.id)}
                                        onChange={() => toggleConvSelection(conv.id)}
                                        className="rounded"
                                    />

                                    {editingConvId === conv.id ? (
                                        <input
                                            type="text"
                                            value={editingConvTitle}
                                            onChange={(e) => setEditingConvTitle(e.target.value)}
                                            onBlur={() => handleRenameConversation(conv.id, editingConvTitle)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') handleRenameConversation(conv.id, editingConvTitle);
                                                if (e.key === 'Escape') setEditingConvId(null);
                                            }}
                                            className="flex-1 bg-nexus-700 px-2 py-1 rounded text-sm"
                                            autoFocus
                                        />
                                    ) : (
                                        <span className="flex-1 truncate text-sm">{conv.title}</span>
                                    )}

                                    {/* Harvest Status */}
                                    <span className={`text-xs ${getHarvestStatusColor(conv.harvestStatus)}`}>
                                        {getHarvestStatusIcon(conv.harvestStatus)}
                                    </span>

                                    {/* Message Count */}
                                    <span className="text-xs text-gray-500">{conv.messageCount}</span>

                                    {/* Actions */}
                                    <div className="flex gap-1">
                                        <button
                                            onClick={() => {
                                                setEditingConvId(conv.id);
                                                setEditingConvTitle(conv.title);
                                            }}
                                            className="p-1 hover:bg-white/10 rounded"
                                            title="Edit title"
                                        >
                                            <Edit3 className="w-3 h-3" />
                                        </button>
                                        <button
                                            onClick={() => handleHarvestConversations([conv.id])}
                                            disabled={harvestingConvs}
                                            className="p-1 hover:bg-purple-500/20 rounded group relative"
                                            title="Harvest Agent Memories"
                                        >
                                            🌾
                                        </button>
                                        <button
                                            onClick={() => handleUserHarvest(conv.id)}
                                            disabled={userHarvestingConvId === conv.id}
                                            className="p-1 hover:bg-cyan-500/20 rounded text-cyan-400"
                                            title="Harvest User Twin"
                                        >
                                            {userHarvestingConvId === conv.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <User className="w-3 h-3" />}
                                        </button>
                                        {(conv.harvestStatus === 'harvested' || conv.harvestStatus === 'partially_harvested') && (
                                            <button
                                                onClick={() => setViewingConvId(conv.id)}
                                                className="p-1 hover:bg-blue-500/20 rounded text-blue-400"
                                                title="View harvest results"
                                            >
                                                <Eye className="w-3 h-3" />
                                            </button>
                                        )}
                                        <button
                                            onClick={() => handleDeleteConversation(conv.id)}
                                            className="p-1 hover:bg-red-500/20 rounded text-red-400"
                                            title="Delete"
                                        >
                                            <Trash2 className="w-3 h-3" />
                                        </button>
                                    </div>
                                </div>

                                {/* Date and Harvest Status */}
                                <div className="flex items-center gap-2 mt-1 ml-6">
                                    <span className="text-xs text-gray-500">
                                        {conv.updatedAt.toLocaleDateString()}
                                    </span>
                                    <span className={`text-xs ${conv.harvestStatus === 'harvested' ? 'text-green-400' :
                                        conv.harvestStatus === 'partially_harvested' ? 'text-yellow-400' : 'text-gray-600'
                                        }`}>
                                        {conv.harvestStatus === 'harvested' ? '✅ Harvested' :
                                            conv.harvestStatus === 'partially_harvested' ?
                                                `🟡 Partial (${(conv.lastHarvestedMessageIndex || 0) + 1}/${conv.messageCount})` :
                                                '⭕ Not harvested'}
                                    </span>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Header */}
                <div className="h-16 border-b border-white/5 flex items-center justify-between px-6 bg-nexus-900/30 backdrop-blur-sm">
                    <div className="flex items-center gap-4">
                        <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
                            {selectedEntity?.name}'s Memory
                        </h1>
                        {loading && <RefreshCw className="w-4 h-4 animate-spin text-nexus-accent" />}
                        {meta?.schemaVersion && (
                            <span className="text-xs text-gray-500 font-mono">v{meta.schemaVersion}</span>
                        )}
                    </div>

                    <div className="flex gap-2 bg-nexus-800 p-1 rounded-lg">
                        {(['warm', 'proposals', 'cold'] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-1.5 rounded-md text-sm transition-all flex items-center gap-2 ${activeTab === tab
                                    ? 'bg-nexus-accent text-white shadow-lg shadow-nexus-accent/20'
                                    : 'text-gray-400 hover:text-white'
                                    }`}
                            >
                                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                                {tab === 'proposals' && meta?.pendingProposals && meta.pendingProposals.length > 0 && (
                                    <span className="w-5 h-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center">
                                        {meta.pendingProposals.length}
                                    </span>
                                )}
                            </button>
                        ))}
                    </div>

                    {/* Import Chat Button */}
                    {selectedEntity && selectedEntity.type === 'agent' && (
                        <button
                            onClick={() => setShowImportModal(true)}
                            className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white rounded-lg text-sm flex items-center gap-2 transition-all"
                        >
                            <Upload className="w-4 h-4" />
                            Import Chat
                        </button>
                    )}
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-nexus-accent/20">
                    {/* Empty State / Initialize */}
                    {!loading && !isInitialized && activeTab !== 'cold' && (
                        <div className="flex flex-col items-center justify-center py-20 bg-white/5 rounded-2xl border border-white/5">
                            <div className="p-4 bg-nexus-accent/10 rounded-full mb-4">
                                <Sparkles className="w-8 h-8 text-nexus-accent" />
                            </div>
                            <h3 className="text-xl font-bold text-white mb-2">Memory System Uninitialized</h3>
                            <p className="text-gray-400 max-w-md text-center mb-8">
                                {selectedEntity?.name} hasn't formed any neural pathways yet.
                                Initialize to create the memory structure.
                            </p>
                            <button
                                onClick={handleInitialize}
                                disabled={saving}
                                className="px-6 py-3 bg-nexus-accent text-white rounded-lg font-bold shadow-lg shadow-nexus-accent/20 hover:bg-nexus-accent-hover transition-all flex items-center gap-2"
                            >
                                {saving ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Brain className="w-5 h-5" />}
                                Initialize Memory
                            </button>
                        </div>
                    )}

                    {/* Warm Memory Tab - Hierarchical Banks */}
                    {activeTab === 'warm' && isInitialized && meta && (
                        <div className="space-y-4">
                            {Object.entries(meta.warmBanks || {}).map(([bankName, docNames]) => {
                                if (!Array.isArray(docNames) || docNames.length === 0) return null;
                                const isExpanded = expandedBanks.has(bankName);
                                const colorClass = BANK_COLORS[bankName] || 'text-gray-400 bg-gray-500/10 border-gray-500/20';

                                return (
                                    <div key={bankName} className="border border-white/5 rounded-xl overflow-hidden">
                                        {/* Bank Header */}
                                        <button
                                            onClick={() => toggleBank(bankName)}
                                            className="w-full flex items-center gap-3 p-4 bg-white/5 hover:bg-white/10 transition-colors"
                                        >
                                            {isExpanded ? (
                                                <ChevronDown className="w-4 h-4 text-gray-400" />
                                            ) : (
                                                <ChevronRight className="w-4 h-4 text-gray-400" />
                                            )}
                                            <div className={`p-2 rounded-lg border ${colorClass}`}>
                                                {BANK_ICONS[bankName] || <Database className="w-4 h-4" />}
                                            </div>
                                            <span className="font-bold text-white capitalize">{bankName.replace(/_/g, ' ')}</span>
                                            <span className="text-xs text-gray-500 ml-auto">
                                                {docNames.length} documents
                                            </span>
                                        </button>

                                        {/* Bank Documents */}
                                        {isExpanded && (
                                            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                                                {docNames.map((docName) => {
                                                    const path = `${bankName}/${docName}`;
                                                    const isEditing = editingPath === path;
                                                    // Get content from warmMemory if available
                                                    const content = warmMemory?.[bankName]?.[docName];

                                                    return (
                                                        <div key={docName} className="group bg-nexus-800/40 border border-white/5 rounded-xl overflow-hidden hover:border-nexus-accent/30 transition-all">
                                                            <div className="h-10 px-4 bg-white/5 flex items-center justify-between">
                                                                <div className="flex items-center gap-2">
                                                                    <Activity className="w-3 h-3 text-nexus-accent" />
                                                                    <span className="font-mono text-sm text-gray-300">{docName.replace(/_/g, ' ')}</span>
                                                                </div>
                                                                <button
                                                                    onClick={() => {
                                                                        setEditingPath(path);
                                                                        setEditContent(formatJSON(content || {}));
                                                                    }}
                                                                    className="p-1.5 rounded-lg hover:bg-white/10 text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                                                                >
                                                                    <Edit3 className="w-3.5 h-3.5" />
                                                                </button>
                                                            </div>
                                                            <div className="p-4">
                                                                {isEditing ? (
                                                                    <div className="flex flex-col gap-2">
                                                                        <textarea
                                                                            value={editContent}
                                                                            onChange={(e) => setEditContent(e.target.value)}
                                                                            className="w-full h-48 bg-nexus-900 border border-white/10 rounded-lg p-3 text-xs font-mono text-green-400 focus:outline-none focus:border-nexus-accent/50 resize-none"
                                                                        />
                                                                        <div className="flex justify-end gap-2">
                                                                            <button
                                                                                onClick={() => setEditingPath(null)}
                                                                                className="px-3 py-1.5 text-xs text-gray-400 hover:text-white"
                                                                            >
                                                                                Cancel
                                                                            </button>
                                                                            <button
                                                                                onClick={() => handleSaveDocument(bankName, docName)}
                                                                                disabled={saving}
                                                                                className="px-3 py-1.5 text-xs bg-nexus-accent text-white rounded-md flex items-center gap-1.5 hover:bg-nexus-accent-hover transition-colors"
                                                                            >
                                                                                {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                                                                                Save
                                                                            </button>
                                                                        </div>
                                                                    </div>
                                                                ) : (
                                                                    <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-white/10">
                                                                        {formatJSON(content)}
                                                                    </pre>
                                                                )}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            {/* Add New Type Button */}
                            <button
                                onClick={() => setIsCreatingType(true)}
                                className="w-full flex items-center justify-center gap-3 p-4 border-2 border-dashed border-white/5 rounded-xl hover:border-nexus-accent/40 hover:bg-nexus-accent/5 transition-all group"
                            >
                                <Plus className="w-5 h-5 text-gray-500 group-hover:text-nexus-accent" />
                                <span className="text-gray-500 font-medium group-hover:text-white">Add Custom Memory Type</span>
                            </button>

                            {/* Create Type Modal */}
                            {isCreatingType && (
                                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                                    <div className="bg-nexus-800 border border-white/10 rounded-2xl p-6 w-full max-w-md">
                                        <h3 className="text-lg font-bold mb-4">Create Custom Memory Type</h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-xs uppercase text-gray-500 font-bold mb-1">Bank (Category)</label>
                                                <select
                                                    value={newBankName}
                                                    onChange={(e) => setNewBankName(e.target.value)}
                                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg px-4 py-2 focus:border-nexus-accent/50 focus:outline-none"
                                                >
                                                    <option value="">Select bank...</option>
                                                    {meta?.warmBanks && Object.keys(meta.warmBanks).map(bank => (
                                                        <option key={bank} value={bank}>{bank}</option>
                                                    ))}
                                                    <option value="custom">+ New Bank</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className="block text-xs uppercase text-gray-500 font-bold mb-1">Document Name</label>
                                                <input
                                                    type="text"
                                                    value={newDocName}
                                                    onChange={(e) => setNewDocName(e.target.value)}
                                                    placeholder="e.g., childhood_memories"
                                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg px-4 py-2 focus:border-nexus-accent/50 focus:outline-none"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs uppercase text-gray-500 font-bold mb-1">Description</label>
                                                <input
                                                    type="text"
                                                    value={newDocDesc}
                                                    onChange={(e) => setNewDocDesc(e.target.value)}
                                                    placeholder="What is this memory for?"
                                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg px-4 py-2 focus:border-nexus-accent/50 focus:outline-none"
                                                />
                                            </div>
                                        </div>
                                        <div className="flex justify-end gap-3 mt-6">
                                            <button
                                                onClick={() => setIsCreatingType(false)}
                                                className="px-4 py-2 rounded-lg hover:bg-white/5"
                                            >
                                                Cancel
                                            </button>
                                            <button
                                                onClick={handleCreateType}
                                                disabled={saving || !newBankName || !newDocName}
                                                className="px-4 py-2 bg-nexus-accent rounded-lg text-white font-medium hover:bg-nexus-accent-hover disabled:opacity-50"
                                            >
                                                {saving ? 'Creating...' : 'Create'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Proposals Tab */}
                    {activeTab === 'proposals' && isInitialized && (
                        <div className="space-y-4">
                            {meta?.pendingProposals?.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-20 text-center">
                                    <Check className="w-16 h-16 text-green-500/30 mb-4" />
                                    <h3 className="text-xl font-bold text-gray-400">No Pending Proposals</h3>
                                    <p className="text-gray-500 max-w-md mt-2">
                                        When agents suggest new memory types, they'll appear here for your approval.
                                    </p>
                                </div>
                            ) : (
                                meta?.pendingProposals?.map(proposal => (
                                    <div key={proposal.id} className="bg-white/5 border border-yellow-500/20 rounded-xl p-6">
                                        <div className="flex items-start gap-4">
                                            <div className="p-3 bg-yellow-500/10 rounded-lg">
                                                <AlertCircle className="w-6 h-6 text-yellow-400" />
                                            </div>
                                            <div className="flex-1">
                                                <h3 className="font-bold text-white">{proposal.name}</h3>
                                                <p className="text-gray-400 text-sm mt-1">{proposal.description}</p>
                                                <div className="flex gap-2 mt-2">
                                                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400">
                                                        {proposal.category}
                                                    </span>
                                                    <span className="text-xs text-gray-500">
                                                        Proposed by {proposal.proposedBy}
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => handleResolveProposal(proposal.id, false)}
                                                    disabled={saving}
                                                    className="p-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                                                >
                                                    <X className="w-5 h-5" />
                                                </button>
                                                <button
                                                    onClick={() => handleResolveProposal(proposal.id, true)}
                                                    disabled={saving}
                                                    className="p-2 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors"
                                                >
                                                    <Check className="w-5 h-5" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    )}

                    {/* Cold Memory Tab */}
                    {activeTab === 'cold' && (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            <Database className="w-16 h-16 text-gray-600 mb-4" />
                            <h3 className="text-xl font-bold text-gray-400">Cold Storage Browser</h3>
                            <p className="text-gray-500 max-w-md mt-2">
                                Semantic search interface coming soon. This will allow you to explore Pinecone vector database content.
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* Chat Import Modal */}
            {selectedEntity && (
                <ChatImportModal
                    isOpen={showImportModal}
                    onClose={() => setShowImportModal(false)}
                    agentId={selectedEntity.id}
                    agentName={selectedEntity.name}
                />
            )}

            {/* Per-Conversation Harvest Results Modal */}
            {viewingConvId && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                    <div className="bg-nexus-900 border border-white/10 rounded-xl w-[800px] max-h-[80vh] overflow-hidden shadow-2xl">
                        <ConversationHarvestView
                            conversationId={viewingConvId}
                            onClose={() => setViewingConvId(null)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};
