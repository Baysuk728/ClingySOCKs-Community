

const API_URL = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

const getHeaders = () => ({
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {})
});

export interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string | { type: string; text?: string; image_url?: { url: string } }[];
    timestamp?: number;
}

export interface ChatStreamEvent {
    type?: 'start' | 'content' | 'content_replace' | 'thinking' | 'tool_call' | 'tool_result' | 'done' | 'error';
    content?: string;
    thinking?: string;
    name?: string;        // tool_call / tool_result name
    arguments?: string;   // tool_call arguments
    result?: string;      // tool_result result
    full_content?: string; // done event
    model?: string;       // start event
    context_metadata?: any; // start event
    tool_call?: {
        function: {
            name: string;
            arguments: string;
        };
    };
    done?: boolean;
    error?: string;
}

export const chatApi = {
    streamChat: async (
        entityId: string,
        messages: ChatMessage[],
        onEvent: (event: ChatStreamEvent) => void,
        onError: (error: any) => void,
        options: {
            model?: string;
            temperature?: number;
            user_id?: string; // For dossier lookup
            chat_id?: string; // For history backfill
            abortController?: AbortController; // External abort controller for stop button
        } = {}
    ) => {
        const ctrl = options.abortController || new AbortController();

        // Ensure messages have timestamps for gap calculation (if not present)
        const messagesWithTime = messages.map(m => ({
            ...m,
            timestamp: m.timestamp || Date.now() / 1000
        }));

        try {
            // Use fetch-event-source logic or standard fetch with readable stream
            // Standard fetch is often easier for simple SSE if we don't need auto-retry complexity
            const response = await fetch(`${API_URL}/chat/${entityId}`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    entity_id: entityId,
                    messages: messagesWithTime,
                    stream: true,
                    ...options
                }),
                signal: ctrl.signal,
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Api Error: ${response.status} ${errorText}`);
            }

            const reader = response.body?.getReader();
            if (!reader) throw new Error('No response body');

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.trim() === '') continue;
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        if (dataStr === '[DONE]') {
                            onEvent({ done: true });
                            continue;
                        }
                        try {
                            const data = JSON.parse(dataStr);
                            onEvent(data);
                        } catch (e) {
                            console.error('Failed to parse SSE line:', line, e);
                        }
                    }
                }
            }

            onEvent({ done: true });

        } catch (err: any) {
            if (err.name === 'AbortError') {
                console.log('Stream aborted');
                return;
            }
            onError(err);
        }
    },

    fetchHistory: async (entityId: string, limit: number = 50, offset: number = 0): Promise<{ messages: any[]; total: number }> => {
        try {
            const response = await fetch(`${API_URL}/messages/${entityId}?limit=${limit}&offset=${offset}`, {
                headers: getHeaders()
            });
            if (!response.ok) {
                throw new Error('Failed to fetch history');
            }
            const data = await response.json();
            return { messages: data.messages || [], total: data.total || 0 };
        } catch (error) {
            console.error("Fetch History Error:", error);
            return { messages: [], total: 0 };
        }
    },

    fetchConversations: async (userId: string, limit: number = 50, offset: number = 0): Promise<any[]> => {
        try {
            const response = await fetch(`${API_URL}/conversations/?user_id=${userId}&limit=${limit}&offset=${offset}`, {
                headers: getHeaders()
            });
            if (!response.ok) {
                throw new Error('Failed to fetch conversations');
            }
            const data = await response.json();
            return data.conversations || [];
        } catch (error) {
            console.error("Fetch Conversations Error:", error);
            return [];
        }
    },

    createConversation: async (entityId: string, title: string): Promise<{ id: string; title: string; entity_id: string }> => {
        const response = await fetch(`${API_URL}/conversations/`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ entity_id: entityId, title }),
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to create conversation: ${response.status} ${errorText}`);
        }
        return response.json();
    },

    deleteConversation: async (conversationId: string): Promise<void> => {
        const response = await fetch(`${API_URL}/conversations/${conversationId}`, {
            method: 'DELETE',
            headers: getHeaders()
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to delete conversation: ${response.status} ${errorText}`);
        }
    },

    previewImport: async (file: File): Promise<ImportPreviewResponse> => {
        const formData = new FormData();
        formData.append('file', file);

        const headers: Record<string, string> = {};
        if (API_KEY) headers['X-API-Key'] = API_KEY;

        const response = await fetch(`${API_URL}/import/preview`, {
            method: 'POST',
            headers,
            body: formData,
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Import preview failed: ${response.status} ${errorText}`);
        }
        return response.json();
    },

    executeImport: async (
        file: File,
        entityId: string,
        userId: string,
        conversationIds: string[] | '*'
    ): Promise<ImportResult> => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('entity_id', entityId);
        formData.append('user_id', userId);
        formData.append('conversation_ids', conversationIds === '*' ? '*' : JSON.stringify(conversationIds));

        const headers: Record<string, string> = {};
        if (API_KEY) headers['X-API-Key'] = API_KEY;

        const response = await fetch(`${API_URL}/import/execute`, {
            method: 'POST',
            headers,
            body: formData,
        });
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Import failed: ${response.status} ${errorText}`);
        }
        return response.json();
    },
};

// Import types
export interface ImportConversationPreview {
    original_id: string;
    import_id: string;
    title: string;
    message_count: number;
    created_at: string | null;
    source_format: string;
    first_message_preview: string | null;
}

export interface ImportPreviewResponse {
    format: string;
    conversations: ImportConversationPreview[];
    total_conversations: number;
    total_messages: number;
}

export interface ImportResult {
    imported: number;
    skipped: number;
    total_messages: number;
    errors: string[];
}
