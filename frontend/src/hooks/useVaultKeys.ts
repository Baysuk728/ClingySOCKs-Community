import { useEffect, useState, useCallback } from 'react';
import { getVaultKeys, VaultKeyInfo } from '../services/vaultApi';
import { useAuth } from '../components/AuthProvider';

const CACHE_KEY = 'vault_keys_v1';
const CACHE_TTL_MS = 5 * 60 * 1000;

interface CacheEntry {
    uid: string;
    keys: Record<string, VaultKeyInfo>;
    fetchedAt: number;
}

function readCache(uid: string): Record<string, VaultKeyInfo> | null {
    try {
        const raw = sessionStorage.getItem(CACHE_KEY);
        if (!raw) return null;
        const entry: CacheEntry = JSON.parse(raw);
        if (entry.uid !== uid) return null;
        if (Date.now() - entry.fetchedAt > CACHE_TTL_MS) return null;
        return entry.keys;
    } catch {
        return null;
    }
}

function writeCache(uid: string, keys: Record<string, VaultKeyInfo>) {
    try {
        sessionStorage.setItem(
            CACHE_KEY,
            JSON.stringify({ uid, keys, fetchedAt: Date.now() } as CacheEntry),
        );
    } catch {
        // sessionStorage full / disabled — ignore
    }
}

/**
 * Returns the current user's vault keys (BYOK), keyed by provider name
 * (`gemini`, `openai`, `anthropic`, `xai`, `openrouter`, `elevenlabs`, ...).
 *
 * Cached in sessionStorage for 5 minutes per user. Components can call
 * `refresh()` after a key is added/removed in Settings.
 */
export function useVaultKeys() {
    const { user } = useAuth();
    const [keys, setKeys] = useState<Record<string, VaultKeyInfo>>(() =>
        user ? readCache(user.uid) ?? {} : {}
    );
    const [loading, setLoading] = useState(false);

    const load = useCallback(async (force = false) => {
        if (!user) {
            setKeys({});
            return;
        }
        if (!force) {
            const cached = readCache(user.uid);
            if (cached) {
                setKeys(cached);
                return;
            }
        }
        setLoading(true);
        try {
            const resp = await getVaultKeys(user.uid);
            const next = resp.keys || {};
            setKeys(next);
            writeCache(user.uid, next);
        } catch (err) {
            console.error('useVaultKeys: failed to load vault keys:', err);
        } finally {
            setLoading(false);
        }
    }, [user]);

    useEffect(() => {
        load();
    }, [load]);

    return { keys, loading, refresh: () => load(true) };
}
