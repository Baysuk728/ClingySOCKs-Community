/**
 * Local Auth — REST API-backed authentication for ClingySOCKs.
 */
import { getApiUrlSync, API_KEY } from './services/apiConfig';

const API_URL = getApiUrlSync();

// ── User type ──

export interface User {
    uid: string;
    email: string | null;
    displayName: string | null;
    getIdToken: () => Promise<string>;
}

// ── Internal state ──

let _currentUser: User | null = null;
let _token: string | null = null;
const _listeners: Array<(user: User | null) => void> = [];

function _notifyListeners() {
    for (const cb of _listeners) cb(_currentUser);
}

function _buildUser(uid: string, email: string, token: string): User {
    _token = token;
    return {
        uid,
        email,
        displayName: email.split('@')[0],
        getIdToken: async () => token,
    };
}

// Persist token across page reloads
const TOKEN_KEY = 'clingysocks-auth-token';
const USER_KEY = 'clingysocks-auth-user';

function _persist(user: User, token: string) {
    try {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify({ uid: user.uid, email: user.email }));
    } catch { /* localStorage may be unavailable */ }
}

function _clearPersisted() {
    try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    } catch { /* noop */ }
}

// ── Public API ──

export async function signUp(email: string, password: string): Promise<User> {
    const resp = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        },
        body: JSON.stringify({ email, password }),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Registration failed' }));
        throw new Error(err.detail || 'Registration failed');
    }
    const data = await resp.json();
    _currentUser = _buildUser(data.user_id, data.email, data.token);
    _persist(_currentUser, data.token);
    _notifyListeners();
    return _currentUser;
}

export async function signIn(email: string, password: string): Promise<User> {
    const resp = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
        },
        body: JSON.stringify({ email, password }),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Authentication failed' }));
        throw new Error(err.detail || 'Authentication failed');
    }
    const data = await resp.json();
    _currentUser = _buildUser(data.user_id, data.email, data.token);
    _persist(_currentUser, data.token);
    _notifyListeners();
    return _currentUser;
}

export async function logOut(): Promise<void> {
    _currentUser = null;
    _token = null;
    _clearPersisted();
    _notifyListeners();
}

/**
 * Subscribe to auth state changes. Returns an unsubscribe function.
 * Fires immediately with the current user (from persisted token if any).
 */
export function onAuthChange(callback: (user: User | null) => void): () => void {
    _listeners.push(callback);

    // If we haven't tried to restore yet, do so now
    if (_currentUser === null && !_restoreAttempted) {
        _restoreAttempted = true;
        _restoreSession().then(() => callback(_currentUser));
    } else {
        // Fire immediately with current state
        callback(_currentUser);
    }

    return () => {
        const idx = _listeners.indexOf(callback);
        if (idx >= 0) _listeners.splice(idx, 1);
    };
}

let _restoreAttempted = false;

async function _restoreSession(): Promise<void> {
    try {
        const savedToken = localStorage.getItem(TOKEN_KEY);
        const savedUser = localStorage.getItem(USER_KEY);
        if (!savedToken || !savedUser) return;

        const parsed = JSON.parse(savedUser);
        _currentUser = _buildUser(parsed.uid, parsed.email, savedToken);
        _notifyListeners();
    } catch {
        _clearPersisted();
    }
}

// ── Auth object for backward-compatible imports ──

export const auth = {
    get currentUser() {
        return _currentUser;
    },
};

/**
 * Get the current Bearer token (for services that need it).
 */
export function getToken(): string | null {
    return _token;
}

/**
 * Get the current user (synchronous).
 */
export function getCurrentUser(): User | null {
    return _currentUser;
}
