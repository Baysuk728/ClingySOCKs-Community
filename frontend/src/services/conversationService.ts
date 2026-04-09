/**
 * Conversation Service for Frontend
 * 
 * Unified conversation storage via the local PostgreSQL-backed REST API.
 * Both Chat page and Harvest use the same data source.
 */

import { getToken, getCurrentUser } from '../auth';

import { getApiUrlSync, API_KEY } from './apiConfig';

const API_URL = getApiUrlSync();

/** Convenience wrapper for authenticated API calls */
async function apiCall<T = any>(endpoint: string, method: string = 'POST', body?: any): Promise<T> {
    const res = await fetch(`${API_URL}${endpoint}`, {
        method,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`,
            ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
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

// New state machine for harvest tracking
export type HarvestState = 'idle' | 'delta_detected' | 'processing';

// Legacy status (for backward compatibility)
export type HarvestStatus = 'not_harvested' | 'partially_harvested' | 'harvested';

export interface ConversationMessage {
    id: string;
    senderId: string;  // 'user' or agentId
    content: string;
    timestamp: Date | string;
}

export interface Conversation {
    id: string;
    title: string;
    participants: string[];  // [agentId]
    isGroup: boolean;
    createdAt: Date | string;
    updatedAt: Date | string;
    messages: ConversationMessage[];

    // Harvest tracking
    harvestStatus?: HarvestState | HarvestStatus;
    lastHarvestedMessageIndex?: number;
    lastHarvestAt?: Date | string;
    totalHarvests?: number;

    // DEPRECATED: Use getConversationHarvestLog() instead
    lastHarvestDeltas?: any;

    // Import tracking
    imported?: boolean;
    source?: string;

    // Archive (soft delete)
    isArchived?: boolean;
}

export interface ConversationSummary {
    id: string;
    title: string;
    participants: string[];
    messageCount: number;
    updatedAt: Date;
    harvestStatus: HarvestStatus;
    lastHarvestAt?: Date;
    lastHarvestedMessageIndex?: number;
    isArchived?: boolean;
    isGroup?: boolean;
}

// ============================================================================
// HELPERS
// ============================================================================

function toDate(val: any): Date {
    if (!val) return new Date();
    if (val instanceof Date) return val;
    if (typeof val === 'string') return new Date(val);
    // Handle multiple date object shapes
    if (val.seconds) return new Date(val.seconds * 1000);
    return new Date();
}

function deriveHarvestStatus(lastHarvestedIdx: number | undefined, messageCount: number): HarvestStatus {
    if (lastHarvestedIdx === undefined || lastHarvestedIdx < 0) return 'not_harvested';
    if (lastHarvestedIdx >= messageCount - 1) return 'harvested';
    return 'partially_harvested';
}

function mapConversationSummary(raw: any): ConversationSummary {
    const messageCount = raw.messageCount ?? (raw.messages || []).length;
    return {
        id: raw.id,
        title: raw.title || `Conversation ${(raw.id || '').slice(0, 8)}`,
        participants: raw.participants || [],
        messageCount,
        updatedAt: toDate(raw.updatedAt),
        harvestStatus: raw.harvestStatus || deriveHarvestStatus(raw.lastHarvestedMessageIndex, messageCount),
        lastHarvestAt: raw.lastHarvestAt ? toDate(raw.lastHarvestAt) : undefined,
        lastHarvestedMessageIndex: raw.lastHarvestedMessageIndex,
        isArchived: raw.isArchived || false,
        isGroup: raw.isGroup || (raw.participants?.length > 1),
    };
}

function mapConversation(raw: any): Conversation {
    return {
        id: raw.id,
        title: raw.title || raw.name || `Conversation ${(raw.id || '').slice(0, 8)}`,
        participants: raw.participants || [],
        isGroup: raw.isGroup || false,
        createdAt: toDate(raw.createdAt),
        updatedAt: toDate(raw.updatedAt),
        messages: (raw.messages || []).map((msg: any, idx: number) => ({
            id: msg.id || `msg-${idx}`,
            senderId: msg.senderId,
            content: msg.content,
            timestamp: toDate(msg.timestamp),
        })),
        harvestStatus: raw.harvestStatus || 'not_harvested',
        lastHarvestAt: raw.lastHarvestAt ? toDate(raw.lastHarvestAt) : undefined,
        lastHarvestDeltas: raw.lastHarvestDeltas,
        lastHarvestedMessageIndex: raw.lastHarvestedMessageIndex,
        totalHarvests: raw.totalHarvests,
        imported: raw.imported,
        source: raw.source,
        isArchived: raw.isArchived,
    };
}

// ============================================================================
// CRUD OPERATIONS
// ============================================================================

/**
 * Get conversations for a specific agent
 */
export async function getConversationsForAgent(agentId: string): Promise<ConversationSummary[]> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    const data = await apiCall<{ conversations: any[] }>(
        '/conversations/list', 'POST', { agentId }
    );
    return (data.conversations || []).map(mapConversationSummary);
}

/**
 * Get a single conversation with full messages
 */
export async function getConversation(conversationId: string): Promise<Conversation | null> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    try {
        const data = await apiCall<any>(`/conversations/${conversationId}`, 'GET');
        if (!data || !data.id) return null;
        return mapConversation(data);
    } catch {
        return null;
    }
}

/**
 * Create a new conversation
 */
export async function createConversation(
    agentId: string,
    title?: string
): Promise<string> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    const data = await apiCall<{ id: string }>(
        '/conversations/create', 'POST', {
            title: title || `Chat with ${agentId}`,
            participants: [agentId],
            isGroup: false,
        }
    );
    return data.id;
}

/**
 * Add a message to a conversation
 */
export async function addMessage(
    conversationId: string,
    senderId: string,
    content: string
): Promise<void> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    await apiCall(`/conversations/${conversationId}/messages`, 'POST', {
        senderId,
        content,
    });
}

/**
 * Update conversation title
 */
export async function updateConversationTitle(
    conversationId: string,
    title: string
): Promise<void> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    await apiCall(`/conversations/${conversationId}`, 'PATCH', { title });
}

/**
 * Delete a conversation
 */
export async function deleteConversation(conversationId: string): Promise<void> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    await apiCall(`/conversations/${conversationId}`, 'DELETE');
}

/**
 * Delete multiple conversations
 */
export async function deleteConversations(conversationIds: string[]): Promise<void> {
    for (const id of conversationIds) {
        await deleteConversation(id);
    }
}

/**
 * Get harvest log for a conversation
 */
export async function getConversationHarvestLog(conversationId: string): Promise<{
    latest: any | null;
    history: any[];
}> {
    try {
        const data = await apiCall<{ success: boolean; latest: any; history: any[] }>(
            `/conversations/${conversationId}/harvest-logs`, 'GET'
        );

        if (data.success) {
            return {
                latest: data.latest,
                history: data.history
            };
        }

        return { latest: null, history: [] };
    } catch (error) {
        console.error('Failed to get harvest logs:', error);
        return { latest: null, history: [] };
    }
}

// ============================================================================
// REAL-TIME SUBSCRIPTIONS (polling-based service)
// ============================================================================

/**
 * Subscribe to conversations for an agent.
 * 
 * This uses polling to provide real-time-like updates.
 * Returns an unsubscribe function.
 */
export function subscribeToConversations(
    agentId: string,
    callback: (conversations: ConversationSummary[]) => void,
    pollIntervalMs: number = 5000
): () => void {
    const user = getCurrentUser();
    if (!user) {
        console.warn('Not authenticated, cannot subscribe to conversations');
        return () => { };
    }

    let active = true;

    const poll = async () => {
        if (!active) return;
        try {
            const convs = await getConversationsForAgent(agentId);
            if (active) callback(convs);
        } catch (error) {
            console.warn('Poll conversations failed:', error);
        }
    };

    // Initial fetch
    poll();
    // Subsequent polls
    const interval = setInterval(poll, pollIntervalMs);

    return () => {
        active = false;
        clearInterval(interval);
    };
}

/**
 * Subscribe to a single conversation (polling-based)
 */
export function subscribeToConversation(
    conversationId: string,
    callback: (conversation: Conversation | null) => void,
    pollIntervalMs: number = 3000
): () => void {
    const user = getCurrentUser();
    if (!user) {
        console.warn('Not authenticated, cannot subscribe to conversation');
        return () => { };
    }

    let active = true;

    const poll = async () => {
        if (!active) return;
        try {
            const conv = await getConversation(conversationId);
            if (active) callback(conv);
        } catch {
            if (active) callback(null);
        }
    };

    poll();
    const interval = setInterval(poll, pollIntervalMs);

    return () => {
        active = false;
        clearInterval(interval);
    };
}

// ============================================================================
// UNIFIED CHAT LIST FUNCTIONS
// ============================================================================

/**
 * Get ALL conversations for the current user (unified chat list)
 * Optionally filters by search term and archive status
 */
export async function getAllConversations(options?: {
    search?: string;
    includeArchived?: boolean;
}): Promise<ConversationSummary[]> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    const data = await apiCall<{ conversations: any[] }>(
        '/conversations/list', 'POST', {
            includeArchived: options?.includeArchived,
            search: options?.search,
        }
    );

    let results = (data.conversations || []).map(mapConversationSummary);

    // Client-side fallback filter
    if (!options?.includeArchived) {
        results = results.filter(c => !c.isArchived);
    }
    if (options?.search) {
        const searchLower = options.search.toLowerCase();
        results = results.filter(c =>
            c.title.toLowerCase().includes(searchLower) ||
            c.participants.some((p: string) => p.toLowerCase().includes(searchLower))
        );
    }

    return results;
}

/**
 * Subscribe to ALL conversations (polling-based)
 */
export function subscribeToAllConversations(
    callback: (conversations: ConversationSummary[]) => void,
    options?: { includeArchived?: boolean },
    pollIntervalMs: number = 5000
): () => void {
    const user = getCurrentUser();
    if (!user) {
        console.warn('Not authenticated, cannot subscribe to conversations');
        return () => { };
    }

    let active = true;

    const poll = async () => {
        if (!active) return;
        try {
            const convs = await getAllConversations({ includeArchived: options?.includeArchived });
            if (active) callback(convs);
        } catch (error) {
            console.warn('Poll all conversations failed:', error);
        }
    };

    poll();
    const interval = setInterval(poll, pollIntervalMs);

    return () => {
        active = false;
        clearInterval(interval);
    };
}

/**
 * Archive a conversation (soft delete)
 */
export async function archiveConversation(conversationId: string): Promise<void> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    await apiCall(`/conversations/${conversationId}`, 'PATCH', { isArchived: true });
}

/**
 * Unarchive a conversation
 */
export async function unarchiveConversation(conversationId: string): Promise<void> {
    const user = getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    await apiCall(`/conversations/${conversationId}`, 'PATCH', { isArchived: false });
}
