/**
 * Memory Service V2 for Frontend
 * 
 * Client for the V2 memory system with hierarchical banks,
 * entity types, relationships, and proposals.
 * 
 * All calls go through the local PostgreSQL-backed REST API.
 */

import { getToken } from '../auth';

const API_URL = (import.meta as any).env?.VITE_MEMORY_API_URL || 'http://localhost:8000';
const API_KEY = (import.meta as any).env?.VITE_MEMORY_API_KEY || '';

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

async function apiGet<T = any>(endpoint: string): Promise<T> {
    const res = await fetch(`${API_URL}${endpoint}`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${getToken()}`,
            ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        },
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`API ${endpoint} failed (${res.status}): ${text}`);
    }
    return res.json();
}

// ============================================================================
// TYPES
// ============================================================================

export type EntityType = 'agent' | 'human';
export type BankCategory = 'persona' | 'history' | 'emotional' | 'lifestyle' | 'life_states' | 'relationships';

export interface MemoryMeta {
    entityId: string;
    entityType: EntityType;
    name: string;
    schemaVersion: string;
    createdAt: any;
    lastHarvest: any | null;
    warmBanks: Record<string, string[]>;
    coldBanks: Record<string, string>;
    capabilities: {
        canRetrieveCold: boolean;
        canProposeMemoryType: boolean;
        editableBanks: string[];
    };
    pendingProposals: MemoryProposal[];
    customTypes: CustomTypeEntry[];
}

export interface MemoryProposal {
    id: string;
    name: string;
    category: BankCategory;
    description: string;
    proposedBy: string;
    proposedAt: any;
    initialContent: any;
    status: 'pending' | 'approved' | 'declined';
}

export interface CustomTypeEntry {
    path: string;
    addedBy: 'user' | 'agent';
    addedAt: any;
}

export interface WarmMemory {
    [bankName: string]: {
        [docName: string]: any;
    };
}

// ============================================================================
// INITIALIZATION
// ============================================================================

/**
 * Initialize memory for an entity (agent or human)
 */
export async function initializeEntityMemory(
    entityId: string,
    entityType: EntityType,
    entityName: string
): Promise<void> {
    await apiCall('/memory/v2/initialize', { entityId, entityType, entityName });
}

// ============================================================================
// META / SELF-AWARENESS
// ============================================================================

/**
 * Get entity meta (table of contents)
 */
export async function getEntityMeta(entityId: string): Promise<MemoryMeta | null> {
    const data = await apiCall<{ success: boolean; meta: MemoryMeta | null }>(
        '/memory/v2/meta', { entityId }
    );
    return data.meta;
}

// ============================================================================
// WARM MEMORY OPERATIONS
// ============================================================================

/**
 * Get all warm memory for an entity
 * @param sessionParticipants Optional: filter relationships to only these participants
 */
export async function getWarmMemory(
    entityId: string,
    sessionParticipants?: string[]
): Promise<WarmMemory> {
    const data = await apiCall<{ success: boolean; warmMemory: WarmMemory }>(
        '/memory/v2/warm', { entityId, sessionParticipants }
    );
    return data.warmMemory;
}

/**
 * Get a specific memory document
 */
export async function getMemoryDocument(
    entityId: string,
    bankName: string,
    docName: string
): Promise<any | null> {
    const data = await apiCall<{ success: boolean; content: any }>(
        '/memory/v2/document', { entityId, bankName, docName }
    );
    return data.content;
}

/**
 * Update a memory document
 */
export async function updateMemoryDocument(
    entityId: string,
    bankName: string,
    docName: string,
    content: any,
    merge: boolean = true
): Promise<void> {
    await apiCall('/memory/v2/document/update', { entityId, bankName, docName, content, merge });
}

// ============================================================================
// RELATIONSHIPS
// ============================================================================

/**
 * Update relationship data
 */
export async function updateRelationship(
    entityId: string,
    targetId: string,
    data: {
        targetType?: EntityType;
        targetName?: string;
        style?: string;
        trustLevel?: number;
        profile?: any;
        dynamics?: any;
        narratives?: any;
        history?: any;
    }
): Promise<void> {
    await apiCall('/memory/v2/relationship/update', { entityId, targetId, data });
}

// ============================================================================
// CUSTOM TYPES
// ============================================================================

/**
 * Create a custom memory type
 */
export async function createCustomMemoryType(
    entityId: string,
    config: {
        bankName: string;
        docName: string;
        description?: string;
        initialContent?: any;
        addedBy: 'user' | 'agent';
    }
): Promise<void> {
    await apiCall('/memory/v2/custom-type', { entityId, ...config });
}

// ============================================================================
// PROPOSALS
// ============================================================================

/**
 * Submit a memory proposal (typically from agent during chat)
 */
export async function submitMemoryProposal(
    entityId: string,
    proposal: {
        name: string;
        category: BankCategory;
        description: string;
        initialContent?: any;
    }
): Promise<string> {
    const data = await apiCall<{ success: boolean; proposalId: string }>(
        '/memory/v2/proposal/submit', { entityId, ...proposal }
    );
    return data.proposalId;
}

/**
 * Approve or decline a proposal
 */
export async function resolveProposal(
    entityId: string,
    proposalId: string,
    approved: boolean
): Promise<void> {
    await apiCall('/memory/v2/proposal/resolve', { entityId, proposalId, approved });
}

// ============================================================================
// BATCH OPERATIONS
// ============================================================================

/**
 * Get all entities for the current user
 */
export async function getAllEntities(): Promise<MemoryMeta[]> {
    const data = await apiCall<{ success: boolean; entities: MemoryMeta[] }>(
        '/memory/v2/entities'
    );
    return data.entities;
}

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Format warm memory into a prompt-friendly string
 */
export function formatWarmMemoryForPrompt(warmMemory: WarmMemory): string {
    const sections: string[] = [];

    for (const [bankName, docs] of Object.entries(warmMemory)) {
        if (bankName === 'relationships') continue; // Handle separately

        for (const [docName, content] of Object.entries(docs)) {
            if (content && Object.keys(content).length > 0) {
                sections.push(`=== ${bankName.toUpperCase()} / ${docName.replace(/_/g, ' ').toUpperCase()} ===`);
                sections.push(JSON.stringify(content, null, 2));
            }
        }
    }

    // Add relationships
    if (warmMemory.relationships) {
        for (const [targetId, data] of Object.entries(warmMemory.relationships)) {
            if (data && Object.keys(data).length > 0) {
                sections.push(`=== RELATIONSHIP: ${(data as any).targetName || targetId} ===`);
                sections.push(JSON.stringify(data, null, 2));
            }
        }
    }

    return sections.join('\n\n');
}

/**
 * Get default bank structure for an entity type
 */
export function getDefaultBanks(entityType: EntityType): Record<string, string[]> {
    if (entityType === 'agent') {
        return {
            persona: ['identity', 'values', 'goals', 'lexicon'],
            history: ['lifetime_summary', 'seasonal_summary', 'recent_summary'],
            emotional: ['current_state', 'triggers', 'coping', 'loops', 'boundaries']
        };
    } else {
        return {
            self: ['identity', 'attachment', 'boundaries'],
            lifestyle: ['schedule', 'health', 'social', 'challenges', 'support_needs'],
            life_states: ['current', 'transitions'],
            emotional: ['loops', 'coping']
        };
    }
}

// ============================================================================
// COMPRESSED MEMORY
// ============================================================================

export interface CompressedMemoryResult {
    markdown: string;
    lastCompressed: any;
    exists: boolean;
}

export interface CompressOnDemandResult {
    success: boolean;
    characterCount: number;
    error?: string;
}

/**
 * Get compressed memory (Markdown character sheet) for an entity
 * Falls back to empty string if not yet compressed
 */
export async function getCompressedMemory(entityId: string): Promise<CompressedMemoryResult> {
    try {
        const data = await apiCall<{ success: boolean; markdown: string; lastCompressed: any; exists: boolean }>(
            '/memory/v2/compressed', { entityId }
        );
        return {
            markdown: data.markdown || '',
            lastCompressed: data.lastCompressed,
            exists: data.exists
        };
    } catch (error) {
        console.warn('Could not get compressed memory:', error);
        return { markdown: '', lastCompressed: null, exists: false };
    }
}

/**
 * Compress memory on-demand with custom options
 */
export async function compressMemoryOnDemand(
    entityId: string,
    options?: { characterLimit?: number; model?: 'gemini' | 'openai' }
): Promise<CompressOnDemandResult> {
    const data = await apiCall<{ success: boolean; characterCount: number; error?: string }>(
        '/memory/v2/compress', {
            entityId,
            characterLimit: options?.characterLimit,
            model: options?.model
        }
    );

    return {
        success: data.success,
        characterCount: data.characterCount,
        error: data.error
    };
}
