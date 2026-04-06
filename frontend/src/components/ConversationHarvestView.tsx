/**
 * ConversationHarvestView - Display harvest results from a single conversation
 * 
 * Shows the extracted deltas (lastHarvestDeltas) from a specific conversation
 * for comparison with the overall memory banks.
 */

import React, { useState, useEffect } from 'react';
import { getConversation, getConversationHarvestLog, Conversation } from '../services/conversationService';
import { ChevronDown, ChevronRight, Clock, FileText, Brain, Heart, Users, Sparkles } from 'lucide-react';

interface ConversationHarvestViewProps {
    conversationId: string;
    onClose?: () => void;
}

// Helper to render JSON with collapsible sections
const JsonSection: React.FC<{
    title: string;
    data: any;
    icon?: React.ReactNode;
    defaultExpanded?: boolean;
}> = ({ title, data, icon, defaultExpanded = false }) => {
    const [expanded, setExpanded] = useState(defaultExpanded);

    // Check if data is empty/null
    const isEmpty = !data ||
        (Array.isArray(data) && data.length === 0) ||
        (typeof data === 'object' && Object.keys(data).length === 0);

    if (isEmpty) return null;

    return (
        <div className="border border-white/10 rounded-lg overflow-hidden">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center gap-2 p-3 bg-nexus-800/50 hover:bg-nexus-800 transition-colors text-left"
            >
                {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                {icon}
                <span className="font-medium">{title}</span>
                <span className="text-xs text-gray-500 ml-auto">
                    {Array.isArray(data) ? `${data.length} items` : 'object'}
                </span>
            </button>
            {expanded && (
                <div className="p-3 bg-nexus-900/50">
                    <pre className="text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(data, null, 2)}
                    </pre>
                </div>
            )}
        </div>
    );
};

// Render relationship deltas with special formatting
const RelationshipSection: React.FC<{ relationships: any[] }> = ({ relationships }) => {
    const [expanded, setExpanded] = useState(true);

    if (!relationships || relationships.length === 0) return null;

    return (
        <div className="border border-white/10 rounded-lg overflow-hidden">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center gap-2 p-3 bg-purple-900/30 hover:bg-purple-900/50 transition-colors text-left"
            >
                {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                <Users className="w-4 h-4 text-purple-400" />
                <span className="font-medium text-purple-300">Relationships</span>
                <span className="text-xs text-gray-500 ml-auto">{relationships.length} targets</span>
            </button>
            {expanded && (
                <div className="p-3 space-y-3 bg-nexus-900/50">
                    {relationships.map((rel, idx) => {
                        // Handle trust as either number or object {level, narrative}
                        const trustValue = typeof rel.trust === 'object'
                            ? rel.trust?.level
                            : rel.trust;
                        const trustNarrative = typeof rel.trust === 'object'
                            ? rel.trust?.narrative
                            : null;

                        // Handle targetProfile with various field names
                        const profileFacts = rel.targetProfile?.facts
                            || rel.targetProfile?.keyFacts
                            || rel.targetProfile?.coreIdentity
                            || [];

                        return (
                            <div key={idx} className="border-l-2 border-purple-500/50 pl-3">
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="font-medium text-purple-300">{rel.targetId || 'Unknown'}</span>
                                    {trustValue !== undefined && (
                                        <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-300">
                                            Trust: {trustValue}
                                        </span>
                                    )}
                                </div>

                                {trustNarrative && (
                                    <p className="text-xs text-gray-400 mb-2 italic">{trustNarrative}</p>
                                )}

                                {profileFacts.length > 0 && (
                                    <div className="mb-2">
                                        <span className="text-xs text-gray-500">Target Profile:</span>
                                        <ul className="text-sm text-gray-300 ml-4 list-disc">
                                            {profileFacts.map((fact: string, i: number) => (
                                                <li key={i}>{fact}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {rel.shared?.insideJokes && rel.shared.insideJokes.length > 0 && (
                                    <div className="mb-2">
                                        <span className="text-xs text-gray-500">Inside Jokes:</span>
                                        <div className="space-y-1 mt-1">
                                            {rel.shared.insideJokes.map((joke: any, i: number) => (
                                                <div key={i} className="text-sm bg-yellow-500/10 p-2 rounded">
                                                    <span className="font-medium text-yellow-300">"{joke.phrase}"</span>
                                                    {joke.origin && <p className="text-xs text-gray-400 mt-1">Origin: {joke.origin}</p>}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {rel.narratives && (
                                    <div>
                                        <span className="text-xs text-gray-500">Narratives:</span>
                                        <p className="text-sm text-gray-300 mt-1">{rel.narratives.origin || rel.narratives.current}</p>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export const ConversationHarvestView: React.FC<ConversationHarvestViewProps> = ({
    conversationId,
    onClose
}) => {
    const [conversation, setConversation] = useState<Conversation | null>(null);
    const [harvestLog, setHarvestLog] = useState<any | null>(null);  // NEW: Harvest log from subcollection
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            try {
                // Fetch conversation metadata
                const conv = await getConversation(conversationId);
                setConversation(conv);

                // Fetch harvest log from subcollection (NEW)
                const log = await getConversationHarvestLog(conversationId);
                setHarvestLog(log.latest);  // Use latest harvest
            } catch (error) {
                console.error('Failed to load conversation or harvest log:', error);
            } finally {
                setLoading(false);
            }
        };

        loadData();
    }, [conversationId]);

    if (loading) {
        return (
            <div className="flex items-center justify-center p-8">
                <div className="animate-spin w-8 h-8 border-2 border-nexus-accent border-t-transparent rounded-full" />
            </div>
        );
    }

    if (!conversation) {
        return (
            <div className="text-center p-8 text-gray-500">
                Conversation not found
            </div>
        );
    }

    // Extract deltas from harvest log (NEW: from subcollection, not conversation doc)
    const deltas = harvestLog?.deltasExtracted || conversation?.lastHarvestDeltas;  // Fallback to old field
    const harvestMeta = harvestLog?.messagesProcessed;
    const llmUsed = harvestLog?.llmUsed;

    if (!deltas) {
        return (
            <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold">{conversation.title}</h3>
                    {onClose && (
                        <button onClick={onClose} className="text-gray-500 hover:text-white">✕</button>
                    )}
                </div>
                <div className="text-center p-8 bg-nexus-800/30 rounded-lg">
                    <Sparkles className="w-12 h-12 mx-auto mb-3 text-gray-600" />
                    <p className="text-gray-400">No harvest results yet</p>
                    <p className="text-sm text-gray-500 mt-1">Harvest this conversation to see extracted memories</p>
                </div>
            </div>
        );
    }

    return (
        <div className="p-6 overflow-y-auto max-h-[calc(100vh-200px)]">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-lg font-bold">{conversation.title}</h3>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                        <Clock className="w-3 h-3" />
                        {conversation.lastHarvestAt
                            ? `Harvested ${new Date(conversation.lastHarvestAt as any).toLocaleString()}`
                            : 'Not harvested'
                        }
                        {harvestMeta && (
                            <>
                                <span>•</span>
                                <FileText className="w-3 h-3" />
                                {`Messages ${harvestMeta.fromIndex + 1}-${harvestMeta.toIndex + 1} (${harvestMeta.count} total)`}
                            </>
                        )}
                        {llmUsed && (
                            <>
                                <span>•</span>
                                <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300">
                                    {llmUsed.toUpperCase()}
                                </span>
                            </>
                        )}
                    </div>
                </div>
                {onClose && (
                    <button onClick={onClose} className="text-gray-500 hover:text-white text-2xl">✕</button>
                )}
            </div>

            {/* Delta Sections */}
            <div className="space-y-3">
                {/* Persona */}
                <JsonSection
                    title="Persona (Identity, Values, Goals)"
                    data={deltas.persona}
                    icon={<Brain className="w-4 h-4 text-blue-400" />}
                    defaultExpanded={true}
                />

                {/* Emotional */}
                <JsonSection
                    title="Emotional (Patterns, Triggers, Loops)"
                    data={deltas.emotional}
                    icon={<Heart className="w-4 h-4 text-red-400" />}
                />

                {/* History */}
                <JsonSection
                    title="History (Life Events, Artifacts)"
                    data={deltas.history}
                    icon={<Clock className="w-4 h-4 text-green-400" />}
                />

                {/* Relationships - Special formatting */}
                <RelationshipSection relationships={deltas.relationships} />

                {/* Cold Memories */}
                {deltas.coldMemories && deltas.coldMemories.length > 0 && (
                    <JsonSection
                        title="Cold Memories (Archived)"
                        data={deltas.coldMemories}
                        icon={<FileText className="w-4 h-4 text-cyan-400" />}
                    />
                )}

                {/* Debug: Show raw data if no sections rendered */}
                {(!deltas.persona || Object.keys(deltas.persona || {}).length === 0) &&
                    (!deltas.emotional || Object.keys(deltas.emotional || {}).length === 0) &&
                    (!deltas.relationships || deltas.relationships.length === 0) && (
                        <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                            <p className="text-yellow-400 text-sm mb-2">⚠️ No meaningful content extracted</p>
                            <details className="text-xs">
                                <summary className="text-gray-400 cursor-pointer">View raw extraction data</summary>
                                <pre className="mt-2 text-gray-500 overflow-auto max-h-40">
                                    {JSON.stringify(deltas, null, 2)}
                                </pre>
                            </details>
                        </div>
                    )}
            </div>
        </div >
    );
};

export default ConversationHarvestView;
