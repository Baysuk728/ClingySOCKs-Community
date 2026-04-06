import { Agent, Message, ApiKeyConfig } from "../types";
import { auth } from "../auth";

// Memory API base URL (same as chatApi.ts)
const MEMORY_API_URL = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

const getHeaders = (json = false): Record<string, string> => ({
  ...(json ? { 'Content-Type': 'application/json' } : {}),
  ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

// Note: API_BASE_URL only used for legacy endpoints (harvest, memory-engine)
// Legacy API base URL (kept for backward compatibility)
const API_BASE_URL = '/api';

/**
 * Generic API call helper for memory backend endpoints
 */
export const apiCall = async (
  endpoint: string,
  options?: {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    body?: string;
    headers?: Record<string, string>;
  }
): Promise<any> => {
  const method = options?.method || 'GET';
  const url = endpoint.startsWith('http') ? endpoint : `${MEMORY_API_URL}${endpoint}`;
  
  const headers: Record<string, string> = {
    ...getHeaders(true),
    ...options?.headers,
  };

  console.log(`🌐 ${method} ${url}`);
  
  const response = await fetch(url, {
    method,
    headers,
    ...(options?.body && { body: options.body }),
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({ error: 'Unknown error' }));
    const errorMsg = errData.detail || errData.error || `API request failed: ${response.status}`;
    console.error(`❌ API Error: ${errorMsg}`, errData);
    throw new Error(errorMsg);
  }

  const data = await response.json();
  console.log(`✅ Response OK:`, data);
  return data;
};

// Legacy function — generateAgentResponse is replaced by chatApi.streamChat
// Kept as stub for backward compatibility
export const generateAgentResponse = async (
  agent: Agent,
  history: Message[],
  _apiKey?: string,
  context?: string
): Promise<string> => {
  return `[Legacy function deprecated — use chatApi.streamChat instead]`;
};

// Legacy function - kept for backward compatibility
export const getApiKeyForAgent = (
  agent: Agent,
  apiKeys: ApiKeyConfig[]
): string | undefined => {
  const providerKeys = apiKeys.filter(k => k.provider === agent.provider);
  if (providerKeys.length === 0) {
    console.warn(`No API key configured for provider: ${agent.provider}`);
    return undefined;
  }
  const defaultKey = providerKeys.find(k => k.isDefault) || providerKeys[0];
  return defaultKey.apiKey;
};

export const healthCheck = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
};

// ============================================================================
// MEMORY HARVEST API
// ============================================================================

export interface HarvestResult {
  success: boolean;
  persona_id: string;
  persona_name: string;
  total_processed: number;
  auto_approved: number;
  proposed: number;
  skipped: number;
  chunks_processed: number;
  decisions: MemoryDecision[];
  auto_approved_decisions: MemoryDecision[];
  proposed_decisions: MemoryDecision[];
  // New unified harvester fields
  total_messages?: number;
  total_chunks?: number;
  total_deltas?: number;
  total_artifacts?: number;
  summary_manager_result?: any;
  artifact_sync_result?: any;
  error?: string;
}

export interface MemoryDecision {
  should_remember: boolean;
  confidence: number;
  reasoning: string;
  memory_content: string;
  memory_domain?: string;
  memory_subtype?: string;
  importance: string;
}

export interface SaveMemoriesResult {
  success: boolean;
  created_count: number;
  memory_ids: string[];
  embedded_count: number;
}

export const processHarvest = async (
  fileContent: string,
  personaId: string,
  personaName: string,
  useSemanticChunking: boolean = true
): Promise<HarvestResult> => {
  try {
    const response = await fetch(`${API_BASE_URL}/harvest/process`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        file_content: fileContent,
        persona_id: personaId,
        persona_name: personaName,
        use_semantic_chunking: useSemanticChunking
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to process harvest');
    }

    return await response.json();
  } catch (error) {
    console.error("Harvest Error:", error);
    throw error;
  }
};

export const approveMemories = async (
  personaId: string,
  decisions: MemoryDecision[]
): Promise<SaveMemoriesResult> => {
  try {
    const response = await fetch(`${API_BASE_URL}/harvest/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        persona_id: personaId,
        decisions
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to save memories');
    }

    return await response.json();
  } catch (error) {
    console.error("Save Memories Error:", error);
    throw error;
  }
};

export const getMemories = async (
  personaId: string,
  limit: number = 50,
  offset: number = 0
): Promise<any[]> => {
  try {
    const response = await fetch(
      `${API_BASE_URL}/memories?persona_id=${personaId}&limit=${limit}&offset=${offset}`
    );

    if (!response.ok) {
      throw new Error('Failed to fetch memories');
    }

    const data = await response.json();
    return data.memories || [];
  } catch (error) {
    console.error("Fetch Memories Error:", error);
    return [];
  }
};

export const searchMemories = async (
  query: string,
  personaId: string,
  limit: number = 10
): Promise<any[]> => {
  try {
    const response = await fetch(`${API_BASE_URL}/memories/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        persona_id: personaId,
        limit
      })
    });

    if (!response.ok) {
      throw new Error('Failed to search memories');
    }

    const data = await response.json();
    return data.results || [];
  } catch (error) {
    console.error("Search Memories Error:", error);
    return [];
  }
};

