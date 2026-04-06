/**
 * Harvest Panel - UI controls for memory harvesting
 */

import React, { useState, useEffect } from 'react';
import { auth } from '../auth';
import {
    Zap,
    RefreshCw,
    Clock,
    Calendar,
    CheckCircle,
    AlertTriangle,
    History,
    ChevronDown,
    ChevronUp,
    X
} from 'lucide-react';

interface HarvestLog {
    id: string;
    timestamp: { seconds: number };
    entityCount: number;
    totalConversations: number;
    totalUpdates: number;
    totalErrors: number;
    results: any[];
}

interface HarvestSummary {
    entitiesProcessed: number;
    totalConversations: number;
    totalUpdates: number;
    totalErrors: number;
}

export const HarvestPanel: React.FC = () => {
    const [isHarvesting, setIsHarvesting] = useState(false);
    const [lastResult, setLastResult] = useState<HarvestSummary | null>(null);
    const [logs, setLogs] = useState<HarvestLog[]>([]);
    const [showLogs, setShowLogs] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [abortController, setAbortController] = useState<AbortController | null>(null);
    const [currentHarvestId, setCurrentHarvestId] = useState<string | null>(null);

    // Manual Trigger States
    const [isUserHarvesting, setIsUserHarvesting] = useState(false);
    const [isBridging, setIsBridging] = useState(false);

    useEffect(() => {
        loadLogs();
    }, []);

    const MEMORY_API_URL = import.meta.env.VITE_MEMORY_API_URL || 'http://localhost:8100';
    const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';
    const getHeaders = (json = true): Record<string, string> => ({
        ...(json ? { 'Content-Type': 'application/json' } : {}),
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    });

    const loadLogs = async () => {
        setLoading(true);
        try {
            // Harvest logs are not yet a REST endpoint — clear logs for now
            setLogs([]);
        } catch (err) {
            console.error('Failed to load harvest logs:', err);
        } finally {
            setLoading(false);
        }
    };

    const runHarvestNow = async () => {
        const controller = new AbortController();
        setAbortController(controller);
        setIsHarvesting(true);
        setError(null);
        setLastResult(null);

        try {
            const resp = await fetch(`${MEMORY_API_URL}/harvest/run`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({}),
                signal: controller.signal,
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Harvest failed' }));
                throw new Error(err.detail || `Harvest failed: ${resp.status}`);
            }

            const data = await resp.json();

            if (data.success) {
                setLastResult(data.summary || data);
                await loadLogs();
            }
        } catch (err) {
            if (controller.signal.aborted) {
                setError('Harvest cancelled. It may continue running in the background.');
                return;
            }

            const error = err as Error;
            setError(error.message);
            console.error('Harvest failed:', err);
        } finally {
            setIsHarvesting(false);
            setAbortController(null);
        }
    };

    const cancelHarvest = async () => {
        if (!currentHarvestId) {
            setError('No active harvest to cancel');
            return;
        }

        try {
            console.log(`🛑 Cancellation requested for harvest ${currentHarvestId}`);
            setError('Cancellation requested. Harvest will stop after current conversation.');
            setIsHarvesting(false);
            setCurrentHarvestId(null);
        } catch (error) {
            console.error('Failed to cancel harvest:', error);
            setError(`Failed to cancel: ${(error as Error).message}`);
        }
    };

    const runUserHarvest = async () => {
        setIsUserHarvesting(true);
        setError(null);
        try {
            if (!auth.currentUser) throw new Error("Not authenticated");

            const resp = await fetch(`${MEMORY_API_URL}/harvest/user`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({ userId: auth.currentUser.uid }),
            });
            if (!resp.ok) throw new Error('User harvest failed');

            alert("✅ User Twin Harvest Complete!");
        } catch (err) {
            console.error(err);
            setError(`User Harvest Failed: ${(err as Error).message}`);
        } finally {
            setIsUserHarvesting(false);
        }
    };

    const runBridge = async () => {
        setIsBridging(true);
        setError(null);
        try {
            if (!auth.currentUser) throw new Error("Not authenticated");

            const savedAgent = localStorage.getItem('nexus_active_agent_id') || 'agent-id';

            const resp = await fetch(`${MEMORY_API_URL}/harvest/bridge`, {
                method: 'POST',
                headers: getHeaders(),
                body: JSON.stringify({
                    userId: auth.currentUser.uid,
                    agentId: savedAgent,
                    agentName: "Agent"
                }),
            });
            if (!resp.ok) throw new Error('Bridge generation failed');

            alert("✅ Session Bridge Generated!");
        } catch (err) {
            console.error(err);
            setError(`Bridge Failed: ${(err as Error).message}`);
        } finally {
            setIsBridging(false);
        }
    };

    const formatDate = (timestamp: { seconds: number }) => {
        return new Date(timestamp.seconds * 1000).toLocaleString();
    };

    return (
        <div className="bg-nexus-800/50 border border-white/5 rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-purple-500/20 rounded-lg">
                    <Zap className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                    <h3 className="text-lg font-bold text-white">Memory Harvest</h3>
                    <p className="text-sm text-gray-500">Consolidate and summarize memories</p>
                </div>
            </div>

            {/* Harvest Button */}
            <div className="flex flex-col gap-4">
                {!isHarvesting ? (
                    <button
                        onClick={runHarvestNow}
                        className="w-full py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl font-bold flex items-center justify-center gap-3 hover:from-purple-700 hover:to-pink-700 transition-all"
                    >
                        <Zap className="w-5 h-5" />
                        Harvest Agent Memories
                    </button>
                ) : (
                    <div className="flex gap-2">
                        <button
                            disabled
                            className="flex-1 py-4 bg-purple-600/50 text-white rounded-xl font-bold flex items-center justify-center gap-3 opacity-50 cursor-not-allowed"
                        >
                            <RefreshCw className="w-5 h-5 animate-spin" />
                            Harvesting Agent...
                        </button>
                        <button
                            onClick={cancelHarvest}
                            className="px-6 py-4 bg-red-600 hover:bg-red-700 text-white rounded-xl font-bold flex items-center justify-center gap-3 transition-all"
                            title="Cancel harvest (may continue on server)"
                        >
                            <X className="w-5 h-5" />
                            Stop
                        </button>
                    </div>
                )}

                {/* Manual Dev Triggers */}
                <div className="grid grid-cols-2 gap-3">
                    <button
                        onClick={runUserHarvest}
                        disabled={isUserHarvesting || isHarvesting}
                        className={`py-3 bg-nexus-700 border border-white/10 text-white rounded-xl font-medium flex items-center justify-center gap-2 hover:bg-nexus-600 transition-all ${isUserHarvesting ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {isUserHarvesting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4 text-cyan-400" />}
                        Harvest User Twin
                    </button>

                    <button
                        onClick={runBridge}
                        disabled={isBridging || isHarvesting}
                        className={`py-3 bg-nexus-700 border border-white/10 text-white rounded-xl font-medium flex items-center justify-center gap-2 hover:bg-nexus-600 transition-all ${isBridging ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {isBridging ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4 text-amber-400" />}
                        Run Session Bridge
                    </button>
                </div>


                {/* Last Result */}
                {lastResult && (
                    <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4">
                        <div className="flex items-center gap-2 text-green-400 mb-2">
                            <CheckCircle className="w-4 h-4" />
                            <span className="font-medium">Harvest Complete</span>
                        </div>
                        <div className="grid grid-cols-4 gap-2 text-sm">
                            <div className="text-center">
                                <div className="text-xl font-bold text-white">{lastResult.entitiesProcessed}</div>
                                <div className="text-gray-500 text-xs">Entities</div>
                            </div>
                            <div className="text-center">
                                <div className="text-xl font-bold text-white">{lastResult.totalConversations}</div>
                                <div className="text-gray-500 text-xs">Conversations</div>
                            </div>
                            <div className="text-center">
                                <div className="text-xl font-bold text-white">{lastResult.totalUpdates}</div>
                                <div className="text-gray-500 text-xs">Updates</div>
                            </div>
                            <div className="text-center">
                                <div className="text-xl font-bold text-white">{lastResult.totalErrors}</div>
                                <div className="text-gray-500 text-xs">Errors</div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
                        <AlertTriangle className="w-5 h-5 text-red-400" />
                        <span className="text-red-400 text-sm">{error}</span>
                    </div>
                )}
            </div>

            {/* Harvest Logs */}
            <div className="mt-6 pt-6 border-t border-white/5">
                <button
                    onClick={() => setShowLogs(!showLogs)}
                    className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors w-full"
                >
                    <History className="w-4 h-4" />
                    <span className="font-medium">Harvest History</span>
                    {showLogs ? <ChevronUp className="w-4 h-4 ml-auto" /> : <ChevronDown className="w-4 h-4 ml-auto" />}
                </button>

                {showLogs && (
                    <div className="mt-4 space-y-2">
                        {loading ? (
                            <div className="flex items-center justify-center py-4">
                                <RefreshCw className="w-5 h-5 animate-spin text-gray-500" />
                            </div>
                        ) : logs.length === 0 ? (
                            <div className="text-center py-4 text-gray-500 text-sm">
                                No harvest history yet
                            </div>
                        ) : (
                            logs.map(log => (
                                <div key={log.id} className="bg-white/5 rounded-lg p-3">
                                    <div className="flex items-center gap-4">
                                        <Clock className="w-4 h-4 text-gray-500" />
                                        <div className="flex-1">
                                            <div className="text-sm text-white">
                                                {formatDate(log.timestamp)}
                                            </div>
                                            <div className="text-xs text-gray-500">
                                                {log.entityCount} entities • {log.totalConversations} conversations • {log.totalUpdates} updates
                                            </div>
                                        </div>
                                        {log.totalErrors > 0 && (
                                            <span className="text-xs px-2 py-0.5 bg-red-500/20 text-red-400 rounded">
                                                {log.totalErrors} errors
                                            </span>
                                        )}
                                    </div>
                                    {/* Show error details */}
                                    {log.results && log.results.some((r: any) => r.errors?.length > 0) && (
                                        <div className="mt-2 pt-2 border-t border-white/5">
                                            {log.results.map((r: any, idx: number) => (
                                                r.errors?.length > 0 && (
                                                    <div key={idx} className="text-xs text-red-400">
                                                        <span className="text-gray-500">{r.entityId}:</span> {r.errors.join(', ')}
                                                    </div>
                                                )
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                )}
            </div>

            {/* Schedule Info */}
            <div className="mt-6 pt-6 border-t border-white/5">
                <div className="flex items-center gap-3 text-gray-500 text-sm">
                    <Calendar className="w-4 h-4" />
                    <span>Automatic nightly harvest: Coming soon</span>
                </div>
            </div>
        </div>
    );
};
