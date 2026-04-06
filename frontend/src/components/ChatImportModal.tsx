/**
 * Chat Import Modal - Multi-step UI for importing chat history from various formats.
 *
 * Step 1: Upload file (.json or .txt)
 * Step 2: Preview conversations + select agent + pick which to import
 * Step 3: Import progress
 * Step 4: Done summary
 */

import React, { useState, useRef } from 'react';
import {
    Upload,
    FileText,
    X,
    Check,
    AlertTriangle,
    Loader2,
    FolderOpen,
    ChevronRight,
    CheckCircle,
    Circle,
} from 'lucide-react';
import { Agent } from '../types';
import { chatApi, ImportConversationPreview, ImportPreviewResponse, ImportResult } from '../services/chatApi';

type Step = 'upload' | 'preview' | 'importing' | 'done';

interface ChatImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImportComplete: () => void; // Refresh conversation list
    agents: Agent[];
    userId: string;
}

const FORMAT_LABELS: Record<string, string> = {
    chatgpt: 'ChatGPT Export',
    claude: 'Claude Export',
    generic_json: 'JSON Chat',
    notebook_lm: 'Notebook LM',
    plain_text: 'Plain Text',
    unknown: 'Unknown Format',
};

export const ChatImportModal: React.FC<ChatImportModalProps> = ({
    isOpen,
    onClose,
    onImportComplete,
    agents,
    userId,
}) => {
    const [step, setStep] = useState<Step>('upload');
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
    const [selectedConvIds, setSelectedConvIds] = useState<Set<string>>(new Set());
    const [selectedAgentId, setSelectedAgentId] = useState<string>(agents[0]?.id || '');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [importResult, setImportResult] = useState<ImportResult | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const reset = () => {
        setStep('upload');
        setFile(null);
        setPreview(null);
        setSelectedConvIds(new Set());
        setSelectedAgentId(agents[0]?.id || '');
        setLoading(false);
        setError(null);
        setImportResult(null);
    };

    const handleClose = () => {
        reset();
        onClose();
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const selected = e.target.files?.[0];
        if (!selected) return;

        // Accept .json and .txt files
        const ext = selected.name.split('.').pop()?.toLowerCase();
        if (ext !== 'json' && ext !== 'txt') {
            setError('Please select a .json or .txt file');
            return;
        }

        setFile(selected);
        setError(null);
        setLoading(true);

        try {
            const result = await chatApi.previewImport(selected);
            setPreview(result);
            // Select all by default
            setSelectedConvIds(new Set(result.conversations.map(c => c.original_id)));
            setStep('preview');
        } catch (err: any) {
            setError(err.message || 'Failed to parse file');
        } finally {
            setLoading(false);
        }
    };

    const toggleConversation = (originalId: string) => {
        setSelectedConvIds(prev => {
            const next = new Set(prev);
            if (next.has(originalId)) {
                next.delete(originalId);
            } else {
                next.add(originalId);
            }
            return next;
        });
    };

    const toggleAll = () => {
        if (!preview) return;
        if (selectedConvIds.size === preview.conversations.length) {
            setSelectedConvIds(new Set());
        } else {
            setSelectedConvIds(new Set(preview.conversations.map(c => c.original_id)));
        }
    };

    const handleImport = async () => {
        if (!file || !selectedAgentId || selectedConvIds.size === 0) return;

        setStep('importing');
        setLoading(true);
        setError(null);

        try {
            const isAll = preview && selectedConvIds.size === preview.conversations.length;
            const convIds = isAll ? '*' as const : Array.from(selectedConvIds);

            const result = await chatApi.executeImport(file, selectedAgentId, userId, convIds);
            setImportResult(result);
            setStep('done');

            // Trigger conversation list refresh
            if (result.imported > 0) {
                onImportComplete();
            }
        } catch (err: any) {
            setError(err.message || 'Import failed');
            setStep('preview'); // Go back to preview on error
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    const selectedAgent = agents.find(a => a.id === selectedAgentId);
    const selectedMsgCount = preview?.conversations
        .filter(c => selectedConvIds.has(c.original_id))
        .reduce((sum, c) => sum + c.message_count, 0) || 0;

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-nexus-800 border border-white/10 rounded-2xl p-6 w-full max-w-2xl shadow-2xl max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <Upload className="w-6 h-6 text-nexus-accent" />
                        <div>
                            <h3 className="text-xl font-bold text-white">Import Chat History</h3>
                            <p className="text-sm text-gray-500">
                                {step === 'upload' && 'Upload a ChatGPT, Claude, or text export'}
                                {step === 'preview' && `${preview?.total_conversations} conversations detected`}
                                {step === 'importing' && 'Importing conversations...'}
                                {step === 'done' && 'Import complete'}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={handleClose}
                        className="text-gray-500 hover:text-white transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Error banner */}
                {error && (
                    <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-red-400">{error}</p>
                    </div>
                )}

                {/* ── Step 1: Upload ── */}
                {step === 'upload' && (
                    <div>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".json,.txt"
                            onChange={handleFileSelect}
                            className="hidden"
                        />
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            disabled={loading}
                            className="w-full py-12 border-2 border-dashed border-white/20 rounded-xl text-gray-400 hover:text-white hover:border-nexus-accent/40 transition-colors flex flex-col items-center justify-center gap-3"
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="w-8 h-8 animate-spin text-nexus-accent" />
                                    <span className="text-nexus-accent">Analyzing file...</span>
                                </>
                            ) : (
                                <>
                                    <FolderOpen className="w-8 h-8" />
                                    <span>Select Chat Export File</span>
                                    <span className="text-xs text-gray-600">.json (ChatGPT, Claude) or .txt (Notebook LM, plain text)</span>
                                </>
                            )}
                        </button>
                    </div>
                )}

                {/* ── Step 2: Preview & Select ── */}
                {step === 'preview' && preview && (
                    <div>
                        {/* Format badge */}
                        <div className="flex items-center gap-3 mb-4">
                            <span className="px-3 py-1 bg-nexus-accent/10 text-nexus-accent rounded-full text-xs font-medium">
                                {FORMAT_LABELS[preview.format] || preview.format}
                            </span>
                            <span className="text-xs text-gray-500">
                                {preview.total_conversations} conversations · {preview.total_messages.toLocaleString()} messages
                            </span>
                            {file && (
                                <span className="text-xs text-gray-600 truncate max-w-[200px]" title={file.name}>
                                    {file.name}
                                </span>
                            )}
                        </div>

                        {/* Agent selector */}
                        <div className="mb-4">
                            <label className="block text-sm text-gray-400 mb-2">Import as Agent</label>
                            <div className="space-y-2 max-h-32 overflow-y-auto">
                                {agents.map(agent => (
                                    <div
                                        key={agent.id}
                                        onClick={() => setSelectedAgentId(agent.id)}
                                        className={`flex items-center gap-3 p-2 rounded-lg border cursor-pointer transition-all ${
                                            selectedAgentId === agent.id
                                                ? 'bg-nexus-accent/10 border-nexus-accent'
                                                : 'bg-white/5 border-white/10 hover:border-white/30'
                                        }`}
                                    >
                                        <img src={agent.avatar} className="w-6 h-6 rounded-full" alt="" />
                                        <span className="text-sm text-white">{agent.name}</span>
                                        {selectedAgentId === agent.id && (
                                            <div className="ml-auto w-2 h-2 rounded-full bg-nexus-accent" />
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Conversation selector */}
                        <div className="mb-4">
                            <div className="flex items-center justify-between mb-2">
                                <label className="text-sm text-gray-400">Conversations</label>
                                <button
                                    onClick={toggleAll}
                                    className="text-xs text-nexus-accent hover:text-nexus-accent/80 transition-colors"
                                >
                                    {selectedConvIds.size === preview.conversations.length ? 'Deselect All' : 'Select All'}
                                </button>
                            </div>
                            <div className="space-y-1 max-h-60 overflow-y-auto border border-white/5 rounded-xl p-2">
                                {preview.conversations.map((conv) => (
                                    <div
                                        key={conv.original_id}
                                        onClick={() => toggleConversation(conv.original_id)}
                                        className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ${
                                            selectedConvIds.has(conv.original_id)
                                                ? 'bg-white/10'
                                                : 'hover:bg-white/5'
                                        }`}
                                    >
                                        {selectedConvIds.has(conv.original_id) ? (
                                            <CheckCircle className="w-4 h-4 text-nexus-accent flex-shrink-0" />
                                        ) : (
                                            <Circle className="w-4 h-4 text-gray-600 flex-shrink-0" />
                                        )}
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm text-white truncate">{conv.title}</div>
                                            <div className="text-xs text-gray-500">
                                                {conv.message_count} msgs
                                                {conv.created_at && ` · ${new Date(conv.created_at).toLocaleDateString()}`}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Import actions */}
                        <div className="flex items-center justify-between">
                            <button
                                onClick={reset}
                                className="px-4 py-2 text-gray-400 hover:text-white transition-colors text-sm"
                            >
                                Back
                            </button>
                            <div className="flex items-center gap-3">
                                <span className="text-xs text-gray-500">
                                    {selectedConvIds.size} selected · {selectedMsgCount.toLocaleString()} msgs
                                </span>
                                <button
                                    onClick={handleImport}
                                    disabled={selectedConvIds.size === 0 || !selectedAgentId || loading}
                                    className="px-6 py-2 bg-nexus-accent text-nexus-900 rounded-xl font-bold flex items-center gap-2 hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all disabled:opacity-50"
                                >
                                    <Upload className="w-4 h-4" />
                                    Import
                                    <ChevronRight className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Step 3: Importing ── */}
                {step === 'importing' && (
                    <div className="flex flex-col items-center justify-center py-12">
                        <Loader2 className="w-12 h-12 text-nexus-accent animate-spin mb-4" />
                        <p className="text-white font-medium">Importing {selectedConvIds.size} conversations...</p>
                        <p className="text-sm text-gray-500 mt-1">{selectedMsgCount.toLocaleString()} messages to process</p>
                    </div>
                )}

                {/* ── Step 4: Done ── */}
                {step === 'done' && importResult && (
                    <div>
                        <div className="flex flex-col items-center py-8">
                            <CheckCircle className="w-16 h-16 text-green-400 mb-4" />
                            <h4 className="text-xl font-bold text-white mb-2">Import Complete</h4>
                            <div className="text-center space-y-1">
                                <p className="text-green-400">
                                    {importResult.imported} conversation{importResult.imported !== 1 ? 's' : ''} imported
                                </p>
                                <p className="text-sm text-gray-400">
                                    {importResult.total_messages.toLocaleString()} messages total
                                </p>
                                {importResult.skipped > 0 && (
                                    <p className="text-sm text-yellow-400">
                                        {importResult.skipped} skipped (already imported)
                                    </p>
                                )}
                            </div>
                        </div>

                        {importResult.errors.length > 0 && (
                            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
                                <p className="text-sm font-medium text-red-400 mb-1">Errors:</p>
                                {importResult.errors.map((err, i) => (
                                    <p key={i} className="text-xs text-red-400/70">{err}</p>
                                ))}
                            </div>
                        )}

                        <p className="text-xs text-gray-500 text-center mb-4">
                            Imported conversations are ready for harvesting. Harvest to extract memories.
                        </p>

                        <div className="flex justify-center gap-3">
                            <button
                                onClick={handleClose}
                                className="px-6 py-2 bg-nexus-accent text-nexus-900 rounded-xl font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all"
                            >
                                Done
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