// ============================================================================
// PERSONA API (PostgreSQL via Memory API)
// ============================================================================

export const getPersonas = async (): Promise<Agent[]> => {
  try {
    const user = auth.currentUser;
    if (!user) throw new Error('Not authenticated');

    const response = await fetch(`${MEMORY_API_URL}/memory/personas?owner_user_id=${user.uid}`, {
      headers: getHeaders(),
    });
    if (!response.ok) throw new Error('Failed to fetch personas');

    const data = await response.json();
    if (!data.success) throw new Error('Failed to fetch personas');

    return (data.personas || []).map((p: any) => ({
      id: p.entity_id,
      name: p.name,
      provider: p.provider || 'gemini',
      modelId: p.model || '',
      voiceId: p.voice_id || '',
      ttsProvider: p.tts_provider || 'google',
      systemPrompt: p.system_prompt || '',
      temperature: p.temperature || 0.7,
      avatar: p.avatar || '🤖',
      role: p.role_description || 'AI Assistant',
      description: p.description || '',
      maxContextChars: p.max_context_chars,
      maxWarmMemory: p.max_warm_memory,
      maxHistoryChars: p.max_history_chars,
      maxHistoryMessages: p.max_history_messages,
      isSystem: false
    }));
  } catch (error) {
    console.error("Get Personas Error:", error);
    return [];
  }
};

export const getPersona = async (personaId: string): Promise<Agent | null> => {
  try {
    const response = await fetch(`${MEMORY_API_URL}/memory/personas/${personaId}`, {
      headers: getHeaders(),
    });
    if (!response.ok) return null;

    const data = await response.json();
    if (!data.success || !data.persona) return null;

    const p = data.persona;
    return {
      id: p.entity_id,
      name: p.name,
      provider: p.provider || 'gemini',
      modelId: p.model || '',
      voiceId: p.voice_id || '',
      ttsProvider: p.tts_provider || 'google',
      systemPrompt: p.system_prompt || '',
      temperature: p.temperature || 0.7,
      avatar: p.avatar || '🤖',
      role: p.role_description || 'AI Assistant',
      description: p.description || '',
      maxContextChars: p.max_context_chars,
      maxWarmMemory: p.max_warm_memory,
      maxHistoryChars: p.max_history_chars,
      maxHistoryMessages: p.max_history_messages,
      isSystem: false
    };
  } catch (error) {
    console.error("Get Persona Error:", error);
    return null;
  }
};

