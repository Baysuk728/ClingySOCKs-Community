import { useState, useEffect } from 'react';
import { AVAILABLE_MODELS } from '../constants';
import { getApiUrlSync } from '../services/apiConfig';

const API_URL = getApiUrlSync();
const CACHE_KEY = 'system_config_v3';
const CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes

interface ModelsResponse {
    models: Record<string, string[]>;
    providers: Record<string, string>;
    defaults: Record<string, string>;
    configured: string[];
}

interface SystemConfig {
    models: Record<string, string[]>;
    providers: Record<string, string>;
    defaults: Record<string, string>;
    configured: string[];
    version: string;
    features: {
        byod: boolean;
        userProfile: boolean;
        memoryGraph: boolean;
    };
}

interface CacheEntry {
    config: SystemConfig;
    timestamp: number;
}

function readCache(): SystemConfig | null {
    try {
        const raw = sessionStorage.getItem(CACHE_KEY);
        if (!raw) return null;
        const entry: CacheEntry = JSON.parse(raw);
        // Return cached data regardless of age (stale-while-revalidate)
        return entry.config;
    } catch {
        return null;
    }
}

function isCacheFresh(): boolean {
    try {
        const raw = sessionStorage.getItem(CACHE_KEY);
        if (!raw) return false;
        const entry: CacheEntry = JSON.parse(raw);
        return (Date.now() - entry.timestamp) < CACHE_TTL_MS;
    } catch {
        return false;
    }
}

function writeCache(config: SystemConfig): void {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ config, timestamp: Date.now() }));
}

export function useSystemConfig() {
    const [config, setConfig] = useState<SystemConfig | null>(() => readCache());
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<Error | null>(null);

    useEffect(() => {
        let mounted = true;

        // If cache is fresh, skip network fetch
        if (isCacheFresh()) return;

        async function fetchConfig() {
            setLoading(true);
            try {
                const res = await fetch(`${API_URL}/models/available`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data: ModelsResponse = await res.json();

                if (mounted) {
                    const full: SystemConfig = {
                        models: data.models,
                        providers: data.providers,
                        defaults: data.defaults,
                        configured: data.configured,
                        version: 'live',
                        features: { byod: true, userProfile: true, memoryGraph: true },
                    };
                    setConfig(full);
                    writeCache(full);
                }
            } catch (err) {
                console.error('Failed to fetch model registry:', err);
                if (mounted) {
                    setError(err as Error);
                    // Only fallback if we have nothing cached
                    if (!config) {
                        setConfig({
                            models: AVAILABLE_MODELS,
                            providers: {},
                            defaults: {},
                            configured: [],
                            version: 'offline',
                            features: { byod: true, userProfile: true, memoryGraph: true }
                        });
                    }
                }
            } finally {
                if (mounted) setLoading(false);
            }
        }

        fetchConfig();

        return () => { mounted = false; };
    }, []);

    const models = config?.models || AVAILABLE_MODELS;

    return { config, models, loading, error };
}
