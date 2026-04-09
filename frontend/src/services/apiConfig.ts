/**
 * Runtime API configuration.
 *
 * Priority:
 *  1. Vite build-time env var  VITE_MEMORY_API_URL  (works for local dev & docker --build-arg)
 *  2. Runtime /config.json     (injected by nginx for Railway / dynamic deploys)
 *  3. Fallback                 http://localhost:8100
 */

let _cachedUrl: string | null = null;
let _fetchPromise: Promise<string> | null = null;

function buildTimeUrl(): string {
    try {
        return (import.meta as any).env?.VITE_MEMORY_API_URL || '';
    } catch {
        return '';
    }
}

async function fetchRuntimeConfig(): Promise<string> {
    try {
        const resp = await fetch('/config.json', { cache: 'no-store' });
        if (resp.ok) {
            const data = await resp.json();
            const url = data?.VITE_MEMORY_API_URL;
            // Ignore the placeholder value (means nginx didn't substitute)
            if (url && url !== 'RUNTIME_API_URL_PLACEHOLDER') {
                return url.replace(/\/+$/, ''); // strip trailing slash
            }
        }
    } catch {
        // /config.json not available (local dev) — fall through
    }
    return '';
}

/**
 * Get the API base URL.  First call may be async (fetches /config.json);
 * subsequent calls return the cached value synchronously.
 */
export async function getApiUrl(): Promise<string> {
    if (_cachedUrl !== null) return _cachedUrl;

    // Build-time var takes priority
    const bt = buildTimeUrl();
    if (bt) {
        _cachedUrl = bt.replace(/\/+$/, '');
        return _cachedUrl;
    }

    // Try runtime config (only fetch once)
    if (!_fetchPromise) {
        _fetchPromise = fetchRuntimeConfig();
    }
    const rt = await _fetchPromise;
    _cachedUrl = rt || 'http://localhost:8100';
    return _cachedUrl;
}

/**
 * Synchronous getter — returns cached URL or build-time URL or fallback.
 * Use this in places that can't be async (e.g. top-level const).
 * Will be correct after the first `getApiUrl()` call resolves.
 */
export function getApiUrlSync(): string {
    if (_cachedUrl !== null) return _cachedUrl;
    const bt = buildTimeUrl();
    if (bt) {
        _cachedUrl = bt.replace(/\/+$/, '');
        return _cachedUrl;
    }
    return 'http://localhost:8100';
}

/** API key from build-time env (if any) */
export const API_KEY: string = (() => {
    try {
        return (import.meta as any).env?.VITE_MEMORY_API_KEY || '';
    } catch {
        return '';
    }
})();

// Eagerly kick off the runtime config fetch so it's ready by the time
// the first API call happens.
getApiUrl();
