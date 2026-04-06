/**
 * Vault API Service — BYOK + BYOD management
 * 
 * Calls the FastAPI /vault/* endpoints for key and database management.
 */

const API_URL = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

const getHeaders = (json = true): Record<string, string> => ({
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

// ─── Types ───────────────────────────────────────────

export type VaultProvider =
    | 'openrouter'
    | 'gemini'
    | 'openai'
    | 'anthropic'
    | 'xai'
    | 'elevenlabs'
    | 'google_tts'
    | 'search';

export type SearchProvider = 'exa' | 'tavily' | 'brave' | 'serpapi';
export type DatabaseProvider = 'supabase' | 'neon' | 'railway' | 'custom';

export interface VaultKeyInfo {
    maskedKey: string;
    updatedAt: string;
    searchProvider?: string;
}

export interface VaultKeysResponse {
    keys: Record<string, VaultKeyInfo>;
}

export interface DatabaseConfigResponse {
    configured: boolean;
    provider?: string;
    schema?: string;
    initialized?: boolean;
    updatedAt?: string;
}

export interface TestResult {
    success: boolean;
    message?: string;
    error?: string;
    latency_ms?: number;
}

// ─── Provider Metadata ───────────────────────────────

export interface ProviderMeta {
    name: string;
    description: string;
    color: string;
    placeholder: string;
    category: 'llm' | 'tts' | 'search';
    docsUrl?: string;
}

export const VAULT_PROVIDERS: Record<VaultProvider, ProviderMeta> = {
    openrouter: {
        name: 'OpenRouter',
        description: 'Access 200+ models from all providers with a single key',
        color: 'text-cyan-400',
        placeholder: 'sk-or-...',
        category: 'llm',
        docsUrl: 'https://openrouter.ai/keys',
    },
    gemini: {
        name: 'Google Gemini',
        description: 'Direct access to Gemini models (2.5 Flash, 2.5 Pro)',
        color: 'text-blue-400',
        placeholder: 'AIza...',
        category: 'llm',
        docsUrl: 'https://aistudio.google.com/apikey',
    },
    openai: {
        name: 'OpenAI',
        description: 'GPT-4o, o3-mini, TTS voices',
        color: 'text-green-400',
        placeholder: 'sk-...',
        category: 'llm',
        docsUrl: 'https://platform.openai.com/api-keys',
    },
    anthropic: {
        name: 'Anthropic Claude',
        description: 'Claude Sonnet, Opus models',
        color: 'text-orange-400',
        placeholder: 'sk-ant-...',
        category: 'llm',
        docsUrl: 'https://console.anthropic.com/settings/keys',
    },
    xai: {
        name: 'xAI Grok',
        description: 'Grok-2, Grok-3 models',
        color: 'text-purple-400',
        placeholder: 'xai-...',
        category: 'llm',
        docsUrl: 'https://console.x.ai',
    },
    elevenlabs: {
        name: 'ElevenLabs',
        description: 'Premium voice synthesis',
        color: 'text-pink-400',
        placeholder: 'xi-...',
        category: 'tts',
        docsUrl: 'https://elevenlabs.io/api',
    },
    google_tts: {
        name: 'Google TTS',
        description: 'Google Cloud Text-to-Speech (Neural2, Studio voices)',
        color: 'text-blue-300',
        placeholder: 'AIza... (same as Gemini key)',
        category: 'tts',
    },
    search: {
        name: 'Web Search',
        description: 'Enable web search capabilities for your AI',
        color: 'text-yellow-400',
        placeholder: 'Depends on provider...',
        category: 'search',
    },
};

export const SEARCH_PROVIDERS: Record<SearchProvider, { name: string; placeholder: string; docsUrl: string }> = {
    exa: { name: 'Exa', placeholder: 'exa-...', docsUrl: 'https://exa.ai' },
    tavily: { name: 'Tavily', placeholder: 'tvly-...', docsUrl: 'https://tavily.com' },
    brave: { name: 'Brave Search', placeholder: 'BSA...', docsUrl: 'https://brave.com/search/api/' },
    serpapi: { name: 'SerpAPI', placeholder: '...', docsUrl: 'https://serpapi.com' },
};

export const DATABASE_PROVIDERS: Record<DatabaseProvider, { name: string; description: string; docsUrl: string }> = {
    supabase: { name: 'Supabase', description: 'Free tier with 500MB · Built-in pgvector', docsUrl: 'https://supabase.com' },
    neon: { name: 'Neon', description: 'Serverless PostgreSQL · Free tier available', docsUrl: 'https://neon.tech' },
    railway: { name: 'Railway', description: 'Easy-deploy PostgreSQL', docsUrl: 'https://railway.app' },
    custom: { name: 'Custom', description: 'Any PostgreSQL 15+ with pgvector', docsUrl: '' },
};


// ─── Key Management ──────────────────────────────────

/**
 * Save or update an API key in the vault
 */
export async function saveVaultKey(
    userId: string,
    provider: VaultProvider,
    apiKey: string,
    searchProvider?: SearchProvider,
): Promise<{ success: boolean; maskedKey?: string; error?: string }> {
    const resp = await fetch(`${API_URL}/vault/keys`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
            user_id: userId,
            provider,
            api_key: apiKey,
            ...(searchProvider ? { search_provider: searchProvider } : {}),
        }),
    });
    return resp.json();
}

