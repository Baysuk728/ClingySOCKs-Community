/**
 * Runtime API configuration.
 *
 * Priority:
 *  1. Vite build-time env var  VITE_MEMORY_API_URL  (works for local dev & docker --build-arg)
 *  2. Synchronous window.__RUNTIME_CONFIG__  (injected by inline script in index.html)
 *  3. Fallback                 http://localhost:8100
 */

declare global {
    interface Window {
        __RUNTIME_CONFIG__?: { VITE_MEMORY_API_URL?: string };
    }
}

let _cachedUrl: string | null = null;

function buildTimeUrl(): string {
    try {
        return (import.meta as any).env?.VITE_MEMORY_API_URL || '';
    } catch {
        return '';
    }
}

function runtimeUrl(): string {
    try {
        const url = window.__RUNTIME_CONFIG__?.VITE_MEMORY_API_URL;
        if (url && url !== 'RUNTIME_API_URL_PLACEHOLDER') {
            return url.replace(/\/+$/, '');
        }
    } catch { /* ignore */ }
    return '';
}

/**
 * Synchronous getter — returns the correct API URL immediately.
 * Works because index.html pre-loads /config.json synchronously.
 */
export function getApiUrlSync(): string {
    if (_cachedUrl !== null) return _cachedUrl;
    const bt = buildTimeUrl();
    if (bt) {
        _cachedUrl = bt.replace(/\/+$/, '');
        return _cachedUrl;
    }
    const rt = runtimeUrl();
    if (rt) {
        _cachedUrl = rt;
        return _cachedUrl;
    }
    return 'http://localhost:8100';
}

/** Async version — kept for compatibility, delegates to sync now. */
export async function getApiUrl(): Promise<string> {
    return getApiUrlSync();
}

/** API key from build-time env (if any) */
export const API_KEY: string = (() => {
    try {
        return (import.meta as any).env?.VITE_MEMORY_API_KEY || '';
    } catch {
        return '';
    }
})();
