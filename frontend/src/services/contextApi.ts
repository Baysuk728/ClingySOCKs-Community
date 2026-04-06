/**
 * Context Builder API — client for /context/* endpoints
 */

import axios from 'axios';

const API_URL = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    },
});

// ── Types ────────────────────────────────────────────

export interface SectionItem {
    id: string;
    label: string;
    char_count: number;
}

export interface SectionInfo {
    key: string;
    label: string;
    icon: string;
    content: string;
    char_count: number;
    enabled: boolean;
    order: number;
    items?: SectionItem[] | null;
}

export interface MemoryBlockInfo {
    id: string;
    title: string;
    category: string | null;
    pinned: boolean;
    char_count: number;
}

export interface BudgetLimits {
    max_context_chars: number | null;
    max_warm_memory: number;
    max_history_chars: number;
    max_history_messages: number;
}

export interface ComponentSummary {
    system_instruction: number;
    warm_memory_enabled: number;
    dynamic_preamble: number;
    tools: number;
    history_estimate: number;
    total: number;
}

export interface ContextPreview {
    entity_id: string;
    system_instruction: string;
    system_instruction_chars: number;
    sections: SectionInfo[];
    dynamic_preamble: string;
    dynamic_preamble_chars: number;
    total_warm_chars: number;
    budget: number;
    budget_used_pct: number;
    section_order: string[];
    disabled_sections: string[];
    disabled_items: Record<string, string[]>;
    pinned_items: Record<string, string[]>;
    voice_anchors: any[] | null;
    // Full transparency fields
    active_model: string;
    tools: string[];
    tools_chars: number;
    memory_blocks: MemoryBlockInfo[];
    history_estimate_chars: number;
    history_message_count: number;
    budget_limits: BudgetLimits;
    component_summary: ComponentSummary;
}

export interface GraphNode {
    id: string;
    type: string;
    label: string;
    group: string;
}

export interface GraphEdge {
    source: string;
    target: string;
    relation: string;
    strength: number;
    context: string | null;
    status: 'active' | 'superseded' | 'historical';
}

export interface GraphData {
    nodes: GraphNode[];
    edges: GraphEdge[];
    arcs: any[];
    stats: {
        total_edges: number;
        total_nodes: number;
        relation_types: string[];
        node_types: string[];
        total_arcs: number;
    };
}

// ── API Functions ────────────────────────────────────

export async function getContextPreview(entityId: string, budget?: number): Promise<ContextPreview> {
    const params: Record<string, any> = {};
    if (budget) params.budget = budget;
    const response = await api.get(`/context/${entityId}/preview`, { params });
    return response.data;
}

export async function updateSectionConfig(
    entityId: string,
    config: {
        section_order?: string[];
        disabled_sections?: string[];
        disabled_items?: Record<string, string[]>;
        pinned_items?: Record<string, string[]>;
        voice_anchors?: any[];
    }
): Promise<void> {
    await api.put(`/context/${entityId}/sections`, config);
}

export async function updateBudgetConfig(
    entityId: string,
    budgets: {
        max_context_chars?: number | null;
        max_warm_memory?: number;
        max_history_chars?: number;
        max_history_messages?: number;
    }
): Promise<void> {
    await api.put(`/context/${entityId}/budgets`, budgets);
}

export async function getGraphData(entityId: string, limit: number = 200): Promise<GraphData> {
    const response = await api.get(`/context/${entityId}/graph`, { params: { limit } });
    return response.data;
}