/**
 * List all vault keys (masked) for a user
 */
export async function getVaultKeys(userId: string): Promise<VaultKeysResponse> {
    const resp = await fetch(`${API_URL}/vault/keys?user_id=${encodeURIComponent(userId)}`, {
        headers: getHeaders(false),
    });
    return resp.json();
}

/**
 * Delete a key from the vault
 */
export async function deleteVaultKey(
    userId: string,
    provider: string,
): Promise<{ success: boolean }> {
    const resp = await fetch(`${API_URL}/vault/keys/${encodeURIComponent(provider)}`, {
        method: 'DELETE',
        headers: getHeaders(),
        body: JSON.stringify({ user_id: userId }),
    });
    return resp.json();
}

/**
 * Test an API key without saving
 */
export async function testVaultKey(
    provider: string,
    apiKey: string,
): Promise<TestResult> {
    const resp = await fetch(`${API_URL}/vault/keys/test`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ provider, api_key: apiKey }),
    });
    return resp.json();
}


// ─── Database Management ─────────────────────────────

/**
 * Save database connection config
 */
export async function saveDatabaseConfig(
    userId: string,
    provider: DatabaseProvider,
    connectionString: string,
    schema: string = 'public',
): Promise<{ success: boolean; error?: string }> {
    const resp = await fetch(`${API_URL}/vault/database`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
            user_id: userId,
            provider,
            connection_string: connectionString,
            schema,
        }),
    });
    return resp.json();
}

/**
 * Get database config metadata (no secrets)
 */
export async function getDatabaseConfig(userId: string): Promise<DatabaseConfigResponse> {
    const resp = await fetch(`${API_URL}/vault/database?user_id=${encodeURIComponent(userId)}`, {
        headers: getHeaders(false),
    });
    return resp.json();
}

/**
 * Test a database connection string
 */
export async function testDatabaseConnection(connectionString: string): Promise<TestResult> {
    const resp = await fetch(`${API_URL}/vault/database/test`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ connection_string: connectionString }),
    });
    return resp.json();
}

/**
 * Initialize the user's database with all ClingySOCKs tables.
 * After successful init, the database is automatically activated as
 * the app's primary database.
 */
export async function initDatabase(userId: string): Promise<{
    success: boolean;
    tables_created?: number;
    activated?: boolean;
    error?: string;
}> {
    const resp = await fetch(`${API_URL}/vault/database/init`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ user_id: userId }),
    });
    return resp.json();
}

/**
 * Activate a previously-initialized database as the app's primary database.
 */
export async function activateDatabase(userId: string): Promise<{ success: boolean; error?: string }> {
    const resp = await fetch(`${API_URL}/vault/database/activate`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ user_id: userId }),
    });
    return resp.json();
}

/**
 * Get current database connection status (source, host, connected)
 */
export interface DatabaseStatus {
    source: 'env' | 'vault';
    host: string;
    mode: 'dev' | 'prod';
    connected: boolean;
}

export async function getDatabaseStatus(): Promise<DatabaseStatus> {
    const resp = await fetch(`${API_URL}/vault/database/status`, {
        headers: getHeaders(false),
    });
    return resp.json();
}

/**
 * Clear vault cache
 */
export async function clearVaultCache(userId: string): Promise<{ success: boolean }> {
    const resp = await fetch(`${API_URL}/vault/cache/clear?user_id=${encodeURIComponent(userId)}`, {
        method: 'POST',
        headers: getHeaders(false),
    });
    return resp.json();
}


// ─── Mode Info ───────────────────────────────────────

export interface VaultModeInfo {
    mode: 'dev' | 'prod';
    env_fallback: boolean;
    description: string;
}

/**
 * Get the current vault mode (dev vs prod)
 */
export async function getVaultMode(): Promise<VaultModeInfo> {
    const resp = await fetch(`${API_URL}/vault/mode`, {
        headers: getHeaders(false),
    });
    return resp.json();
}
