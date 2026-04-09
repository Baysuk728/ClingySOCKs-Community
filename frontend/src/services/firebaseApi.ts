/**
 * API Key Service
 * Handles saving, retrieving, and deleting API keys via the vault REST API.
 */
import { getToken } from '../auth';
import { ModelProvider } from "../types";

import { getApiUrlSync, API_KEY } from './apiConfig';

const API_URL = getApiUrlSync();

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

export interface VaultApiKey {
    id: string;
    name: string;
    provider: ModelProvider;
    maskedKey: string;
    isDefault: boolean;
    createdAt: number;
}

/**
 * Save a new API key (encrypted server-side)
 */
export const saveApiKey = async (
    name: string,
    provider: ModelProvider,
    apiKey: string,
    isDefault: boolean = false
): Promise<{ success: boolean; keyId: string }> => {
    return apiCall('/vault/keys/save', 'POST', { name, provider, apiKey, isDefault });
};

/**
 * Get all API keys for the current user (masked, not decrypted)
 */
export const getApiKeys = async (): Promise<VaultApiKey[]> => {
    const data = await apiCall<{ keys: VaultApiKey[] }>('/vault/keys', 'GET');
    return data.keys;
};

/**
 * Update an existing API key
 */
export const updateApiKey = async (
    keyId: string,
    updates: { name?: string; apiKey?: string; isDefault?: boolean }
): Promise<{ success: boolean }> => {
    return apiCall(`/vault/keys/${keyId}`, 'PATCH', updates);
};

/**
 * Delete an API key
 */
export const deleteApiKey = async (keyId: string): Promise<{ success: boolean }> => {
    return apiCall(`/vault/keys/${keyId}`, 'DELETE');
};
