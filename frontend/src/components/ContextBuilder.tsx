/**
 * Context Builder — Visual context window manager
 * 
 * Split-pane layout:
 *  Left: Draggable section list with toggles + budget bars
 *  Right: Live context preview (formatted output)
 * 
 * Features:
 *  - Drag-and-drop section reordering
 *  - Per-section enable/disable toggles
 *  - Budget visualization (char count bars)
 *  - Click-to-expand section content editing
 *  - Live preview of assembled context
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
    Layers, Eye, EyeOff, GripVertical, ChevronDown, ChevronRight,
    Save, RefreshCw, Loader2, BarChart3, FileText, Clock,
    Maximize2, Minimize2, Settings2, Zap, Wrench, Cpu, Pin, MessageSquare,
} from 'lucide-react';
import {
    getContextPreview, updateSectionConfig, updateBudgetConfig,
    type ContextPreview, type SectionInfo, type ComponentSummary, type BudgetLimits,
} from '../services/contextApi';
import { listEntities, type MemoryEntity } from '../services/memoryApi';

// ── Color mapping for section types ──
const SECTION_COLORS: Record<string, string> = {
    persona: '#a78bfa',
    user_profile: '#38bdf8',
    session_bridge: '#fbbf24',
    recent_narrative: '#818cf8',
    active_threads: '#f87171',
    lexicon: '#a78bfa',
    permissions: '#a3e635',
    memory_blocks: '#06b6d4',
    relationship: '#f97316',
    mythology: '#34d399',
    seasonal_narrative: '#60a5fa',
    lifetime_narrative: '#c084fc',
    state_needs: '#fb923c',
    repair_patterns: '#34d399',
    emotional_patterns: '#f472b6',
    recent_events: '#fbbf24',
    echo_dream: '#c084fc',
    inside_jokes: '#fcd34d',
    intimate_moments: '#fb7185',
    rituals: '#2dd4bf',
    artifacts: '#60a5fa',
};

interface Props {
    agents?: { id: string; name: string }[];
}

// ── Cache tag badge ──
const CACHE_TAG_COLORS = {
    stable: { bg: 'rgba(167,139,250,0.15)', text: '#a78bfa' },
    cacheable: { bg: 'rgba(52,211,153,0.15)', text: '#34d399' },
    volatile: { bg: 'rgba(251,191,36,0.15)', text: '#fbbf24' },
} as const;

function CacheTag({ tag }: { tag: 'stable' | 'cacheable' | 'volatile' }) {
    const colors = CACHE_TAG_COLORS[tag];
    return (
        <span style={{
            fontSize: 9, padding: '1px 5px', borderRadius: 3,
            background: colors.bg, color: colors.text,
        }}>
            {tag}
        </span>
    );
}

export function ContextBuilder({ agents }: Props) {
    const [entities, setEntities] = useState<MemoryEntity[]>([]);
    const [selectedEntity, setSelectedEntity] = useState<MemoryEntity | null>(null);
    const [preview, setPreview] = useState<ContextPreview | null>(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [expandedSection, setExpandedSection] = useState<string | null>(null);
    const [showPreview, setShowPreview] = useState(true);
    const [previewMode, setPreviewMode] = useState<'structured' | 'raw'>('structured');
    const [draggedKey, setDraggedKey] = useState<string | null>(null);
    const [dragOverKey, setDragOverKey] = useState<string | null>(null);
    const [hasChanges, setHasChanges] = useState(false);

    // Local section state (for drag-and-drop reordering + toggles before save)
    const [localSections, setLocalSections] = useState<SectionInfo[]>([]);
    const [disabledSections, setDisabledSections] = useState<string[]>([]);
    const [disabledItems, setDisabledItems] = useState<Record<string, string[]>>({});
    const [pinnedItems, setPinnedItems] = useState<Record<string, string[]>>({});
    const [voiceAnchors, setVoiceAnchors] = useState<any[] | null>(null);
    const [isEditingVoiceAnchors, setIsEditingVoiceAnchors] = useState(false);
    const [voiceAnchorsJson, setVoiceAnchorsJson] = useState("");

    // Budget editing state
    const [editingBudgets, setEditingBudgets] = useState(false);
    const [budgetDraft, setBudgetDraft] = useState<{
        max_context_chars: string;
        max_warm_memory: string;
        max_history_chars: string;
        max_history_messages: string;
    }>({ max_context_chars: '', max_warm_memory: '', max_history_chars: '', max_history_messages: '' });
    const budgetSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    const saveBudgets = useCallback(async (draft: typeof budgetDraft) => {
        if (!selectedEntity) return;
        const payload: Record<string, number | undefined> = {};
        const v = (s: string) => s ? parseInt(s, 10) : undefined;
        if (draft.max_context_chars !== '') payload.max_context_chars = v(draft.max_context_chars) || 0;
        if (draft.max_warm_memory !== '') payload.max_warm_memory = v(draft.max_warm_memory);
        if (draft.max_history_chars !== '') payload.max_history_chars = v(draft.max_history_chars);
        if (draft.max_history_messages !== '') payload.max_history_messages = v(draft.max_history_messages);
        if (Object.keys(payload).length === 0) return;
        try {
            await updateBudgetConfig(selectedEntity.id, payload);
        } catch (err) {
            console.error('Failed to save budgets:', err);
        }
    }, [selectedEntity]);

    const handleBudgetChange = (field: keyof typeof budgetDraft, value: string) => {
        // Only allow digits
        if (value && !/^\d*$/.test(value)) return;
        const next = { ...budgetDraft, [field]: value };
        setBudgetDraft(next);
        // Auto-save after 800ms debounce
        if (budgetSaveTimer.current) clearTimeout(budgetSaveTimer.current);
        budgetSaveTimer.current = setTimeout(() => saveBudgets(next), 800);
    };

    // Load entities
    useEffect(() => {
        listEntities().then(data => {
            const list = Array.isArray(data) ? data : [];
            setEntities(list);
            if (list.length > 0) setSelectedEntity(list[0]);
        }).catch(console.error);
    }, []);

    // Load preview when entity changes
    const loadPreview = useCallback(async () => {
        if (!selectedEntity) return;
        setLoading(true);
        try {
            const data = await getContextPreview(selectedEntity.id);
            setPreview(data);
            setLocalSections(data.sections);
            setDisabledSections(data.disabled_sections);
            setDisabledItems(data.disabled_items || {});
            setPinnedItems(data.pinned_items || {});
            setVoiceAnchors(data.voice_anchors || null);
            setVoiceAnchorsJson(data.voice_anchors ? JSON.stringify(data.voice_anchors, null, 2) : "");
            setHasChanges(false);
            // Sync budget draft with loaded values
            if (data.budget_limits) {
                setBudgetDraft({
                    max_context_chars: data.budget_limits.max_context_chars?.toString() || '',
                    max_warm_memory: data.budget_limits.max_warm_memory?.toString() || '',
                    max_history_chars: data.budget_limits.max_history_chars?.toString() || '',
                    max_history_messages: data.budget_limits.max_history_messages?.toString() || '',
                });
            }
        } catch (err) {
            console.error('Failed to load context preview:', err);
        } finally {
            setLoading(false);
        }
    }, [selectedEntity]);

    useEffect(() => { loadPreview(); }, [loadPreview]);

    // Save preferences
    const savePreferences = async () => {
        if (!selectedEntity) return;
        setSaving(true);
        try {
            await updateSectionConfig(selectedEntity.id, {
                section_order: localSections.map(s => s.key),
                disabled_sections: disabledSections,
                disabled_items: disabledItems,
                pinned_items: pinnedItems,
                voice_anchors: voiceAnchors || undefined,
            });
            setHasChanges(false);
        } catch (err) {
            console.error('Failed to save preferences:', err);
        } finally {
            setSaving(false);
        }
    };

    // Toggle section
    const toggleSection = (key: string) => {
        setDisabledSections(prev => {
            const next = prev.includes(key)
                ? prev.filter(k => k !== key)
                : [...prev, key];
            setHasChanges(true);
            return next;
        });
    };

    // Toggle individual item within a section
    const toggleItem = (sectionKey: string, itemId: string) => {
        setDisabledItems(prev => {
            const sectionList = prev[sectionKey] || [];
            const isDisabled = sectionList.includes(itemId);
            const next = {
                ...prev,
                [sectionKey]: isDisabled
                    ? sectionList.filter(id => id !== itemId)
                    : [...sectionList, itemId],
            };
            setHasChanges(true);
            return next;
        });
    };

    // Toggle individual item pin
    const togglePinItem = (sectionKey: string, itemId: string) => {
        setPinnedItems(prev => {
            const sectionList = prev[sectionKey] || [];
            const isPinned = sectionList.includes(itemId);
            const next = {
                ...prev,
                [sectionKey]: isPinned
                    ? sectionList.filter(id => id !== itemId)
                    : [...sectionList, itemId],
            };
            setHasChanges(true);
            return next;
        });
    };

    // Drag handlers
    const handleDragStart = (key: string) => {
        setDraggedKey(key);
    };

    const handleDragOver = (e: React.DragEvent, key: string) => {
        e.preventDefault();
        if (key !== draggedKey) {
            setDragOverKey(key);
        }
    };

    const handleDrop = (targetKey: string) => {
        if (!draggedKey || draggedKey === targetKey) {
            setDraggedKey(null);
            setDragOverKey(null);
            return;
        }

        setLocalSections(prev => {
            const items = [...prev];
            const dragIdx = items.findIndex(s => s.key === draggedKey);
            const dropIdx = items.findIndex(s => s.key === targetKey);
            if (dragIdx < 0 || dropIdx < 0) return prev;

            const [dragged] = items.splice(dragIdx, 1);
            items.splice(dropIdx, 0, dragged);
            return items;
        });
        setHasChanges(true);
        setDraggedKey(null);
        setDragOverKey(null);
    };

    const handleDragEnd = () => {
        setDraggedKey(null);
        setDragOverKey(null);
    };

    // Calculate budget stats
    const enabledChars = localSections
        .filter(s => !disabledSections.includes(s.key) && s.content)
        .reduce((sum, s) => sum + s.char_count, 0);
    const budget = preview?.budget || 8000;
    const budgetPct = Math.min((enabledChars / budget) * 100, 100);

    // Build raw preview text
    const buildRawPreview = () => {
        if (!preview) return '';
        let text = '';
        text += '--- SYSTEM INSTRUCTION ---\n';
        text += preview.system_instruction + '\n\n';
        text += '--- CONTEXT PRIMER (warm memory — CACHEABLE) ---\n';
        text += '[WARM MEMORY]\n';
        text += '╔══════════════════════════════════╗\n';
        text += '║     WARM MEMORY CONTEXT          ║\n';
        text += '╚══════════════════════════════════╝\n\n';

        for (const section of localSections) {
            if (disabledSections.includes(section.key) || !section.content) continue;
            const meta = preview.sections.find(s => s.key === section.key);
            text += `━━━ ${meta?.icon || '📦'} ${meta?.label || section.key} ━━━\n`;
            text += section.content + '\n\n';
        }

        text += '\n--- TOOLS (stable — cached with system prompt) ---\n';
        if (preview.tools?.length) {
            for (const t of preview.tools) text += `  • ${t}\n`;
            text += `  (${preview.tools_chars?.toLocaleString() || '?'} chars)\n`;
        } else {
            text += '  [none]\n';
        }

        text += '\n--- DYNAMIC PREAMBLE (timestamp/gap — NOT cached) ---\n';
        text += preview.dynamic_preamble + '\n\n';
        if (preview.active_model) text += `Active Model: ${preview.active_model}\n\n`;

        text += `--- HISTORY (${preview.history_message_count ?? '?'} messages, ~${(preview.history_estimate_chars ?? 0).toLocaleString()} chars) ---\n`;
        text += `  Budget: max ${preview.budget_limits?.max_history_chars?.toLocaleString() || '?'} chars / ${preview.budget_limits?.max_history_messages || '?'} messages\n`;
        text += '  [budget-trimmed conversation messages]\n';

        if (preview.memory_blocks?.length) {
            text += '\n--- MEMORY BLOCKS (cacheable) ---\n';
            for (const b of preview.memory_blocks) {
                text += `  ${b.pinned ? '📌 ' : ''}${b.title} [${b.category}] (${b.char_count} chars)\n`;
            }
        }

        return text;
    };

    return (
        <div style={{
            display: 'flex', flexDirection: 'column', height: '100%',
            background: 'var(--bg-primary, #0a0a0f)', color: '#e0e0e0',
        }}>
            {/* Header */}
            <div style={{
                padding: '16px 24px', borderBottom: '1px solid rgba(255,255,255,0.08)',
                display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0,
            }}>
                <Layers size={20} style={{ color: '#a78bfa' }} />
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Context Builder</h2>

                {/* Entity selector */}
                <select
                    value={selectedEntity?.id || ''}
                    onChange={e => {
                        const ent = entities.find(en => en.id === e.target.value);
                        if (ent) setSelectedEntity(ent);
                    }}
                    style={{
                        background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                        color: '#e0e0e0', padding: '6px 12px', borderRadius: 6, fontSize: 13,
                    }}
                >
                    {entities.map(e => (
                        <option key={e.id} value={e.id}>{e.name || e.id}</option>
                    ))}
                </select>

                <div style={{ flex: 1 }} />

                {/* Active model badge */}
                {preview?.active_model && (
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        background: 'rgba(167,139,250,0.1)', border: '1px solid rgba(167,139,250,0.2)',
                        padding: '4px 10px', borderRadius: 6, fontSize: 11,
                    }}>
                        <Cpu size={12} style={{ color: '#a78bfa' }} />
                        <span style={{ color: '#c4b5fd', fontFamily: 'monospace' }}>
                            {preview.active_model}
                        </span>
                    </div>
                )}

                {/* Stacked component budget bar */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                    <BarChart3 size={14} style={{ color: '#818cf8' }} />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <div style={{
                            width: 180, height: 10, background: 'rgba(255,255,255,0.06)',
                            borderRadius: 4, overflow: 'hidden', display: 'flex',
                        }}>
                            {preview?.component_summary && (() => {
                                const s = preview.component_summary;
                                const total = s.total || 1;
                                const segments = [
                                    { chars: s.system_instruction, color: '#a78bfa', label: 'System' },
                                    { chars: s.warm_memory_enabled, color: '#34d399', label: 'Warm' },
                                    { chars: s.tools, color: '#60a5fa', label: 'Tools' },
                                    { chars: s.dynamic_preamble, color: '#fbbf24', label: 'Preamble' },
                                    { chars: s.history_estimate, color: '#f97316', label: 'History' },
                                ];
                                return segments.map((seg, i) => (
                                    <div
                                        key={i}
                                        title={`${seg.label}: ${seg.chars.toLocaleString()} chars`}
                                        style={{
                                            width: `${(seg.chars / total) * 100}%`,
                                            height: '100%',
                                            background: seg.color,
                                            minWidth: seg.chars > 0 ? 2 : 0,
                                        }}
                                    />
                                ));
                            })()}
                        </div>
                        <div style={{ display: 'flex', gap: 6, fontSize: 9, opacity: 0.5 }}>
                            {preview?.budget_limits && (
                                <>
                                    <span>Warm ≤ {preview.budget_limits.max_warm_memory.toLocaleString()}</span>
                                    <span>|</span>
                                    <span>Hist ≤ {preview.budget_limits.max_history_chars.toLocaleString()} ({preview.budget_limits.max_history_messages} msgs)</span>
                                </>
                            )}
                        </div>
                    </div>
                    <span style={{
                        color: budgetPct > 90 ? '#f87171' : budgetPct > 70 ? '#fbbf24' : '#34d399',
                        fontFamily: 'monospace', fontSize: 11,
                    }}>
                        {(preview?.component_summary?.total || enabledChars).toLocaleString()} total
                    </span>
                </div>

                {/* Actions */}
                <button
                    onClick={() => setShowPreview(!showPreview)}
                    style={{
                        background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                        color: '#e0e0e0', padding: '6px 12px', borderRadius: 6, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                    }}
                >
                    {showPreview ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                    Preview
                </button>

                <button
                    onClick={loadPreview}
                    disabled={loading}
                    style={{
                        background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                        color: '#e0e0e0', padding: '6px 12px', borderRadius: 6, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                        opacity: loading ? 0.5 : 1,
                    }}
                >
                    {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                    Refresh
                </button>

                {hasChanges && (
                    <button
                        onClick={savePreferences}
                        disabled={saving}
                        style={{
                            background: '#a78bfa', border: 'none',
                            color: '#fff', padding: '6px 16px', borderRadius: 6, cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                            fontWeight: 600, opacity: saving ? 0.6 : 1,
                        }}
                    >
                        {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
                        Save
                    </button>
                )}
            </div>

            {/* Main content */}
            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
                {/* Left panel — Section list */}
                <div style={{
                    flex: showPreview ? '0 0 50%' : '1',
                    overflow: 'auto', padding: '16px',
                    borderRight: showPreview ? '1px solid rgba(255,255,255,0.08)' : 'none',
                }}>
                    {loading && !preview ? (
                        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
                            <Loader2 size={24} className="spin" style={{ color: '#a78bfa' }} />
                        </div>
                    ) : (
                        <>
                            {/* System Instruction block */}
                            <div style={{
                                background: 'rgba(167,139,250,0.06)', border: '1px solid rgba(167,139,250,0.15)',
                                borderRadius: 8, padding: '12px 16px', marginBottom: 8,
                            }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    cursor: 'pointer', userSelect: 'none',
                                }}
                                    onClick={() => setExpandedSection(expandedSection === '__system__' ? null : '__system__')}
                                >
                                    {expandedSection === '__system__' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <Settings2 size={14} style={{ color: '#a78bfa' }} />
                                    <span style={{ fontSize: 13, fontWeight: 600 }}>System Instruction</span>
                                    <CacheTag tag="stable" />
                                    <span style={{
                                        fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace', marginLeft: 'auto',
                                    }}>
                                        {preview?.system_instruction_chars?.toLocaleString() || 0} chars
                                    </span>
                                </div>
                                {expandedSection === '__system__' && preview && (
                                    <pre style={{
                                        marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.3)',
                                        borderRadius: 6, fontSize: 11, lineHeight: 1.5,
                                        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                        maxHeight: 300, overflow: 'auto', color: '#c0c0c0',
                                    }}>
                                        {preview.system_instruction}
                                    </pre>
                                )}
                            </div>

                            {/* Warm Memory sections */}
                            <div style={{
                                fontSize: 11, color: 'rgba(255,255,255,0.4)', padding: '8px 4px',
                                display: 'flex', alignItems: 'center', gap: 6,
                            }}>
                                <Zap size={12} />
                                WARM MEMORY SECTIONS — drag to reorder, toggle to include/exclude
                                <CacheTag tag="cacheable" />
                            </div>

                            {localSections.map(section => {
                                const isEnabled = !disabledSections.includes(section.key);
                                const isExpanded = expandedSection === section.key;
                                const isDragged = draggedKey === section.key;
                                const isDragOver = dragOverKey === section.key;
                                const color = SECTION_COLORS[section.key] || '#999';

                                return (
                                    <div
                                        key={section.key}
                                        draggable
                                        onDragStart={() => handleDragStart(section.key)}
                                        onDragOver={e => handleDragOver(e, section.key)}
                                        onDrop={() => handleDrop(section.key)}
                                        onDragEnd={handleDragEnd}
                                        style={{
                                            background: isDragOver
                                                ? 'rgba(167,139,250,0.12)'
                                                : isEnabled
                                                    ? 'rgba(255,255,255,0.03)'
                                                    : 'rgba(255,255,255,0.01)',
                                            border: `1px solid ${isDragOver ? 'rgba(167,139,250,0.4)' : 'rgba(255,255,255,0.06)'}`,
                                            borderRadius: 8,
                                            marginBottom: 4,
                                            opacity: isDragged ? 0.4 : isEnabled ? 1 : 0.45,
                                            transition: 'all 0.15s',
                                            cursor: 'grab',
                                        }}
                                    >
                                        <div style={{
                                            padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 8,
                                        }}>
                                            <GripVertical size={14} style={{ color: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />

                                            {/* Toggle */}
                                            <button
                                                onClick={(e) => { e.stopPropagation(); toggleSection(section.key); }}
                                                style={{
                                                    background: 'none', border: 'none', cursor: 'pointer',
                                                    padding: 2, display: 'flex', flexShrink: 0,
                                                }}
                                                title={isEnabled ? 'Disable section' : 'Enable section'}
                                            >
                                                {isEnabled
                                                    ? <Eye size={14} style={{ color: '#34d399' }} />
                                                    : <EyeOff size={14} style={{ color: '#666' }} />
                                                }
                                            </button>

                                            {/* Section icon + label */}
                                            <span style={{ fontSize: 15 }}>{section.icon}</span>
                                            <span style={{
                                                fontSize: 13, fontWeight: 500,
                                                color: isEnabled ? '#e0e0e0' : '#666',
                                                flex: 1,
                                            }}>
                                                {section.label}
                                            </span>

                                            {/* Char count bar */}
                                            {section.content && (
                                                <div style={{
                                                    display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
                                                }}>
                                                    <div style={{
                                                        width: 60, height: 4, background: 'rgba(255,255,255,0.06)',
                                                        borderRadius: 2, overflow: 'hidden',
                                                    }}>
                                                        <div style={{
                                                            width: `${Math.min((section.char_count / budget) * 100, 100)}%`,
                                                            height: '100%',
                                                            background: isEnabled ? color : '#444',
                                                            borderRadius: 2,
                                                        }} />
                                                    </div>
                                                    <span style={{
                                                        fontSize: 10, fontFamily: 'monospace',
                                                        color: isEnabled ? 'rgba(255,255,255,0.4)' : '#444',
                                                        minWidth: 45, textAlign: 'right',
                                                    }}>
                                                        {section.char_count.toLocaleString()}
                                                    </span>
                                                </div>
                                            )}

                                            {/* Expand toggle */}
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setExpandedSection(isExpanded ? null : section.key);
                                                }}
                                                style={{
                                                    background: 'none', border: 'none', cursor: 'pointer',
                                                    padding: 2, display: 'flex', flexShrink: 0,
                                                    color: 'rgba(255,255,255,0.3)',
                                                }}
                                            >
                                                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                            </button>
                                        </div>

                                        {/* Expanded content */}
                                        {isExpanded && (
                                            <div style={{
                                                padding: '0 12px 12px 44px',
                                            }}>
                                                {section.items && section.items.length > 0 ? (
                                                    /* Item-level toggles */
                                                    <div style={{
                                                        background: 'rgba(0,0,0,0.3)', borderRadius: 6,
                                                        padding: 8, maxHeight: 400, overflow: 'auto',
                                                    }}>
                                                        <div style={{
                                                            fontSize: 9, color: '#666', marginBottom: 6, padding: '0 4px',
                                                        }}>
                                                            {section.items.length} items — click eye to show/hide individual items
                                                        </div>
                                                        {section.items.map(item => {
                                                            const sectionDisabled = disabledItems[section.key] || [];
                                                            const itemEnabled = !sectionDisabled.includes(item.id);
                                                            const sectionPinned = pinnedItems[section.key] || [];
                                                            const itemPinned = sectionPinned.includes(item.id);
                                                            return (
                                                                <div
                                                                    key={item.id}
                                                                    style={{
                                                                        display: 'flex', alignItems: 'center', gap: 6,
                                                                        padding: '4px 6px', borderRadius: 4,
                                                                        opacity: itemEnabled ? 1 : 0.4,
                                                                        background: itemEnabled ? (itemPinned ? 'rgba(6,182,212,0.08)' : 'transparent') : 'rgba(255,255,255,0.02)',
                                                                        border: itemPinned ? '1px solid rgba(6,182,212,0.2)' : '1px solid transparent',
                                                                    }}
                                                                >
                                                                    <button
                                                                        onClick={() => togglePinItem(section.key, item.id)}
                                                                        style={{
                                                                            background: 'none', border: 'none', cursor: 'pointer',
                                                                            padding: 1, display: 'flex', flexShrink: 0,
                                                                        }}
                                                                        title={itemPinned ? 'Unpin this item' : 'Pin this item (prevents truncation)'}
                                                                    >
                                                                        {itemPinned
                                                                            ? <Pin size={11} style={{ color: '#06b6d4' }} />
                                                                            : <Pin size={11} style={{ color: '#666' }} />
                                                                        }
                                                                    </button>
                                                                    <button
                                                                        onClick={() => toggleItem(section.key, item.id)}
                                                                        style={{
                                                                            background: 'none', border: 'none', cursor: 'pointer',
                                                                            padding: 1, display: 'flex', flexShrink: 0,
                                                                        }}
                                                                        title={itemEnabled ? 'Hide this item' : 'Show this item'}
                                                                    >
                                                                        {itemEnabled
                                                                            ? <Eye size={11} style={{ color: '#34d399' }} />
                                                                            : <EyeOff size={11} style={{ color: '#666' }} />
                                                                        }
                                                                    </button>
                                                                    <span style={{
                                                                        fontSize: 11, color: itemEnabled ? '#c0c0c0' : '#555',
                                                                        flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
                                                                        whiteSpace: 'nowrap',
                                                                        textDecoration: itemEnabled ? 'none' : 'line-through',
                                                                    }}>
                                                                        {item.label}
                                                                    </span>
                                                                    <span style={{
                                                                        fontSize: 9, fontFamily: 'monospace',
                                                                        color: 'rgba(255,255,255,0.25)', flexShrink: 0,
                                                                    }}>
                                                                        {item.char_count}
                                                                    </span>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : section.content ? (
                                                    <pre style={{
                                                        padding: 12, background: 'rgba(0,0,0,0.3)',
                                                        borderRadius: 6, fontSize: 11, lineHeight: 1.5,
                                                        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                                        maxHeight: 400, overflow: 'auto', color: '#c0c0c0',
                                                        margin: 0,
                                                    }}>
                                                        {section.content}
                                                    </pre>
                                                ) : (
                                                    <div style={{
                                                        padding: 12, background: 'rgba(0,0,0,0.2)',
                                                        borderRadius: 6, fontSize: 12, color: '#666',
                                                        fontStyle: 'italic',
                                                    }}>
                                                        No content — this section is empty
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            {/* Voice Anchors block */}
                            <div style={{
                                background: 'rgba(236,72,153,0.06)', border: '1px solid rgba(236,72,153,0.15)',
                                borderRadius: 8, padding: '12px 16px', marginTop: 8,
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, userSelect: 'none' }}>
                                    <div
                                        style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', flex: 1 }}
                                        onClick={() => setExpandedSection(expandedSection === '__anchors__' ? null : '__anchors__')}
                                    >
                                        {expandedSection === '__anchors__' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        <span style={{ fontSize: 15 }}>🎭</span>
                                        <span style={{ fontSize: 13, fontWeight: 600 }}>Voice Anchors</span>
                                        <CacheTag tag="stable" />
                                        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace', marginLeft: 'auto' }}>
                                            {voiceAnchors?.length || 0} modes
                                        </span>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setIsEditingVoiceAnchors(!isEditingVoiceAnchors);
                                            if (!isEditingVoiceAnchors) {
                                                setExpandedSection('__anchors__');
                                            }
                                        }}
                                        style={{
                                            background: isEditingVoiceAnchors ? '#ec4899' : 'rgba(236,72,153,0.15)',
                                            color: isEditingVoiceAnchors ? '#fff' : '#fbcfe8',
                                            border: 'none', padding: '4px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 10,
                                        }}
                                    >
                                        {isEditingVoiceAnchors ? 'Done' : 'Edit JSON'}
                                    </button>
                                </div>
                                
                                {expandedSection === '__anchors__' && (
                                    <div style={{ marginTop: 8 }}>
                                        {isEditingVoiceAnchors ? (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                                <div style={{ fontSize: 11, color: '#999' }}>
                                                    Paste Agent's Voice Anchors JSON array here. Example: {"[ { \"mode\": \"...\", \"description\": \"...\", \"examples\": [...] } ]"}
                                                </div>
                                                <textarea
                                                    value={voiceAnchorsJson}
                                                    onChange={(e) => {
                                                        setVoiceAnchorsJson(e.target.value);
                                                        setHasChanges(true);
                                                        try {
                                                            const parsed = JSON.parse(e.target.value);
                                                            setVoiceAnchors(Array.isArray(parsed) ? parsed : null);
                                                        } catch (err) {
                                                            // Invalid JSON, don't update the actual object yet
                                                        }
                                                    }}
                                                    style={{
                                                        width: '100%', height: 200, background: 'rgba(0,0,0,0.3)',
                                                        border: '1px solid rgba(236,72,153,0.3)', borderRadius: 6,
                                                        color: '#fbcfe8', padding: 8, fontSize: 11, fontFamily: 'monospace',
                                                        resize: 'vertical',
                                                    }}
                                                    placeholder="[ { ... } ]"
                                                    spellCheck={false}
                                                />
                                            </div>
                                        ) : (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                                {voiceAnchors && voiceAnchors.length > 0 ? (
                                                    voiceAnchors.map((anchor, idx) => (
                                                        <div key={idx} style={{
                                                            background: 'rgba(0,0,0,0.2)', padding: '6px 10px', borderRadius: 4,
                                                            border: '1px solid rgba(255,255,255,0.05)'
                                                        }}>
                                                            <div style={{ fontSize: 12, fontWeight: 600, color: '#e0e0e0', marginBottom: 2 }}>
                                                                {anchor.mode || 'Unknown Mode'}
                                                            </div>
                                                            <div style={{ fontSize: 11, color: '#aaa', fontStyle: 'italic', marginBottom: 6 }}>
                                                                {anchor.description || ''}
                                                            </div>
                                                            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
                                                                {anchor.examples ? `${anchor.examples.length} examples` : '0 examples'}
                                                            </div>
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div style={{ fontSize: 11, color: '#666', fontStyle: 'italic', padding: 8 }}>
                                                        No voice anchors defined. Click 'Edit JSON' to add them.
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Dynamic Preamble block */}
                            <div style={{
                                background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.15)',
                                borderRadius: 8, padding: '12px 16px', marginTop: 8,
                            }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    cursor: 'pointer', userSelect: 'none',
                                }}
                                    onClick={() => setExpandedSection(expandedSection === '__dynamic__' ? null : '__dynamic__')}
                                >
                                    {expandedSection === '__dynamic__' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <Clock size={14} style={{ color: '#fbbf24' }} />
                                    <span style={{ fontSize: 13, fontWeight: 600 }}>Dynamic Preamble</span>
                                    <CacheTag tag="volatile" />
                                    <span style={{
                                        fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace', marginLeft: 'auto',
                                    }}>
                                        {preview?.dynamic_preamble_chars?.toLocaleString() || 0} chars
                                    </span>
                                </div>
                                {expandedSection === '__dynamic__' && preview && (
                                    <pre style={{
                                        marginTop: 8, padding: 12, background: 'rgba(0,0,0,0.3)',
                                        borderRadius: 6, fontSize: 11, lineHeight: 1.5,
                                        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                        maxHeight: 200, overflow: 'auto', color: '#c0c0c0',
                                    }}>
                                        {preview.dynamic_preamble}
                                    </pre>
                                )}
                            </div>

                            {/* Tools block */}
                            <div style={{
                                background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.15)',
                                borderRadius: 8, padding: '12px 16px', marginTop: 8,
                            }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    cursor: 'pointer', userSelect: 'none',
                                }}
                                    onClick={() => setExpandedSection(expandedSection === '__tools__' ? null : '__tools__')}
                                >
                                    {expandedSection === '__tools__' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <Wrench size={14} style={{ color: '#60a5fa' }} />
                                    <span style={{ fontSize: 13, fontWeight: 600 }}>Tools</span>
                                    <CacheTag tag="stable" />
                                    <span style={{
                                        fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace', marginLeft: 'auto',
                                    }}>
                                        {preview?.tools?.length || 0} tools &middot; {preview?.tools_chars?.toLocaleString() || 0} chars
                                    </span>
                                </div>
                                {expandedSection === '__tools__' && preview?.tools && (
                                    <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                        {preview.tools.map((tool, i) => (
                                            <span key={i} style={{
                                                fontSize: 11, padding: '3px 8px', borderRadius: 4,
                                                background: tool.startsWith('[MCP]')
                                                    ? 'rgba(251,191,36,0.12)' : 'rgba(96,165,250,0.12)',
                                                color: tool.startsWith('[MCP]') ? '#fbbf24' : '#60a5fa',
                                                border: `1px solid ${tool.startsWith('[MCP]')
                                                    ? 'rgba(251,191,36,0.2)' : 'rgba(96,165,250,0.2)'}`,
                                            }}>
                                                {tool}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Memory Blocks (individual) */}
                            {preview?.memory_blocks && preview.memory_blocks.length > 0 && (
                                <div style={{
                                    background: 'rgba(6,182,212,0.06)', border: '1px solid rgba(6,182,212,0.15)',
                                    borderRadius: 8, padding: '12px 16px', marginTop: 8,
                                }}>
                                    <div style={{
                                        display: 'flex', alignItems: 'center', gap: 8,
                                        cursor: 'pointer', userSelect: 'none',
                                    }}
                                        onClick={() => setExpandedSection(expandedSection === '__blocks__' ? null : '__blocks__')}
                                    >
                                        {expandedSection === '__blocks__' ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        <Pin size={14} style={{ color: '#06b6d4' }} />
                                        <span style={{ fontSize: 13, fontWeight: 600 }}>Memory Blocks</span>
                                        <CacheTag tag="cacheable" />
                                        <span style={{
                                            fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace', marginLeft: 'auto',
                                        }}>
                                            {preview.memory_blocks.filter(b => b.pinned).length} pinned / {preview.memory_blocks.length} total
                                        </span>
                                    </div>
                                    {expandedSection === '__blocks__' && (
                                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                                            {preview.memory_blocks.map(block => (
                                                <div key={block.id} style={{
                                                    display: 'flex', alignItems: 'center', gap: 8,
                                                    padding: '6px 10px', borderRadius: 6,
                                                    background: block.pinned ? 'rgba(6,182,212,0.08)' : 'rgba(0,0,0,0.2)',
                                                    border: `1px solid ${block.pinned ? 'rgba(6,182,212,0.2)' : 'rgba(255,255,255,0.05)'}`,
                                                }}>
                                                    {block.pinned && <Pin size={10} style={{ color: '#06b6d4', flexShrink: 0 }} />}
                                                    <span style={{ fontSize: 12, flex: 1, color: block.pinned ? '#e0e0e0' : '#888' }}>
                                                        {block.title}
                                                    </span>
                                                    {block.category && (
                                                        <span style={{
                                                            fontSize: 9, padding: '1px 5px', borderRadius: 3,
                                                            background: 'rgba(255,255,255,0.06)', color: '#888',
                                                        }}>
                                                            {block.category}
                                                        </span>
                                                    )}
                                                    <span style={{
                                                        fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.3)',
                                                    }}>
                                                        {block.char_count.toLocaleString()}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Conversation History */}
                            <div style={{
                                background: 'rgba(249,115,22,0.06)', border: '1px solid rgba(249,115,22,0.15)',
                                borderRadius: 8, padding: '12px 16px', marginTop: 8,
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <MessageSquare size={14} style={{ color: '#f97316' }} />
                                    <span style={{ fontSize: 13, fontWeight: 600 }}>Conversation History</span>
                                    <CacheTag tag="volatile" />
                                    <span style={{
                                        fontSize: 11, color: 'rgba(255,255,255,0.4)', fontFamily: 'monospace', marginLeft: 'auto',
                                    }}>
                                        {preview?.history_message_count || 0} msgs &middot; ~{(preview?.history_estimate_chars || 0).toLocaleString()} chars
                                    </span>
                                </div>
                                {preview?.budget_limits && (
                                    <div style={{
                                        marginTop: 6, fontSize: 10, color: 'rgba(255,255,255,0.3)',
                                        display: 'flex', gap: 12,
                                    }}>
                                        <span>Budget: ≤ {preview.budget_limits.max_history_chars.toLocaleString()} chars</span>
                                        <span>Max: {preview.budget_limits.max_history_messages} msgs</span>
                                        {preview.history_estimate_chars > preview.budget_limits.max_history_chars && (
                                            <span style={{ color: '#f87171' }}>
                                                (truncated to ~{preview.budget_limits.max_history_chars.toLocaleString()})
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Component breakdown summary */}
                            {preview?.component_summary && (
                                <div style={{
                                    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
                                    borderRadius: 8, padding: '12px 16px', marginTop: 12,
                                }}>
                                    <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 8, color: '#888' }}>
                                        CONTEXT BREAKDOWN
                                    </div>
                                    {[
                                        { label: 'System Instruction', chars: preview.component_summary.system_instruction, color: '#a78bfa', tag: 'stable' as const },
                                        { label: 'Warm Memory', chars: preview.component_summary.warm_memory_enabled, color: '#34d399', tag: 'cacheable' as const, limit: preview.budget_limits?.max_warm_memory },
                                        { label: 'Tools', chars: preview.component_summary.tools, color: '#60a5fa', tag: 'stable' as const },
                                        { label: 'Dynamic Preamble', chars: preview.component_summary.dynamic_preamble, color: '#fbbf24', tag: 'volatile' as const },
                                        { label: 'History (est.)', chars: preview.component_summary.history_estimate, color: '#f97316', tag: 'volatile' as const, limit: preview.budget_limits?.max_history_chars },
                                    ].map((row, i) => (
                                        <div key={i} style={{
                                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
                                        }}>
                                            <div style={{ width: 6, height: 6, borderRadius: 3, background: row.color, flexShrink: 0 }} />
                                            <span style={{ fontSize: 11, flex: 1, color: '#c0c0c0' }}>{row.label}</span>
                                            <CacheTag tag={row.tag} />
                                            <span style={{ fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.4)', minWidth: 60, textAlign: 'right' }}>
                                                {row.chars.toLocaleString()}
                                                {row.limit ? ` / ${row.limit.toLocaleString()}` : ''}
                                            </span>
                                        </div>
                                    ))}
                                    <div style={{
                                        borderTop: '1px solid rgba(255,255,255,0.08)',
                                        marginTop: 6, paddingTop: 6,
                                        display: 'flex', alignItems: 'center',
                                    }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, flex: 1, color: '#e0e0e0' }}>Total</span>
                                        <span style={{ fontSize: 12, fontWeight: 600, fontFamily: 'monospace', color: '#e0e0e0' }}>
                                            {preview.component_summary.total.toLocaleString()} chars
                                            {preview.budget_limits?.max_context_chars
                                                ? ` / ${preview.budget_limits.max_context_chars.toLocaleString()}`
                                                : ''}
                                        </span>
                                    </div>
                                </div>
                            )}

                            {/* Budget Editor */}
                            <div style={{
                                background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
                                borderRadius: 8, padding: '12px 16px', marginTop: 12,
                            }}>
                                <div
                                    onClick={() => setEditingBudgets(!editingBudgets)}
                                    style={{
                                        fontSize: 11, fontWeight: 600, color: '#888', cursor: 'pointer',
                                        display: 'flex', alignItems: 'center', gap: 6,
                                    }}
                                >
                                    <Settings2 size={12} />
                                    BUDGET LIMITS
                                    {editingBudgets ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                                    <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)', marginLeft: 'auto' }}>auto-saves</span>
                                </div>
                                {editingBudgets && (
                                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                                        {[
                                            { key: 'max_context_chars' as const, label: 'Total Context Budget', placeholder: 'unlimited', hint: 'chars (0 = unlimited)' },
                                            { key: 'max_warm_memory' as const, label: 'Warm Memory', placeholder: '8000', hint: 'chars' },
                                            { key: 'max_history_chars' as const, label: 'History', placeholder: '20000', hint: 'chars' },
                                            { key: 'max_history_messages' as const, label: 'History Messages', placeholder: '50', hint: 'count' },
                                        ].map(({ key, label, placeholder, hint }) => (
                                            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                <span style={{ fontSize: 11, color: '#c0c0c0', minWidth: 130 }}>{label}</span>
                                                <input
                                                    type="text"
                                                    inputMode="numeric"
                                                    value={budgetDraft[key]}
                                                    onChange={e => handleBudgetChange(key, e.target.value)}
                                                    placeholder={placeholder}
                                                    style={{
                                                        flex: 1, maxWidth: 100, padding: '3px 8px', fontSize: 11,
                                                        fontFamily: 'monospace', background: 'rgba(255,255,255,0.06)',
                                                        border: '1px solid rgba(255,255,255,0.1)', borderRadius: 4,
                                                        color: '#e0e0e0', outline: 'none',
                                                    }}
                                                />
                                                <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.25)' }}>{hint}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>

                {/* Right panel — Preview */}
                {showPreview && (
                    <div style={{
                        flex: '0 0 50%', overflow: 'auto', padding: 16,
                        background: 'rgba(0,0,0,0.2)',
                    }}>
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                        }}>
                            <Eye size={14} style={{ color: '#818cf8' }} />
                            <span style={{ fontSize: 13, fontWeight: 600 }}>Live Preview</span>
                            <div style={{ flex: 1 }} />
                            <div style={{
                                display: 'flex', background: 'rgba(255,255,255,0.06)',
                                borderRadius: 6, overflow: 'hidden',
                            }}>
                                {(['structured', 'raw'] as const).map(mode => (
                                    <button
                                        key={mode}
                                        onClick={() => setPreviewMode(mode)}
                                        style={{
                                            background: previewMode === mode ? 'rgba(167,139,250,0.2)' : 'transparent',
                                            border: 'none', color: previewMode === mode ? '#a78bfa' : '#888',
                                            padding: '4px 10px', fontSize: 11, cursor: 'pointer',
                                        }}
                                    >
                                        {mode.charAt(0).toUpperCase() + mode.slice(1)}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {previewMode === 'raw' ? (
                            <pre style={{
                                padding: 16, background: 'rgba(0,0,0,0.4)',
                                borderRadius: 8, fontSize: 11, lineHeight: 1.6,
                                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                color: '#b0b0b0', fontFamily: "'Fira Code', 'Cascadia Code', monospace",
                            }}>
                                {buildRawPreview()}
                            </pre>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {/* System instruction preview */}
                                <PreviewBlock
                                    label="System Instruction"
                                    icon="⚙️"
                                    color="#a78bfa"
                                    chars={preview?.system_instruction_chars || 0}
                                    tag="stable"
                                    content={preview?.system_instruction || ''}
                                />

                                {/* Warm memory sections */}
                                {localSections
                                    .filter(s => !disabledSections.includes(s.key) && s.content)
                                    .map(section => (
                                        <PreviewBlock
                                            key={section.key}
                                            label={`${section.icon} ${section.label}`}
                                            icon=""
                                            color={SECTION_COLORS[section.key] || '#999'}
                                            chars={section.char_count}
                                            tag="cacheable"
                                            content={section.content}
                                        />
                                    ))
                                }

                                {/* Tools */}
                                {preview?.tools && preview.tools.length > 0 && (
                                    <PreviewBlock
                                        label={`Tools (${preview.tools.length})`}
                                        icon="🔧"
                                        color="#34d399"
                                        chars={preview.tools_chars || 0}
                                        tag="stable"
                                        content={preview.tools.map(t => `• ${t}`).join('\n')}
                                    />
                                )}

                                {/* Dynamic preamble */}
                                <PreviewBlock
                                    label="Dynamic Preamble"
                                    icon="⏱️"
                                    color="#fbbf24"
                                    chars={preview?.dynamic_preamble_chars || 0}
                                    tag="volatile"
                                    content={preview?.dynamic_preamble || ''}
                                />

                                {/* Memory Blocks */}
                                {preview?.memory_blocks && preview.memory_blocks.length > 0 && (
                                    <PreviewBlock
                                        label={`Memory Blocks (${preview.memory_blocks.length})`}
                                        icon="🧩"
                                        color="#c084fc"
                                        chars={preview.memory_blocks.reduce((s, b) => s + b.char_count, 0)}
                                        tag="cacheable"
                                        content={preview.memory_blocks.map(b =>
                                            `${b.pinned ? '📌 ' : ''}${b.title} [${b.category}] — ${b.char_count} chars`
                                        ).join('\n')}
                                    />
                                )}

                                {/* History */}
                                <PreviewBlock
                                    label={`Conversation History (${preview?.history_message_count ?? '?'} msgs)`}
                                    icon="💬"
                                    color="#60a5fa"
                                    chars={preview?.history_estimate_chars || 0}
                                    tag="volatile"
                                    content={`${preview?.history_message_count ?? 0} messages (~${(preview?.history_estimate_chars ?? 0).toLocaleString()} chars)\nBudget: max ${preview?.budget_limits?.max_history_chars?.toLocaleString() || '?'} chars / ${preview?.budget_limits?.max_history_messages || '?'} messages\n\n[Messages are budget-trimmed at runtime]`}
                                />
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Preview Block sub-component ──────────────────────

function PreviewBlock({ label, icon, color, chars, tag, content }: {
    label: string;
    icon: string;
    color: string;
    chars: number;
    tag: 'stable' | 'cacheable' | 'volatile';
    content: string;
}) {
    const [expanded, setExpanded] = useState(false);

    const tagColors = {
        stable: { bg: 'rgba(167,139,250,0.15)', text: '#a78bfa' },
        cacheable: { bg: 'rgba(52,211,153,0.15)', text: '#34d399' },
        volatile: { bg: 'rgba(251,191,36,0.15)', text: '#fbbf24' },
    };

    return (
        <div style={{
            background: `${color}08`, border: `1px solid ${color}22`,
            borderRadius: 8, overflow: 'hidden',
        }}>
            <div
                onClick={() => setExpanded(!expanded)}
                style={{
                    padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8,
                    cursor: 'pointer', userSelect: 'none',
                }}
            >
                {icon && <span style={{ fontSize: 13 }}>{icon}</span>}
                <span style={{ fontSize: 12, fontWeight: 500, color: '#d0d0d0' }}>{label}</span>
                <span style={{
                    fontSize: 9, padding: '1px 5px', borderRadius: 3,
                    background: tagColors[tag].bg, color: tagColors[tag].text,
                }}>
                    {tag}
                </span>
                <span style={{
                    fontSize: 10, fontFamily: 'monospace', color: 'rgba(255,255,255,0.3)', marginLeft: 'auto',
                }}>
                    {chars > 0 ? `${chars.toLocaleString()} chars` : ''}
                </span>
                {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </div>
            {expanded && (
                <pre style={{
                    margin: '0 12px 12px', padding: 10, background: 'rgba(0,0,0,0.4)',
                    borderRadius: 6, fontSize: 10, lineHeight: 1.5,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    maxHeight: 300, overflow: 'auto', color: '#b0b0b0',
                }}>
                    {content}
                </pre>
            )}
        </div>
    );
}