export const createPersona = async (agent: Omit<Agent, 'id'>): Promise<Agent> => {
  try {
    const user = auth.currentUser;
    if (!user) throw new Error('Not authenticated');

    // Generate entity_id from name (kebab-case)
    const entityId = `agent-${(agent.name || 'unnamed').toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${Date.now()}`;

    const response = await fetch(`${MEMORY_API_URL}/memory/personas`, {
      method: 'POST',
      headers: getHeaders(true),
      body: JSON.stringify({
        entity_id: entityId,
        name: agent.name,
        owner_user_id: user.uid,
        model: agent.modelId,
        provider: agent.provider || 'gemini',
        temperature: agent.temperature || 0.7,
        avatar: agent.avatar || '🤖',
        system_prompt: agent.systemPrompt || '',
        voice_id: agent.voiceId || '',
        tts_provider: agent.ttsProvider || 'google',
        role_description: agent.role || 'AI Assistant',
        description: agent.description || '',
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to create persona');
    }

    const data = await response.json();
    const p = data.persona;
    return {
      id: p.entity_id,
      name: p.name,
      provider: p.provider || 'gemini',
      modelId: p.model || '',
      voiceId: p.voice_id || '',
      ttsProvider: p.tts_provider || 'google',
      systemPrompt: p.system_prompt || '',
      temperature: p.temperature || 0.7,
      avatar: p.avatar || agent.avatar || '🤖',
      role: p.role_description || agent.role || 'AI Assistant',
      description: p.description || '',
      maxContextChars: p.max_context_chars,
      maxWarmMemory: p.max_warm_memory,
      maxHistoryChars: p.max_history_chars,
      maxHistoryMessages: p.max_history_messages,
      isSystem: false
    };
  } catch (error) {
    console.error("Create Persona Error:", error);
    throw error;
  }
};

export const updatePersona = async (agent: Agent): Promise<Agent> => {
  try {
    const response = await fetch(`${MEMORY_API_URL}/memory/personas/${agent.id}`, {
      method: 'PUT',
      headers: getHeaders(true),
      body: JSON.stringify({
        name: agent.name,
        model: agent.modelId,
        provider: agent.provider || 'gemini',
        temperature: agent.temperature || 0.7,
        avatar: agent.avatar,
        system_prompt: agent.systemPrompt || '',
        voice_id: agent.voiceId || '',
        tts_provider: agent.ttsProvider || 'google',
        role_description: agent.role || '',
        ...(agent.description ? { description: agent.description } : {}),
        ...(agent.maxContextChars != null ? { max_context_chars: agent.maxContextChars } : {}),
        ...(agent.maxWarmMemory != null ? { max_warm_memory: agent.maxWarmMemory } : {}),
        ...(agent.maxHistoryChars != null ? { max_history_chars: agent.maxHistoryChars } : {}),
        ...(agent.maxHistoryMessages != null ? { max_history_messages: agent.maxHistoryMessages } : {}),
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to update persona');
    }

    const data = await response.json();
    const p = data.persona;
    return {
      id: p.entity_id,
      name: p.name,
      provider: p.provider || 'gemini',
      modelId: p.model || '',
      voiceId: p.voice_id || '',
      ttsProvider: p.tts_provider || 'google',
      systemPrompt: p.system_prompt || '',
      temperature: p.temperature || 0.7,
      avatar: p.avatar || agent.avatar || '🤖',
      role: p.role_description || agent.role || 'AI Assistant',
      description: p.description || '',
      maxContextChars: p.max_context_chars,
      maxWarmMemory: p.max_warm_memory,
      maxHistoryChars: p.max_history_chars,
      maxHistoryMessages: p.max_history_messages,
      isSystem: agent.isSystem || false
    };
  } catch (error) {
    console.error("Update Persona Error:", error);
    throw error;
  }
};

export const deletePersona = async (personaId: string): Promise<void> => {
  try {
    const response = await fetch(`${MEMORY_API_URL}/memory/personas/${personaId}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Failed to delete persona');
    }
  } catch (error) {
    console.error("Delete Persona Error:", error);
    throw error;
  }
};

// ============================================================================
// TEXT-TO-SPEECH API  (proxied through memory backend → /voice/synthesize)
// ============================================================================

export interface SpeechResult {
  audio_url: string;   // relative path: /voice/audio/{cache_key}
  cached: boolean;
  provider: 'google' | 'openai' | 'elevenlabs' | 'local';
  content_type: string;
}

export const generateSpeech = async (
  text: string,
  voiceId: string,
  ttsProvider: 'google' | 'openai' | 'elevenlabs' | 'local' = 'google',
  modelId?: string
): Promise<SpeechResult> => {
  try {
    const response = await fetch(`${MEMORY_API_URL}/voice/synthesize`, {
      method: 'POST',
      headers: getHeaders(true),
      body: JSON.stringify({
        text,
        voice_id: voiceId,
        tts_provider: ttsProvider,
        ...(modelId && { model_id: modelId }),
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `TTS request failed: ${response.status}`);
    }

    const data: SpeechResult = await response.json();
    // Prefix audio_url with backend origin so the browser can fetch it
    data.audio_url = `${MEMORY_API_URL}${data.audio_url}`;
    return data;
  } catch (error: any) {
    console.error("TTS Error:", error);
    throw new Error(error.message || 'Failed to generate speech');
  }
};
