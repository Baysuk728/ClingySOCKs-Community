/**
 * Memory Dashboard — Browse, search, and manage relational memory
 * 
 * Four tabs: Overview | Browse | Search | Create
 * Features: inline editing, create/delete items, context toggle
 * Uses the Memory API via memoryApi.ts
 */

import { useState, useEffect, useCallback } from 'react';
import {
    Brain, Search, Database, BarChart3, BookOpen,
    Heart, Shield, Zap, MessageSquare, Star, Clock,
    User, Sparkles, GitBranch, Loader2, RefreshCw,
    Package, AlertCircle, Plus, Pencil, Trash2, Check,
    X, Save, ChevronDown, ChevronUp, Cpu,
} from 'lucide-react';
import {
    getStats, listEntities, recallMemoryDashboard, searchMemoriesDashboard,
    memoryApi,
    type MemoryEntity, type MemoryStats, type RecallItem, type DashboardSearchResult,
} from '../services/memoryApi';

// ── Memory type metadata ──
const MEMORY_TYPE_META: Record<string, { label: string; icon: typeof Brain; color: string }> = {
    lexicon: { label: 'Lexicon', icon: BookOpen, color: '#a78bfa' },
    life_events: { label: 'Life Events', icon: Star, color: '#fbbf24' },
    artifacts: { label: 'Artifacts', icon: Package, color: '#60a5fa' },
    emotional_patterns: { label: 'Emotional Patterns', icon: Heart, color: '#f472b6' },
    repair_patterns: { label: 'Repair Patterns', icon: Shield, color: '#34d399' },
    state_needs: { label: 'State Needs', icon: Zap, color: '#fb923c' },
    permissions: { label: 'Permissions', icon: Shield, color: '#a3e635' },
    unresolved_threads: { label: 'Unresolved Threads', icon: AlertCircle, color: '#f87171' },
    narratives: { label: 'Narratives', icon: MessageSquare, color: '#818cf8' },
    echo_dreams: { label: 'Echo Dreams', icon: Sparkles, color: '#c084fc' },
    rituals: { label: 'Rituals', icon: Clock, color: '#2dd4bf' },
    user_profiles: { label: 'User Profile', icon: User, color: '#38bdf8' },
    inside_jokes: { label: 'Inside Jokes', icon: MessageSquare, color: '#fcd34d' },
    intimate_moments: { label: 'Intimate Moments', icon: Heart, color: '#fb7185' },
    relationships: { label: 'Relationships', icon: GitBranch, color: '#f97316' },
    memory_blocks: { label: 'Memory Blocks', icon: Database, color: '#06b6d4' },
};

// Types that support write operations
const WRITABLE_TYPES = new Set([
    'lexicon', 'inside_jokes', 'life_events', 'permissions', 'rituals',
    'unresolved_threads', 'narratives', 'memory_blocks', 'echo_dreams',
]);

// Fields for creating/editing each type
const TYPE_FIELDS: Record<string, { key: string; label: string; multiline?: boolean; required?: boolean }[]> = {
    lexicon:              [{ key: 'term', label: 'Term', required: true }, { key: 'definition', label: 'Definition', multiline: true, required: true }, { key: 'origin', label: 'Origin' }],
    inside_jokes:         [{ key: 'phrase', label: 'Phrase', required: true }, { key: 'origin', label: 'Origin / Story', multiline: true }, { key: 'punchline', label: 'Punchline' }],
    life_events:          [{ key: 'title', label: 'Title', required: true }, { key: 'narrative', label: 'Narrative', multiline: true, required: true }, { key: 'date', label: 'Date' }],
    permissions:          [{ key: 'permission', label: 'Permission', required: true }, { key: 'context', label: 'Context', multiline: true }],
    rituals:              [{ key: 'name', label: 'Name', required: true }, { key: 'description', label: 'Description', multiline: true }, { key: 'trigger', label: 'Trigger' }],
    unresolved_threads:   [{ key: 'thread', label: 'Thread', required: true }, { key: 'summary', label: 'Summary', multiline: true }],
    narratives:           [{ key: 'title', label: 'Title', required: true }, { key: 'narrative', label: 'Narrative', multiline: true, required: true }],
    memory_blocks:        [{ key: 'title', label: 'Title', required: true }, { key: 'content', label: 'Content', multiline: true, required: true }],
    echo_dreams:          [{ key: 'title', label: 'Title', required: true }, { key: 'whisper', label: 'Whisper / Content', multiline: true }],
};

