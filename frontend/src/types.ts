export type ModelProvider = 'gemini' | 'openai' | 'claude' | 'grok' | 'openrouter' | 'local' | 'elevenlabs';

export interface ApiKeyConfig {
  id: string;
  name: string;           // User-friendly name (e.g., "My Gemini Key")
  provider: ModelProvider;
  apiKey: string;         // The actual API key (stored encrypted in localStorage)
  createdAt: number;
  isDefault?: boolean;    // Default key for this provider
}

export interface Agent {
  id: string;
  name: string;
  avatar: string; // URL or emoji
  role: string;
  provider: ModelProvider;
  modelId: string;
  voiceId?: string; // TTS voice name/ID (provider-specific)
  ttsProvider?: 'google' | 'openai' | 'elevenlabs' | 'local'; // TTS provider
  systemPrompt: string;
  temperature: number;
  isSystem?: boolean;
  description?: string;
  maxContextChars?: number;
  maxWarmMemory?: number;
  maxHistoryChars?: number;
  maxHistoryMessages?: number;
}

export interface Message {
  id: string;
  chatId: string;
  senderId: string; // 'user' or agentId
  content: string;
  timestamp: number;
  isThinking?: boolean;
  mediaAttachments?: {
    kind: 'image' | 'audio';
    relativePath: string;
    name: string;
  }[];
  imageDataUrls?: string[]; // Base64 data URLs for user-attached images
}

export type HarvestState = 'idle' | 'delta_detected' | 'processing' | 'not_harvested' | 'harvested' | 'partially_harvested';

export interface ChatSession {
  id: string;
  name: string;
  participants: string[]; // Agent IDs
  isGroup: boolean;
  lastMessageAt: number;
  preview: string;
  harvestState?: HarvestState;
  messageCount?: number;
  entityId?: string;
  source?: string;
}

export interface Memory {
  id: string;
  source: string; // Filename
  type: 'chat_log' | 'document' | 'code';
  content: string;
  vectorId?: string; // Mock Qdrant ID
  timestamp: number;
  status: 'processing' | 'indexed' | 'error';
}

export type ViewMode = 'chat' | 'personas' | 'memory' | 'context' | 'graph' | 'tasks' | 'files' | 'settings' | 'profile';

