import React, { useState, useEffect } from 'react';
import { Agent } from '../types';
import {
    getWarmMemory,
    getMemoryRegistry,
    createMemoryType,
    updateMemory,
    initializePersonaMemory,
    MemoryType,
    WarmMemory
} from '../services/memoryService';
import {
    Brain,
    Save,
    Plus,
    ChevronRight,
    Activity,
    Database,
    Clock,
    Settings,
    RefreshCw,
    Trash2,
    Edit3,
    Sparkles
} from 'lucide-react';

interface MemoryManagerProps {
    agents: Agent[];
}

export const MemoryManager: React.FC<MemoryManagerProps> = ({ agents }) => {
    const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
    const [warmMemory, setWarmMemory] = useState<WarmMemory | null>(null);
    const [registry, setRegistry] = useState<MemoryType[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [activeTab, setActiveTab] = useState<'warm' | 'registry' | 'cold'>('warm');
    const [editingType, setEditingType] = useState<string | null>(null);
    const [editContent, setEditContent] = useState<string>('');

    // New Memory Type State
    const [isCreatingType, setIsCreatingType] = useState(false);
    const [newTypeName, setNewTypeName] = useState('');
    const [newTypeDesc, setNewTypeDesc] = useState('');

    const selectedAgent = agents.find(a => a.id === selectedAgentId);

    useEffect(() => {
        if (agents.length > 0 && !selectedAgentId) {
            setSelectedAgentId(agents[0].id);
        }
    }, [agents, selectedAgentId]);

    useEffect(() => {
        if (!selectedAgentId) return;
        loadMemoryData(selectedAgentId);
    }, [selectedAgentId]);

    const loadMemoryData = async (agentId: string) => {
        setLoading(true);
        try {
            const warm = await getWarmMemory(agentId);
            const reg = await getMemoryRegistry(agentId);
            setWarmMemory(warm);
            setRegistry(reg);
        } catch (error) {
            console.error("Failed to load memory data:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleInitialize = async () => {
        if (!selectedAgentId || !selectedAgent) return;
        setSaving(true);
        try {
            await initializePersonaMemory(selectedAgentId, selectedAgent.name);
            await loadMemoryData(selectedAgentId);
        } catch (error) {
            console.error("Failed to initialize memory:", error);
            alert("Failed to initialize memory.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveMemory = async (typeId: string) => {
        if (!selectedAgentId) return;
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

            await updateMemory(selectedAgentId, typeId, contentParsed);

            // Reload specific memory part in local state
            setWarmMemory(prev => prev ? { ...prev, [typeId]: contentParsed } : null);
            setEditingType(null);
        } catch (error) {
            console.error("Failed to save memory:", error);
            alert("Failed to save memory. Check console for details.");
        } finally {
            setSaving(false);
        }
    };

    const handleCreateType = async () => {
        if (!selectedAgentId || !newTypeName) return;
        setSaving(true);
        try {
            await createMemoryType(selectedAgentId, {
                name: newTypeName,
                description: newTypeDesc,
                initialContent: {}
            });
            setIsCreatingType(false);
            setNewTypeName('');
            setNewTypeDesc('');
            loadMemoryData(selectedAgentId); // Reload registry
        } catch (error) {
            console.error("Failed to create type:", error);
            alert("Failed to create memory type.");
        } finally {
            setSaving(false);
        }
    };

    const formatJSON = (data: any) => JSON.stringify(data, null, 2);

    return (
        <div className="flex h-full bg-nexus-900/50 text-gray-200">
            {/* Sidebar - Agent List */}
            <div className="w-64 border-r border-white/5 bg-nexus-900/80 p-4 flex flex-col gap-2">
                <h2 className="text-nexus-accent font-bold mb-4 flex items-center gap-2">
                    <Brain className="w-5 h-5" /> Memory Banks
                </h2>
                {agents.map(agent => (
                    <button
                        key={agent.id}
                        onClick={() => setSelectedAgentId(agent.id)}
                        className={`flex items-center gap-3 p-3 rounded-xl transition-all ${selectedAgentId === agent.id
                            ? 'bg-nexus-accent/20 text-white border border-nexus-accent/30'
                            : 'hover:bg-white/5 text-gray-400'
                            }`}
                    >
                        <div className={`w-2 h-2 rounded-full ${selectedAgentId === agent.id ? 'bg-nexus-accent animate-pulse' : 'bg-gray-600'}`} />
                        <span className="truncate">{agent.name}</span>
                    </button>
                ))}
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col overflow-hidden">

                {/* Header */}
                <div className="h-16 border-b border-white/5 flex items-center justify-between px-6 bg-nexus-900/30 backdrop-blur-sm">
                    <div className="flex items-center gap-4">
                        <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
                            {selectedAgent?.name}'s Neural Network
                        </h1>
                        {loading && <RefreshCw className="w-4 h-4 animate-spin text-nexus-accent" />}
                    </div>

                    <div className="flex gap-2 bg-nexus-800 p-1 rounded-lg">
                        {(['warm', 'registry', 'cold'] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-1.5 rounded-md text-sm transition-all ${activeTab === tab
                                    ? 'bg-nexus-accent text-white shadow-lg shadow-nexus-accent/20'
                                    : 'text-gray-400 hover:text-white'
                                    }`}
                            >
                                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-nexus-accent/20">

                    {/* Empty State / Initialize */}
                    {!loading && activeTab !== 'cold' && (!warmMemory || Object.keys(warmMemory).length === 0) && (
                        <div className="flex flex-col items-center justify-center py-20 bg-white/5 rounded-2xl border border-white/5">
                            <div className="p-4 bg-nexus-accent/10 rounded-full mb-4">
                                <Sparkles className="w-8 h-8 text-nexus-accent" />
                            </div>
                            <h3 className="text-xl font-bold text-white mb-2">Neural Network Uninitialized</h3>
                            <p className="text-gray-400 max-w-md text-center mb-8">
                                {selectedAgent?.name} hasn't formed any neural pathways yet.
                                Initialize the memory system to create the core identity and memory structures.
                            </p>
                            <button
                                onClick={handleInitialize}
                                disabled={saving}
                                className="px-6 py-3 bg-nexus-accent text-white rounded-lg font-bold shadow-lg shadow-nexus-accent/20 hover:bg-nexus-accent-hover transition-all flex items-center gap-2"
                            >
                                {saving ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Brain className="w-5 h-5" />}
                                Initialize Neural Pathways
                            </button>
                        </div>
                    )}

                    {/* Warm Memory Tab */}
                    {activeTab === 'warm' && warmMemory && Object.keys(warmMemory).length > 0 && (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {Object.entries(warmMemory).map(([key, content]) => (
                                <div key={key} className="group bg-nexus-800/40 border border-white/5 rounded-2xl overflow-hidden hover:border-nexus-accent/30 transition-all duration-300">
                                    <div className="h-10 px-4 bg-white/5 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <Activity className="w-4 h-4 text-nexus-accent" />
                                            <span className="font-mono text-sm text-nexus-blue-100">{key}</span>
                                        </div>
                                        <button
                                            onClick={() => {
                                                setEditingType(key);
                                                setEditContent(formatJSON(content));
                                            }}
                                            className="p-1.5 rounded-lg hover:bg-white/10 text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                                        >
                                            <Edit3 className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                    <div className="p-4">
                                        {editingType === key ? (
                                            <div className="flex flex-col gap-2">
                                                <textarea
                                                    value={editContent}
                                                    onChange={(e) => setEditContent(e.target.value)}
                                                    className="w-full h-48 bg-nexus-900 border border-white/10 rounded-lg p-3 text-xs font-mono text-green-400 focus:outline-none focus:border-nexus-accent/50 resize-none"
                                                />
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        onClick={() => setEditingType(null)}
                                                        className="px-3 py-1.5 text-xs text-gray-400 hover:text-white"
                                                    >
                                                        Cancel
                                                    </button>
                                                    <button
                                                        onClick={() => handleSaveMemory(key)}
                                                        disabled={saving}
                                                        className="px-3 py-1.5 text-xs bg-nexus-accent text-white rounded-md flex items-center gap-1.5 hover:bg-nexus-accent-hover transition-colors"
                                                    >
                                                        {saving ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                                                        Save
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap h-48 overflow-y-auto scrollbar-thin scrollbar-thumb-white/10">
                                                {formatJSON(content)}
                                            </pre>
                                        )}
                                    </div>
                                </div>
                            ))}

                            {/* Add New Memory Card */}
                            <button
                                onClick={() => setIsCreatingType(true)}
                                className="flex flex-col items-center justify-center gap-3 h-64 border-2 border-dashed border-white/5 rounded-2xl hover:border-nexus-accent/40 hover:bg-nexus-accent/5 transition-all group"
                            >
                                <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center group-hover:bg-nexus-accent/20 transition-colors">
                                    <Plus className="w-6 h-6 text-gray-500 group-hover:text-nexus-accent" />
                                </div>
                                <span className="text-gray-500 font-medium group-hover:text-white">Create Memory Type</span>
                            </button>
                        </div>
                    )}

                    {/* Registry Tab */}
                    {activeTab === 'registry' && (
                        <div className="space-y-4">
                            {isCreatingType && (
                                <div className="bg-nexus-800/60 border border-nexus-accent/30 rounded-xl p-6 mb-6">
                                    <h3 className="text-lg font-bold mb-4">Create New Memory Type</h3>
                                    <div className="grid grid-cols-2 gap-4 mb-4">
                                        <div>
                                            <label className="block text-xs uppercase text-gray-500 font-bold mb-1">Type ID (key)</label>
                                            <input
                                                type="text"
                                                value={newTypeName}
                                                onChange={(e) => setNewTypeName(e.target.value)}
                                                placeholder="e.g., childhood_memories"
                                                className="w-full bg-nexus-900 border border-white/10 rounded-lg px-4 py-2 focus:border-nexus-accent/50 focus:outline-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs uppercase text-gray-500 font-bold mb-1">Description</label>
                                            <input
                                                type="text"
                                                value={newTypeDesc}
                                                onChange={(e) => setNewTypeDesc(e.target.value)}
                                                placeholder="What is this memory for?"
                                                className="w-full bg-nexus-900 border border-white/10 rounded-lg px-4 py-2 focus:border-nexus-accent/50 focus:outline-none"
                                            />
                                        </div>
                                    </div>
                                    <div className="flex justify-end gap-3">
                                        <button
                                            onClick={() => setIsCreatingType(false)}
                                            className="px-4 py-2 rounded-lg hover:bg-white/5"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            onClick={handleCreateType}
                                            disabled={saving || !newTypeName}
                                            className="px-4 py-2 bg-nexus-accent rounded-lg text-white font-medium hover:bg-nexus-accent-hover disabled:opacity-50"
                                        >
                                            {saving ? 'Creating...' : 'Create Type'}
                                        </button>
                                    </div>
                                </div>
                            )}

                            <div className="space-y-2">
                                <div className="grid grid-cols-12 gap-4 text-xs font-bold text-gray-500 uppercase px-4 pb-2 border-b border-white/5">
                                    <div className="col-span-3">ID</div>
                                    <div className="col-span-4">Description</div>
                                    <div className="col-span-2">Trigger</div>
                                    <div className="col-span-2">Created By</div>
                                    <div className="col-span-1 text-right">Actions</div>
                                </div>
                                {registry.map((type) => (
                                    <div key={type.id} className="grid grid-cols-12 gap-4 items-center bg-white/5 rounded-lg px-4 py-3 hover:bg-white/10 transition-colors">
                                        <div className="col-span-3 font-mono text-nexus-blue-100">{type.id}</div>
                                        <div className="col-span-4 text-gray-400 truncate">{type.description}</div>
                                        <div className="col-span-2">
                                            <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 text-xs border border-blue-500/20">
                                                {type.updateTrigger}
                                            </span>
                                        </div>
                                        <div className="col-span-2 text-gray-500 text-xs capitalize">{type.createdBy}</div>
                                        <div className="col-span-1 text-right">
                                            <button className="text-gray-500 hover:text-red-400">
                                                <Trash2 className="w-4 h-4 ml-auto" />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Cold Memory Tab - Placeholder */}
                    {activeTab === 'cold' && (
                        <div className="flex flex-col items-center justify-center h-64 text-center">
                            <Database className="w-16 h-16 text-gray-600 mb-4" />
                            <h3 className="text-xl font-bold text-gray-400">Cold Storage Browser</h3>
                            <p className="text-gray-500 max-w-md mt-2">
                                Semantic search interface coming soon. This will allow you to explore the Pinecone vector database content.
                            </p>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
};