// ── Serializers ──
function getItemTitle(type: string, item: RecallItem): string {
    return item.term || item.title || item.name || item.phrase || item.thread || item.state || item.permission || `${type} #${item.id || '?'}`;
}

function getItemBody(type: string, item: RecallItem): string {
    return item.definition || item.narrative || item.summary || item.description || item.pattern || item.need || item.origin || item.whisper || item.content || JSON.stringify(item, null, 2).slice(0, 300);
}

interface Props {
    agents?: { id: string; name: string }[];
    currentUserId?: string;
}

type Tab = 'overview' | 'browse' | 'search' | 'create';

export function MemoryDashboard({ agents, currentUserId }: Props) {
    const [entities, setEntities] = useState<MemoryEntity[]>([]);
    const [selectedEntity, setSelectedEntity] = useState<MemoryEntity | null>(null);
    const [stats, setStats] = useState<MemoryStats | null>(null);
    const [statsLoading, setStatsLoading] = useState(false);
    const [activeTab, setActiveTab] = useState<Tab>('overview');

    // Browse
    const [browseType, setBrowseType] = useState('lexicon');
    const [browseItems, setBrowseItems] = useState<RecallItem[]>([]);
    const [browseLoading, setBrowseLoading] = useState(false);
    const [browseQuery, setBrowseQuery] = useState('');

    // Search
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<DashboardSearchResult[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [searchSubmitted, setSearchSubmitted] = useState(false);

    // Toast
    const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);
    const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 3000);
    };

    // Load entities
    useEffect(() => {
        listEntities().then(data => {
            const entityList = Array.isArray(data) ? data : [];
            setEntities(entityList);
            if (entityList.length > 0) setSelectedEntity(entityList[0]);
        }).catch(console.error);
    }, []);

    // Load stats on entity change
    useEffect(() => {
        if (!selectedEntity) return;
        setStatsLoading(true);
        getStats(selectedEntity.id)
            .then(setStats)
            .catch(console.error)
            .finally(() => setStatsLoading(false));
    }, [selectedEntity]);

    // Browse: load items
    const loadBrowseItems = useCallback(async () => {
        if (!selectedEntity) return;
        setBrowseLoading(true);
        try {
            const items = await recallMemoryDashboard(selectedEntity.id, browseType, browseQuery || undefined, 'all', 30);
            setBrowseItems(Array.isArray(items) ? items : []);
        } catch (e) { console.error(e); setBrowseItems([]); }
        finally { setBrowseLoading(false); }
    }, [selectedEntity, browseType, browseQuery]);

    useEffect(() => {
        if (activeTab === 'browse') loadBrowseItems();
    }, [activeTab, browseType, selectedEntity]);

    // Search
    const handleSearch = async () => {
        if (!selectedEntity || !searchQuery.trim()) return;
        setSearchLoading(true);
        setSearchSubmitted(true);
        try {
            const results = await searchMemoriesDashboard(selectedEntity.id, searchQuery.trim());
            setSearchResults(Array.isArray(results) ? results : []);
        } catch (e) { console.error(e); setSearchResults([]); }
        finally { setSearchLoading(false); }
    };

    const refreshStats = () => {
        if (!selectedEntity) return;
        setStatsLoading(true);
        getStats(selectedEntity.id)
            .then(setStats)
            .catch(console.error)
            .finally(() => setStatsLoading(false));
    };

    // Write/update/resolve handler
    const handleWrite = async (type: string, data: Record<string, any>, action: 'create' | 'update' | 'resolve' = 'create') => {
        if (!selectedEntity) return;
        try {
            await memoryApi.write(selectedEntity.id, type, data, action);
            showToast(`Memory item ${action}d successfully!`);
            // Refresh browse if on browse tab
            if (activeTab === 'browse' && browseType === type) loadBrowseItems();
            refreshStats();
        } catch (e: any) {
            showToast(e?.message || 'Write failed', 'error');
        }
    };

    const [harvestLoading, setHarvestLoading] = useState(false);

    // Progress tracking
    const [harvestStatus, setHarvestStatus] = useState<any>(null);
    const [isHarvesting, setIsHarvesting] = useState(false);

    useEffect(() => {
        if (!isHarvesting || !selectedEntity) return;

        const interval = setInterval(async () => {
            try {
                const data = await memoryApi.getHarvestProgress(selectedEntity.id);
                setHarvestStatus(data);
                if (data.status === 'complete' || data.status === 'error' || data.status === 'idle') {
                    if (data.status === 'complete') {
                        showToast('Harvest complete!');
                        refreshStats();
                    } else if (data.status === 'error') {
                        showToast(data.error_message || 'Harvest failed', 'error');
                    }
                    setIsHarvesting(false);
                }
            } catch (e) {
                console.error('Failed to fetch harvest progress', e);
            }
        }, 3000);

        return () => clearInterval(interval);
    }, [isHarvesting, selectedEntity]);

    const handleHarvest = async () => {
        if (!selectedEntity || harvestLoading) return;
        setHarvestLoading(true);
        try {
            await memoryApi.triggerHarvest(selectedEntity.id);
            setIsHarvesting(true);
            setHarvestStatus({ status: 'processing', progress_percent: 5, current_step: 'Initializing...' });
            showToast('Harvest started');
        } catch (e: any) {
            const errorMsg = e?.response?.data?.detail || e?.message || 'Failed to start harvest';
            showToast(errorMsg, 'error');
        } finally {
            setHarvestLoading(false);
        }
    };

    const totalItems = stats ? Object.values(stats.counts).reduce((a, b) => a + b, 0) : 0;

    return (
        <div className="h-full overflow-y-auto p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                        <Brain className="w-7 h-7 text-nexus-accent" />
                        Memory Dashboard
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">Browse, search, and manage relational memory</p>
                </div>
                <div className="flex items-center gap-2">
                    {selectedEntity && (
                        <button
                            onClick={handleHarvest}
                            disabled={harvestLoading || isHarvesting}
                            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-nexus-accent/10 border border-nexus-accent/30 text-nexus-accent text-sm font-medium hover:bg-nexus-accent/20 transition-all disabled:opacity-50"
                            title={`Run harvest for ${selectedEntity.name}`}
                        >
                            {isHarvesting ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                                <Cpu className={`w-4 h-4 ${harvestLoading ? 'animate-pulse' : ''}`} />
                            )}
                            {isHarvesting ? `${harvestStatus?.progress_percent || 0}%` : (harvestLoading ? 'Starting…' : 'Harvest')}
                        </button>
                    )}
                    <button
                        onClick={refreshStats}
                        disabled={statsLoading}
                        className="p-2 rounded-lg bg-nexus-900/50 border border-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-all disabled:opacity-50"
                    >
                        <RefreshCw className={`w-4 h-4 ${statsLoading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Entity Selector */}
            {entities.length > 1 && (
                <div className="flex gap-2 flex-wrap">
                    {entities.map(e => (
                        <button
                            key={e.id}
                            onClick={() => { setSelectedEntity(e); setBrowseItems([]); setSearchResults([]); setSearchSubmitted(false); setIsHarvesting(false); }}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all
                                ${selectedEntity?.id === e.id
                                    ? 'bg-nexus-accent/20 text-nexus-accent border border-nexus-accent/30'
                                    : 'bg-nexus-900/50 text-gray-400 border border-white/5 hover:bg-white/5'
                                }`}
                        >
                            <Database className="w-3 h-3" />
                            {e.name}
                        </button>
                    ))}
                </div>
            )}

            {/* Live Progress Bar */}
            {isHarvesting && (
                <div className="bg-nexus-900/50 border border-nexus-accent/20 rounded-xl p-4 space-y-3 animate-in slide-in-from-top-2">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-nexus-accent animate-pulse" />
                            <span className="text-sm font-semibold text-white">Harvesting Knowledge...</span>
                        </div>
                        <span className="text-xs font-mono text-nexus-accent">{harvestStatus?.progress_percent}%</span>
                    </div>
                    
                    <div className="h-2 w-full bg-nexus-900 rounded-full overflow-hidden border border-white/5">
                        <div 
                            className="h-full bg-nexus-accent transition-all duration-500 ease-out shadow-[0_0_10px_rgba(0,242,255,0.5)]"
                            style={{ width: `${harvestStatus?.progress_percent}%` }}
                        />
                    </div>

                    <div className="flex items-center justify-between text-[11px]">
                        <div className="text-gray-400 flex items-center gap-1">
                            <Sparkles size={12} className="text-nexus-accent" />
                            {harvestStatus?.current_step || 'Processing...'}
                        </div>
                        {harvestStatus?.total_chunks > 0 && (
                            <div className="text-gray-500">
                                Chunk {harvestStatus?.completed_chunks} / {harvestStatus?.total_chunks}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="flex gap-1 bg-nexus-900/50 border border-white/5 rounded-xl p-1">
                {(['overview', 'browse', 'search', 'create'] as Tab[]).map(tab => {
                    const Icon = tab === 'overview' ? BarChart3 : tab === 'browse' ? BookOpen : tab === 'create' ? Plus : Search;
                    return (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all flex-1 justify-center
                                ${activeTab === tab
                                    ? 'bg-nexus-accent/10 text-nexus-accent'
                                    : 'text-gray-500 hover:text-white hover:bg-white/5'
                                }`}
                        >
                            <Icon className="w-4 h-4" />
                            {tab.charAt(0).toUpperCase() + tab.slice(1)}
                        </button>
                    );
                })}
            </div>

            {/* Toast notification */}
            {toast && (
                <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg text-sm font-medium shadow-lg transition-all
                    ${toast.type === 'success' ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'}`}>
                    {toast.msg}
                </div>
            )}

            {/* Tab Content */}
            {activeTab === 'overview' && (
                <OverviewTab stats={stats} loading={statsLoading} totalItems={totalItems} />
            )}
            {activeTab === 'browse' && (
                <BrowseTab
                    stats={stats}
                    browseType={browseType}
                    setBrowseType={setBrowseType}
                    items={browseItems}
                    loading={browseLoading}
                    query={browseQuery}
                    setQuery={setBrowseQuery}
                    onSearch={loadBrowseItems}
                    onWrite={handleWrite}
                />
            )}
            {activeTab === 'search' && (
                <SearchTab
                    query={searchQuery}
                    setQuery={setSearchQuery}
                    results={searchResults}
                    loading={searchLoading}
                    submitted={searchSubmitted}
                    onSearch={handleSearch}
                />
            )}
            {activeTab === 'create' && selectedEntity && (
                <CreateTab entityId={selectedEntity.id} onWrite={handleWrite} />
            )}
        </div>
    );
}

// ═══════════════════════════════════════════════════════
// Overview Tab
// ═══════════════════════════════════════════════════════

function OverviewTab({ stats, loading, totalItems }: { stats: MemoryStats | null; loading: boolean; totalItems: number }) {
    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center py-20 text-gray-500">
                <Loader2 className="w-8 h-8 animate-spin mb-3" />
                <p>Loading stats...</p>
            </div>
        );
    }

    if (!stats) {
        return (
            <div className="flex flex-col items-center justify-center py-20 text-gray-500">
                <Database className="w-10 h-10 mb-3" />
                <p>Select an entity to view memory stats</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-in fade-in">
            {/* Top stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-white">{totalItems.toLocaleString()}</div>
                    <div className="text-xs text-gray-500 mt-1">Total Items</div>
                </div>
                <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-white">{stats.embedding_count.toLocaleString()}</div>
                    <div className="text-xs text-gray-500 mt-1">Embeddings</div>
                </div>
                <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-white">{Object.keys(stats.counts).length}</div>
                    <div className="text-xs text-gray-500 mt-1">Memory Types</div>
                </div>
                <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 text-center">
                    <div className="text-sm font-medium text-gray-300">
                        {stats.last_harvest ? new Date(stats.last_harvest).toLocaleDateString() : '—'}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">Last Harvest</div>
                </div>
            </div>

            {/* Per-type grid */}
            <div>
                <h3 className="text-sm font-semibold text-gray-400 mb-3">Memory Types</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {Object.entries(stats.counts)
                        .sort(([, a], [, b]) => b - a)
                        .map(([type, count]) => {
                            const meta = MEMORY_TYPE_META[type] || { label: type, icon: Database, color: '#94a3b8' };
                            const Icon = meta.icon;
                            return (
                                <div key={type} className="bg-nexus-900/50 border border-white/5 rounded-xl p-3 flex items-center gap-3 hover:bg-white/5 transition-all">
                                    <div
                                        className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                                        style={{ background: `${meta.color}15`, border: `1px solid ${meta.color}30` }}
                                    >
                                        <Icon size={16} style={{ color: meta.color }} />
                                    </div>
                                    <div className="min-w-0">
                                        <div className="text-lg font-bold text-white">{count.toLocaleString()}</div>
                                        <div className="text-[10px] text-gray-500 uppercase tracking-wider truncate">{meta.label}</div>
                                    </div>
                                </div>
                            );
                        })}
                </div>
            </div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════
// Browse Tab
// ═══════════════════════════════════════════════════════

function BrowseTab({
    stats, browseType, setBrowseType, items, loading, query, setQuery, onSearch, onWrite,
}: {
    stats: MemoryStats | null;
    browseType: string;
    setBrowseType: (t: string) => void;
    items: RecallItem[];
    loading: boolean;
    query: string;
    setQuery: (q: string) => void;
    onSearch: () => void;
    onWrite: (type: string, data: Record<string, any>, action: 'create' | 'update' | 'resolve') => Promise<void>;
}) {
    const types = stats ? Object.keys(stats.counts).filter(t => stats.counts[t] > 0) : [];
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editData, setEditData] = useState<Record<string, string>>({});
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const isWritable = WRITABLE_TYPES.has(browseType);

    const startEdit = (item: RecallItem) => {
        const fields = TYPE_FIELDS[browseType] || [];
        const data: Record<string, string> = {};
        for (const f of fields) data[f.key] = item[f.key] || '';
        if (item.id) data['id'] = item.id;
        setEditData(data);
        setEditingId(item.id || null);
    };

    const saveEdit = async () => {
        setSaving(true);
        try {
            await onWrite(browseType, editData, 'update');
            setEditingId(null);
        } finally { setSaving(false); }
    };

    const resolveItem = async (item: RecallItem) => {
        const id = item.id;
        if (!id) return;
        await onWrite(browseType, { id, status: 'resolved' }, 'resolve');
    };

    return (
        <div className="space-y-4 animate-in fade-in">
            {/* Controls */}
            <div className="flex gap-3 flex-wrap">
                <select
                    value={browseType}
                    onChange={e => setBrowseType(e.target.value)}
                    className="bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-nexus-accent outline-none min-w-[200px]"
                >
                    {types.map(t => {
                        const meta = MEMORY_TYPE_META[t];
                        return <option key={t} value={t}>{meta?.label || t} ({stats!.counts[t]})</option>;
                    })}
                </select>

                <div className="flex-1 flex gap-2 min-w-[200px]">
                    <div className="flex-1 relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                        <input
                            className="w-full bg-nexus-900 border border-white/10 rounded-lg pl-10 pr-3 py-2 text-sm text-white focus:border-nexus-accent outline-none"
                            placeholder="Filter items..."
                            value={query}
                            onChange={e => setQuery(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && onSearch()}
                        />
                    </div>
                    <button
                        onClick={onSearch}
                        disabled={loading}
                        className="px-4 py-2 rounded-lg bg-nexus-900 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-all text-sm disabled:opacity-50"
                    >
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Filter'}
                    </button>
                </div>
            </div>

            {/* Items */}
            {loading ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                    <Loader2 className="w-8 h-8 animate-spin mb-3" />
                    <p>Loading {MEMORY_TYPE_META[browseType]?.label || browseType}...</p>
                </div>
            ) : items.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                    <BookOpen className="w-10 h-10 mb-3" />
                    <p>No items found</p>
                </div>
            ) : (
                <div className="space-y-2">
                    <div className="text-xs text-gray-500 flex items-center justify-between">
                        <span>{items.length} items</span>
                        {isWritable && <span className="text-nexus-accent/50 text-[10px]">Click item to expand &bull; Edit inline</span>}
                    </div>
                    {items.map((item, i) => {
                        const meta = MEMORY_TYPE_META[browseType];
                        const Icon = meta?.icon || Database;
                        const isEditing = editingId === item.id;
                        const isExpanded = expandedId === item.id;
                        const fields = TYPE_FIELDS[browseType] || [];

                        return (
                            <div key={item.id || i} className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 hover:bg-white/5 transition-all group">
                                {/* Header row */}
                                <div className="flex items-center gap-2 mb-1">
                                    {meta && <Icon size={14} style={{ color: meta.color }} />}
                                    <div
                                        className="text-sm font-semibold text-white flex-1 cursor-pointer"
                                        onClick={() => setExpandedId(isExpanded ? null : (item.id || null))}
                                    >
                                        {getItemTitle(browseType, item)}
                                    </div>
                                    {/* Action buttons */}
                                    {isWritable && !isEditing && (
                                        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button
                                                onClick={() => startEdit(item)}
                                                className="p-1 rounded hover:bg-white/10 text-gray-400 hover:text-white"
                                                title="Edit"
                                            >
                                                <Pencil size={12} />
                                            </button>
                                            {item.status === 'active' && (
                                                <button
                                                    onClick={() => resolveItem(item)}
                                                    className="p-1 rounded hover:bg-green-500/20 text-gray-400 hover:text-green-400"
                                                    title="Resolve"
                                                >
                                                    <Check size={12} />
                                                </button>
                                            )}
                                        </div>
                                    )}
                                    <button
                                        onClick={() => setExpandedId(isExpanded ? null : (item.id || null))}
                                        className="p-1 text-gray-500"
                                    >
                                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                    </button>
                                </div>

                                {/* Inline edit form */}
                                {isEditing ? (
                                    <div className="mt-2 space-y-2 bg-nexus-900/80 rounded-lg p-3 border border-nexus-accent/20">
                                        {fields.map(f => (
                                            <div key={f.key}>
                                                <label className="text-[10px] text-gray-500 uppercase">{f.label}</label>
                                                {f.multiline ? (
                                                    <textarea
                                                        value={editData[f.key] || ''}
                                                        onChange={e => setEditData(prev => ({ ...prev, [f.key]: e.target.value }))}
                                                        className="w-full bg-nexus-900 border border-white/10 rounded px-2 py-1 text-xs text-white mt-0.5 min-h-[60px] outline-none focus:border-nexus-accent"
                                                    />
                                                ) : (
                                                    <input
                                                        value={editData[f.key] || ''}
                                                        onChange={e => setEditData(prev => ({ ...prev, [f.key]: e.target.value }))}
                                                        className="w-full bg-nexus-900 border border-white/10 rounded px-2 py-1 text-xs text-white mt-0.5 outline-none focus:border-nexus-accent"
                                                    />
                                                )}
                                            </div>
                                        ))}
                                        <div className="flex gap-2 justify-end">
                                            <button
                                                onClick={() => setEditingId(null)}
                                                className="px-3 py-1 rounded text-xs text-gray-400 hover:text-white hover:bg-white/10"
                                            >
                                                <X size={12} className="inline mr-1" /> Cancel
                                            </button>
                                            <button
                                                onClick={saveEdit}
                                                disabled={saving}
                                                className="px-3 py-1 rounded text-xs bg-nexus-accent/20 text-nexus-accent hover:bg-nexus-accent/30 disabled:opacity-50"
                                            >
                                                {saving ? <Loader2 size={12} className="inline mr-1 animate-spin" /> : <Save size={12} className="inline mr-1" />}
                                                Save
                                            </button>
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        <div className="text-xs text-gray-400 line-clamp-3">
                                            {getItemBody(browseType, item)}
                                        </div>
                                        {/* Expanded view: all fields */}
                                        {isExpanded && (
                                            <div className="mt-2 pt-2 border-t border-white/5 space-y-1">
                                                {Object.entries(item)
                                                    .filter(([k]) => !['id', 'entity_id'].includes(k))
                                                    .map(([k, v]) => (
                                                        <div key={k} className="flex gap-2 text-[11px]">
                                                            <span className="text-gray-500 min-w-[100px] shrink-0">{k}:</span>
                                                            <span className="text-gray-300 break-all">
                                                                {typeof v === 'object' ? JSON.stringify(v) : String(v ?? '')}
                                                            </span>
                                                        </div>
                                                    ))}
                                            </div>
                                        )}
                                    </>
                                )}

                                {/* Status badges */}
                                {!isEditing && (
                                    <div className="flex items-center gap-2 mt-2">
                                        {item.status && (
                                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium
                                                ${item.status === 'active' ? 'bg-green-500/20 text-green-400'
                                                    : item.status === 'resolved' ? 'bg-nexus-accent/20 text-nexus-accent'
                                                        : 'bg-yellow-500/20 text-yellow-400'}`}
                                            >
                                                {item.status}
                                            </span>
                                        )}
                                        {item.lore_score != null && (
                                            <span className="text-[10px] text-gray-500">Score: {item.lore_score}</span>
                                        )}
                                        {item.created_at && (
                                            <span className="text-[10px] text-gray-500">{new Date(item.created_at).toLocaleDateString()}</span>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ═══════════════════════════════════════════════════════
// Search Tab
// ═══════════════════════════════════════════════════════

function SearchTab({
    query, setQuery, results, loading, submitted, onSearch,
}: {
    query: string;
    setQuery: (q: string) => void;
    results: DashboardSearchResult[];
    loading: boolean;
    submitted: boolean;
    onSearch: () => void;
}) {
    return (
        <div className="space-y-4 animate-in fade-in">
            {/* Search input */}
            <div className="flex gap-3">
                <div className="flex-1 relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                    <input
                        className="w-full bg-nexus-900 border border-white/10 rounded-lg pl-10 pr-3 py-3 text-sm text-white focus:border-nexus-accent outline-none"
                        placeholder="Search memories... (e.g., 'birthday', 'fear of abandonment', 'first date')"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && onSearch()}
                    />
                </div>
                <button
                    onClick={onSearch}
                    disabled={loading || !query.trim()}
                    className="px-5 py-3 rounded-lg bg-nexus-accent text-nexus-900 font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.3)] transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Search'}
                </button>
            </div>

            {/* Results */}
            {loading ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                    <Loader2 className="w-8 h-8 animate-spin mb-3" />
                    <p>Searching memories...</p>
                </div>
            ) : !submitted ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                    <Search className="w-10 h-10 mb-3" />
                    <p>Enter a query to search across all memory types</p>
                    <p className="text-xs mt-1 text-gray-600">Uses semantic similarity when embeddings are enabled</p>
                </div>
            ) : results.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                    <AlertCircle className="w-10 h-10 mb-3" />
                    <p>No results found for "{query}"</p>
                </div>
            ) : (
                <div className="space-y-2">
                    <div className="text-xs text-gray-500">{results.length} results</div>
                    {results.map((result, i) => {
                        const meta = MEMORY_TYPE_META[result.type];
                        const Icon = meta?.icon || Database;
                        return (
                            <div key={i} className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 hover:bg-white/5 transition-all">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        {meta && <Icon size={14} style={{ color: meta.color }} />}
                                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-nexus-accent/20 text-nexus-accent font-medium">
                                            {meta?.label || result.type}
                                        </span>
                                    </div>
                                    {result.similarity != null && (
                                        <div className="flex items-center gap-2">
                                            <span className="text-[10px] text-gray-500">
                                                {(result.similarity * 100).toFixed(0)}%
                                            </span>
                                            <div className="w-16 h-1.5 bg-nexus-900 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-nexus-accent rounded-full transition-all"
                                                    style={{ width: `${result.similarity * 100}%` }}
                                                />
                                            </div>
                                        </div>
                                    )}
                                </div>
                                <div className="text-sm font-semibold text-white mb-1">
                                    {getItemTitle(result.type, result)}
                                </div>
                                <div className="text-xs text-gray-400 line-clamp-3">
                                    {getItemBody(result.type, result)}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ═══════════════════════════════════════════════════════
// Create Tab
// ═══════════════════════════════════════════════════════

function CreateTab({
    entityId,
    onWrite,
}: {
    entityId: string;
    onWrite: (type: string, data: Record<string, any>, action: 'create' | 'update' | 'resolve') => Promise<void>;
}) {
    const writableTypes = Array.from(WRITABLE_TYPES);
    const [createType, setCreateType] = useState(writableTypes[0]);
    const [formData, setFormData] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    const [success, setSuccess] = useState(false);

    const fields = TYPE_FIELDS[createType] || [];

    const resetForm = () => {
        setFormData({});
        setSuccess(false);
    };

    useEffect(() => { resetForm(); }, [createType]);

    const handleCreate = async () => {
        for (const f of fields) {
            if (f.required && !formData[f.key]?.trim()) return;
        }
        setSaving(true);
        try {
            await onWrite(createType, formData, 'create');
            setSuccess(true);
            setTimeout(() => { resetForm(); }, 1500);
        } finally { setSaving(false); }
    };

    const meta = MEMORY_TYPE_META[createType];
    const Icon = meta?.icon || Database;

    return (
        <div className="space-y-4 animate-in fade-in max-w-2xl mx-auto">
            <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-6">
                <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                    <Plus size={16} className="text-nexus-accent" />
                    Create Memory Item
                </h3>

                {/* Type selector */}
                <div className="mb-5">
                    <label className="text-xs text-gray-500 uppercase block mb-2">Memory Type</label>
                    <div className="flex flex-wrap gap-2">
                        {writableTypes.map(t => {
                            const m = MEMORY_TYPE_META[t];
                            const I = m?.icon || Database;
                            return (
                                <button
                                    key={t}
                                    onClick={() => setCreateType(t)}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all
                                        ${createType === t
                                            ? 'bg-nexus-accent/15 text-nexus-accent border border-nexus-accent/30'
                                            : 'bg-nexus-900 text-gray-400 border border-white/5 hover:bg-white/5'
                                        }`}
                                >
                                    <I size={12} style={{ color: m?.color }} />
                                    {m?.label || t}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Fields */}
                <div className="space-y-3">
                    {fields.map(f => (
                        <div key={f.key}>
                            <label className="text-xs text-gray-400 flex items-center gap-1 mb-1">
                                {f.label}
                                {f.required && <span className="text-red-400">*</span>}
                            </label>
                            {f.multiline ? (
                                <textarea
                                    value={formData[f.key] || ''}
                                    onChange={e => setFormData(prev => ({ ...prev, [f.key]: e.target.value }))}
                                    placeholder={`Enter ${f.label.toLowerCase()}...`}
                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white min-h-[80px] outline-none focus:border-nexus-accent transition-colors"
                                />
                            ) : (
                                <input
                                    value={formData[f.key] || ''}
                                    onChange={e => setFormData(prev => ({ ...prev, [f.key]: e.target.value }))}
                                    placeholder={`Enter ${f.label.toLowerCase()}...`}
                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-nexus-accent transition-colors"
                                />
                            )}
                        </div>
                    ))}
                </div>

                {/* Submit */}
                <div className="flex items-center justify-end gap-3 mt-5">
                    {success && (
                        <span className="text-green-400 text-xs flex items-center gap-1">
                            <Check size={12} /> Created!
                        </span>
                    )}
                    <button
                        onClick={resetForm}
                        className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/10 transition-all"
                    >
                        Reset
                    </button>
                    <button
                        onClick={handleCreate}
                        disabled={saving || fields.some(f => f.required && !formData[f.key]?.trim())}
                        className="px-5 py-2 rounded-lg text-sm bg-nexus-accent text-nexus-900 font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.3)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                        {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                        Create {meta?.label || createType}
                    </button>
                </div>
            </div>

            <div className="text-xs text-gray-500 text-center">
                Created items will appear in the Browse tab and become part of warm memory after next harvest.
            </div>
        </div>
    );
}