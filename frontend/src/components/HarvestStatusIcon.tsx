/**
 * Harvest Status Icon Component
 * 
 * Displays icon indicating harvest state for a conversation
 */

import React from 'react';
import { CheckCircle, Circle, AlertCircle, RefreshCw } from 'lucide-react';

export type HarvestState = 'idle' | 'delta_detected' | 'processing' | 'not_harvested' | 'harvested' | 'partially_harvested';

interface HarvestStatusIconProps {
    status?: HarvestState;
    className?: string;
}

export const HarvestStatusIcon: React.FC<HarvestStatusIconProps> = ({ status, className = '' }) => {
    // Normalize status (handle both old and new format)
    const normalizedStatus = status === 'harvested' ? 'idle' : status;

    switch (normalizedStatus) {
        case 'idle':
            // 🟢 Green check - All messages harvested
            return (
                <CheckCircle
                    className={`w-4 h-4 text-green-400 ${className}`}
                    title="All up to date - No new messages to harvest"
                />
            );

        case 'delta_detected':
            // 🟡 Yellow circle - New messages since last harvest
            return (
                <Circle
                    className={`w-4 h-4 text-yellow-400 fill-yellow-400 ${className}`}
                    title="New messages since last harvest"
                />
            );

        case 'processing':
            // ⏳ Blue spinner - Harvest in progress
            return (
                <RefreshCw
                    className={`w-4 h-4 text-blue-400 animate-spin ${className}`}
                    title="Harvest in progress..."
                />
            );

        case 'partially_harvested':
            // ⚠️ Orange warning - Harvest had errors
            return (
                <AlertCircle
                    className={`w-4 h-4 text-orange-400 ${className}`}
                    title="Last harvest had errors"
                />
            );

        case 'not_harvested':
        default:
            // ⚪ Gray circle - Never harvested
            return (
                <Circle
                    className={`w-4 h-4 text-gray-500 ${className}`}
                    title="Not yet harvested"
                />
            );
    }
};

// Status text helper
export const getHarvestStatusText = (status?: HarvestState): string => {
    const normalizedStatus = status === 'harvested' ? 'idle' : status;

    switch (normalizedStatus) {
        case 'idle':
            return 'Up to date';
        case 'delta_detected':
            return 'New messages';
        case 'processing':
            return 'Harvesting...';
        case 'partially_harvested':
            return 'Had errors';
        case 'not_harvested':
        default:
            return 'Not harvested';
    }
};
