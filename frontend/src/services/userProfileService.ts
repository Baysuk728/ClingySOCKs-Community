/**
 * User Profile Service
 * Handles user dossier and profile data
 * Uses backend REST API endpoints.
 */

import { apiCall } from './api';

export interface UserDossier {
    // Core Identity
    name?: string;
    pronouns?: string;
    age_range?: string;
    location?: string;
    languages?: string[]; // Array

    // Neurotype & Cognition
    neurotype?: string;
    thinking_patterns?: string[]; // Array
    cognitive_strengths?: string[]; // Array
    cognitive_challenges?: string[]; // Array

    // Attachment & Emotional
    attachment_style?: string;
    attachment_notes?: string;
    ifs_parts?: string[]; // Array
    emotional_triggers?: string[]; // Array
    coping_mechanisms?: string[]; // Array

    // Health & Wellness
    medical_conditions?: string[]; // Array
    medications?: string[]; // Array
    health_notes?: string;

    // Life Situation
    family_situation?: string;
    relationship_status?: string;
    living_situation?: string;
    work_situation?: string;
    financial_notes?: string;

    // Interests & Goals
    hobbies?: string[]; // Array
    interests?: string[]; // Array
    life_goals?: string[]; // Array
    longings?: string[]; // Array
    current_projects?: string[]; // Array

    // Communication
    preferred_communication_style?: string;
    humor_style?: string;
    boundary_preferences?: string;
    support_preferences?: string;

    [key: string]: any; // Allow custom fields
}

/**
 * Save user dossier via REST API
 */
export async function saveUserDossier(dossier: UserDossier): Promise<void> {
    try {
        console.log('🔗 API: Saving user dossier to /user-profile/me', dossier);
        const response = await apiCall('/user-profile/me', {
            method: 'PUT',
            body: JSON.stringify(dossier)
        });

        const data = response as { success: boolean; message?: string };

        if (!data.success) {
            throw new Error(data.message || 'Failed to save dossier');
        }
        console.log('✅ Dossier saved successfully');
    } catch (error) {
        console.error('❌ API Error in saveUserDossier:', error);
        throw error;
    }
}

/**
 * Get user dossier via REST API
 */
export async function getUserDossier(): Promise<UserDossier | null> {
    try {
        console.log('🔗 API: Fetching user dossier from /user-profile/me');
        const response = await apiCall('/user-profile/me');
        const data = response as { success: boolean; profile: UserDossier | null };

        if (!data.success) {
            throw new Error('Failed to retrieve dossier');
        }

        console.log('✅ Dossier retrieved:', data.profile);
        return data.profile;
    } catch (error) {
        console.error('❌ API Error in getUserDossier:', error);
        throw error;
    }
}

/**
 * Get locked fields for user profile (fields protected from harvester updates)
 */
export async function getLockedFields(): Promise<string[]> {
    try {
        console.log('🔗 API: Fetching locked fields from /user-profile/me/locked');
        const response = await apiCall('/user-profile/me/locked');
        const data = response as { success: boolean; locked_fields?: string[] };

        if (!data.success) {
            console.warn('Failed to retrieve locked fields');
            return [];
        }

        console.log('✅ Locked fields retrieved:', data.locked_fields);
        return data.locked_fields || [];
    } catch (error) {
        console.error('❌ API Error in getLockedFields:', error);
        return [];
    }
}

/**
 * Update locked fields (fields protected from harvester updates)
 */
export async function updateLockedFields(lockedFields: string[]): Promise<void> {
    try {
        console.log('🔗 API: Updating locked fields at /user-profile/me/locked', lockedFields);
        const response = await apiCall('/user-profile/me/locked', {
            method: 'PUT',
            body: JSON.stringify({ locked_fields: lockedFields })
        });

        const data = response as { success: boolean; message?: string };

        if (!data.success) {
            throw new Error(data.message || 'Failed to update locked fields');
        }
        console.log('✅ Locked fields updated successfully');
    } catch (error) {
        console.error('❌ API Error in updateLockedFields:', error);
        throw error;
    }
}
