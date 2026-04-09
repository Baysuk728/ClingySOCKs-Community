/**
 * Memory Service for Frontend (Legacy V1)
 * 
 * Provides access to memory management via the local REST API.
 * Handles warm memory loading, updates, and cold memory search.
 */

import { getToken } from '../auth';

import { getApiUrlSync, API_KEY } from './apiConfig';

const API_URL = getApiUrlSync();

/** Convenience wrapper for authenticated API calls */
async function apiCall<T = any>(endpoint: string, body?: any): Promise<T> {
    const res = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`,
            ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`API ${endpoint} failed (${res.status}): ${text}`);
    }
    return res.json();
}

// Type definitions
export interface MemoryType {
    id: string;
    name: string;
    description: string;
    loadOnStart: boolean;
    updateTrigger: 'realtime' | 'session_end' | 'nightly';
    createdBy: 'system' | 'user' | 'agent';
}

export interface WarmMemory {
    identity?: {
        name: string;
        coreValues: string[];
        role: string;
        mission: string;
        personalityTraits: string[];
    };
    style?: {
        tone: string;
        verbosity: string;
        useMetaphors: boolean;
        vocabulary: string[];
        insideJokes: string[];
        preferredGreeting: string;
    };
    emotional_state?: {
        currentMood: string;
        energyLevel: number;
        lastInteractionSentiment: string;
        context: string;
    };
    warm_cache?: {
        messages: Array<{
            summary: string;
            importance: string;
            timestamp: any;
        }>;
        maxMessages: number;
    };
    recent_summary?: {
        content: string;
        turnCount: number;
        lastTopics: string[];
    };
    lifetime_summary?: {
        content: string;
        majorThemes: string[];
        milestones: string[];
    };
    table_of_contents?: {
        sections: string[];
        lastGenerated: any;
    };
    [key: string]: any;
}

export interface TimelineEntry {
    id: string;
    summary: string;
    coldMemoryRef?: string;
    importance: 'low' | 'medium' | 'high' | 'critical';
    timestamp: any;
    tags?: string[];
}

export interface SearchResult {
    id: string;
    score: number;
    content: string;
    metadata: {
        timestamp: string;
        importance?: string;
        tags?: string[];
        title?: string;
    };
}

/**
 * Initialize memory system for a new persona
 */
export async function initializePersonaMemory(personaId: string, personaName: string): Promise<void> {
    try {
        await apiCall('/memory/initialize', { personaId, personaName });
        console.log(`✅ Memory initialized for persona: ${personaName}`);
    } catch (error) {
        console.error('Failed to initialize persona memory:', error);
        throw error;
    }
}

/**
 * Get all warm memories for a persona (loaded at session start)
 */
export async function getWarmMemory(personaId: string): Promise<WarmMemory> {
    try {
        const data = await apiCall<{ success: boolean; memory: WarmMemory }>(
            '/memory/warm', { personaId }
        );
        return data.memory || {};
    } catch (error) {
        console.error('Failed to get warm memory:', error);
        return {};
    }
}

/**
 * Get a specific memory type
 */
export async function getMemory(personaId: string, typeId: string): Promise<any> {
    try {
        const data = await apiCall<{ success: boolean; content: any }>(
            '/memory/get', { personaId, typeId }
        );
        return data.content;
    } catch (error) {
        console.error(`Failed to get memory ${typeId}:`, error);
        return null;
    }
}

/**
 * Update a memory
 */
export async function updateMemory(
    personaId: string,
    typeId: string,
    content: any,
    merge: boolean = true
): Promise<void> {
    try {
        await apiCall('/memory/update', { personaId, typeId, content, merge });
    } catch (error) {
        console.error(`Failed to update memory ${typeId}:`, error);
        throw error;
    }
}

/**
 * Add a delta to the warm cache (real-time update)
 */
export async function addToWarmCache(
    personaId: string,
    summary: string,
    importance: 'low' | 'medium' | 'high' | 'critical' = 'medium'
): Promise<void> {
    try {
        await apiCall('/memory/warm-cache/add', { personaId, summary, importance });
    } catch (error) {
        console.error('Failed to add to warm cache:', error);
        // Non-critical, don't throw
    }
}

/**
 * Create a new custom memory type
 */
export async function createMemoryType(
    personaId: string,
    config: {
        name: string;
        description: string;
        loadOnStart?: boolean;
        updateTrigger?: 'realtime' | 'session_end' | 'nightly';
        initialContent?: any;
    }
): Promise<string> {
    try {
        const data = await apiCall<{ success: boolean; typeId: string }>(
            '/memory/type/create', { personaId, ...config }
        );
        return data.typeId;
    } catch (error) {
        console.error('Failed to create memory type:', error);
        throw error;
    }
}

/**
 * Get all memory types for a persona
 */
export async function getMemoryRegistry(personaId: string): Promise<MemoryType[]> {
    try {
        const data = await apiCall<{ success: boolean; registry: MemoryType[] }>(
            '/memory/registry', { personaId }
        );
        return data.registry || [];
    } catch (error) {
        console.error('Failed to get memory registry:', error);
        return [];
    }
}

/**
 * Add a timeline entry
 */
export async function addTimelineEntry(
    personaId: string,
    entry: {
        summary: string;
        importance: 'low' | 'medium' | 'high' | 'critical';
        coldMemoryRef?: string;
        tags?: string[];
    }
): Promise<string> {
    try {
        const data = await apiCall<{ success: boolean; entryId: string }>(
            '/memory/timeline/add', { personaId, ...entry }
        );
        return data.entryId;
    } catch (error) {
        console.error('Failed to add timeline entry:', error);
        throw error;
    }
}

/**
 * Get recent timeline entries
 */
export async function getTimeline(personaId: string, limit: number = 20): Promise<TimelineEntry[]> {
    try {
        const data = await apiCall<{ success: boolean; timeline: TimelineEntry[] }>(
            '/memory/timeline', { personaId, limit }
        );
        return data.timeline || [];
    } catch (error) {
        console.error('Failed to get timeline:', error);
        return [];
    }
}

/**
 * Store memory in cold storage
 */
export async function storeColdMemory(
    personaId: string,
    content: string,
    type: 'conversation' | 'artifact' | 'echo',
    metadata?: {
        importance?: 'low' | 'medium' | 'high' | 'critical';
        tags?: string[];
        title?: string;
        sessionId?: string;
    }
): Promise<string> {
    try {
        const data = await apiCall<{ success: boolean; memoryId: string }>(
            '/memory/cold/store', { personaId, content, type, metadata }
        );
        return data.memoryId;
    } catch (error) {
        console.error('Failed to store cold memory:', error);
        throw error;
    }
}

/**
 * Search cold memories semantically
 */
export async function searchColdMemory(
    personaId: string,
    query: string,
    options?: {
        type?: 'conversation' | 'artifact' | 'echo';
        topK?: number;
    }
): Promise<SearchResult[]> {
    try {
        const data = await apiCall<{ success: boolean; results: SearchResult[] }>(
            '/memory/cold/search', { personaId, query, ...options }
        );
        return data.results || [];
    } catch (error) {
        console.error('Failed to search cold memory:', error);
        return [];
    }
}

/**
 * Build context string from warm memory for AI prompts
 */
export function buildContextFromWarmMemory(warmMemory: WarmMemory): string {
    const parts: string[] = [];

    if (warmMemory.identity) {
        parts.push(`## Your Identity
Name: ${warmMemory.identity.name}
Role: ${warmMemory.identity.role}
Mission: ${warmMemory.identity.mission}
Core Values: ${warmMemory.identity.coreValues?.join(', ') || 'Not defined'}
Personality: ${warmMemory.identity.personalityTraits?.join(', ') || 'Not defined'}`);
    }

    if (warmMemory.lifetime_summary?.content) {
        parts.push(`## Your Journey So Far
${warmMemory.lifetime_summary.content}`);
    }

    if (warmMemory.recent_summary?.content) {
        parts.push(`## Recent Conversation Summary
${warmMemory.recent_summary.content}`);
    }

    if (warmMemory.emotional_state) {
        parts.push(`## Current State
Mood: ${warmMemory.emotional_state.currentMood}
Energy: ${Math.round(warmMemory.emotional_state.energyLevel * 100)}%`);
    }

    if (warmMemory.warm_cache?.messages?.length) {
        const recentDeltas = warmMemory.warm_cache.messages
            .slice(-5)
            .map(m => `- ${m.summary}`)
            .join('\n');
        parts.push(`## Recent Highlights
${recentDeltas}`);
    }

    if (warmMemory.style) {
        parts.push(`## Communication Style
Tone: ${warmMemory.style.tone}
Verbosity: ${warmMemory.style.verbosity}
Use Metaphors: ${warmMemory.style.useMetaphors ? 'Yes' : 'No'}`);
    }

    return parts.join('\n\n');
}
