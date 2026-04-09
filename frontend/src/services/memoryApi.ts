import axios from 'axios';
import { Memory } from '../types';

import { getApiUrlSync } from './apiConfig';

const API_URL = getApiUrlSync();
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    },
});

export interface WarmMemory {
    core_state: any;
    entity_context: any;
    recent_memories: any[];
}

export interface SearchResult {
    id: string;
    content: string;
    similarity: number;
    metadata: any;
}

export const memoryApi = {
    // Get Warm Memory
    getWarmMemory: async (entityId: string, level: string = 'standard'): Promise<WarmMemory> => {
        const response = await api.get(`/memory/${entityId}/warm`, {
            params: { level },
        });
        return response.data;
    },

    // Recall Memory
    recall: async (entityId: string, type: string, query?: string): Promise<Memory[]> => {
        const response = await api.post(`/memory/${entityId}/recall`, {
            type,
            query,
        });
        return response.data;
    },

    // Search Memory
    search: async (entityId: string, query: string): Promise<SearchResult[]> => {
        const response = await api.post(`/memory/${entityId}/search`, {
            query,
        });
        return response.data;
    },

    // Write Memory
    write: async (
        entityId: string,
        type: string,
        data: any,
        action: 'create' | 'update' | 'resolve' = 'create'
    ): Promise<any> => {
        const response = await api.post(`/memory/${entityId}/write`, {
            type,
            data,
            action,
        });
        return response.data;
    },

    // Graph Traversal
    traverse: async (entityId: string, nodeId: string, depth: number = 1): Promise<any> => {
        const response = await api.post(`/memory/${entityId}/graph/traverse`, {
            node_id: nodeId,
            depth
        });
        return response.data;
    },

    // Trigger Harvest
    triggerHarvest: async (entityId: string, dryRun: boolean = false): Promise<{ message: string; dry_run: boolean }> => {
        const response = await api.post(`/harvest/${entityId}`, { dry_run: dryRun });
        return response.data?.data ?? response.data;
    },

    // Get Harvest Progress
    getHarvestProgress: async (entityId: string): Promise<any> => {
        const response = await api.get(`/harvest/${entityId}/progress`);
        return response.data?.data ?? response.data;
    },
};

// ─── Dashboard Types ──────────────────────────────────

export interface MemoryEntity {
    id: string;
    name: string;
    entity_type: string;
    last_harvest: string | null;
    created_at: string | null;
}

export interface MemoryStats {
    entity_id: string;
    counts: Record<string, number>;
    embedding_count: number;
    last_harvest: string | null;
}

export interface RecallItem {
    [key: string]: any;
}

export interface DashboardSearchResult {
    type: string;
    similarity?: number;
    [key: string]: any;
}

// ─── Dashboard API Functions ──────────────────────────

export async function getStats(entityId: string): Promise<MemoryStats> {
    const response = await api.get(`/memory/${entityId}/stats`);
    return response.data;
}

export async function listEntities(): Promise<MemoryEntity[]> {
    const response = await api.get('/admin/entities');
    return response.data?.data || response.data || [];
}

export async function recallMemoryDashboard(
    entityId: string,
    type: string,
    query?: string,
    status: string = 'all',
    limit: number = 30,
): Promise<RecallItem[]> {
    const response = await api.post(`/memory/${entityId}/recall`, {
        type, query, status, limit,
    });
    return response.data?.data || response.data || [];
}

export async function searchMemoriesDashboard(
    entityId: string,
    query: string,
    types?: string[],
    limit: number = 20,
): Promise<DashboardSearchResult[]> {
    const response = await api.post(`/memory/${entityId}/search`, {
        query, types, limit,
    });
    return response.data?.data || response.data || [];
}
