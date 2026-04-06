import React, { useState, useRef, useEffect } from 'react';
import { Agent } from '../types';
import { 
  Upload, Database, FileText, CheckCircle, Loader2, Search, 
  Brain, Sparkles, AlertCircle, X, Check, Eye, EyeOff
} from 'lucide-react';
import { 
  processHarvest, 
  approveMemories, 
  getMemories, 
  searchMemories,
  HarvestResult,
  MemoryDecision 
} from '../services/api';

interface MemoryLabProps {
  agents: Agent[];
}

type ViewMode = 'upload' | 'processing' | 'review' | 'saved';
type ReviewTab = 'all' | 'to-save';

export const MemoryLab: React.FC<MemoryLabProps> = ({ agents }) => {
  const [viewMode, setViewMode] = useState<ViewMode>('upload');
  const [reviewTab, setReviewTab] = useState<ReviewTab>('to-save');
  const [isDragging, setIsDragging] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [useSemanticChunking, setUseSemanticChunking] = useState(true);

  // Add custom scrollbar styles
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      .memory-lab-scrollbar::-webkit-scrollbar {
        width: 10px;
      }
      .memory-lab-scrollbar::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.2);
        border-radius: 5px;
      }
      .memory-lab-scrollbar::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.3);
        border-radius: 5px;
      }
      .memory-lab-scrollbar::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.5);
      }
    `;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);
  
  // Harvest state
  const [harvestResult, setHarvestResult] = useState<HarvestResult | null>(null);
  const [selectedDecisions, setSelectedDecisions] = useState<Set<number>>(new Set());
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Saved memories state
  const [savedMemories, setSavedMemories] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load saved memories when view changes to 'saved'
  useEffect(() => {
    if (viewMode === 'saved' && selectedAgent) {
      loadSavedMemories();
    }
  }, [viewMode, selectedAgent]);

  const loadSavedMemories = async () => {
    if (!selectedAgent) return;
    
    try {
      const memories = await getMemories(selectedAgent.id, 50, 0);
      setSavedMemories(memories);
    } catch (error) {
      console.error('Failed to load memories:', error);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleFile = async (file: File) => {
    if (!selectedAgent) {
      setError('Please select an agent first');
      return;
    }

    setError(null);
    setIsProcessing(true);
    setViewMode('processing');

    try {
      const fileContent = await file.text();
      
      const result = await processHarvest(
        fileContent,
        selectedAgent.id,
        selectedAgent.name,
        useSemanticChunking
      );

      if (!result.success) {
        throw new Error(result.error || 'Harvest failed');
      }

      setHarvestResult(result);
      
      // NEW: Unified harvester saves automatically - show saved memories
      // If there are no decisions (new system), memories are already saved
      if (result.total_deltas && result.total_deltas > 0) {
        // Memories already saved by unified harvester - show them
        setViewMode('saved');
        loadSavedMemories(); // Reload to show newly saved memories
      } else {
        // Fallback: old system with decisions - show review
        const proposedIndices = new Set<number>();
        result.proposed_decisions?.forEach((_, idx) => {
          proposedIndices.add(idx);
        });
        setSelectedDecisions(proposedIndices);
        setViewMode('review');
      }
      
      setIsProcessing(false);
    } catch (error) {
      setError((error as Error).message);
      setIsProcessing(false);
      setViewMode('upload');
    }
  };

  const handleSaveMemories = async () => {
    if (!harvestResult || !selectedAgent) return;

    setIsSaving(true);
    setError(null);

    try {
      // Combine auto-approved and selected proposed decisions
      const decisionsToSave = [
        ...harvestResult.auto_approved_decisions,
        ...harvestResult.proposed_decisions.filter((_, idx) => selectedDecisions.has(idx))
      ];

      if (decisionsToSave.length === 0) {
        setError('No memories selected to save');
        setIsSaving(false);
        return;
      }

      const result = await approveMemories(selectedAgent.id, decisionsToSave);

      if (!result.success) {
        throw new Error('Failed to save memories');
      }

      // Success!
      setViewMode('saved');
      loadSavedMemories();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim() || !selectedAgent) return;

    setIsSearching(true);
    try {
      const results = await searchMemories(searchQuery, selectedAgent.id, 10);
      setSearchResults(results);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsSearching(false);
    }
  };

  const toggleDecision = (idx: number) => {
    const newSelected = new Set(selectedDecisions);
    if (newSelected.has(idx)) {
      newSelected.delete(idx);
    } else {
      newSelected.add(idx);
    }
    setSelectedDecisions(newSelected);
  };

  const selectAll = () => {
    if (!harvestResult) return;
    const allIndices = new Set<number>();
    harvestResult.proposed_decisions.forEach((_, idx) => allIndices.add(idx));
    setSelectedDecisions(allIndices);
  };

  const deselectAll = () => {
    setSelectedDecisions(new Set());
  };

  return (
    <div className="h-full p-6 lg:p-10 flex flex-col">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
          <Database className="w-8 h-8 text-nexus-cosy" />
          Memory Harvest Lab
        </h2>
        <p className="text-gray-400">
          Extract memories from conversation logs using AI-powered semantic analysis
        </p>
      </div>

      {error && (
        <div className="mb-6 bg-red-500/10 border border-red-500/50 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-red-400 font-medium">Error</p>
            <p className="text-red-300 text-sm">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="ml-auto text-red-400 hover:text-red-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      )}

      {/* VIEW: Upload */}
      {viewMode === 'upload' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left: Upload Zone */}
          <div className="lg:col-span-1 space-y-6">
            {/* Agent Selection */}
            <div className="bg-nexus-900/50 rounded-xl p-6 border border-white/5">
              <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider mb-4">
                Select Agent
              </h3>
              <select
                value={selectedAgent?.id || ''}
                onChange={(e) => {
                  const agent = agents.find(a => a.id === e.target.value);
                  setSelectedAgent(agent || null);
                }}
                className="w-full bg-nexus-800 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-nexus-accent"
              >
                <option value="">Choose an agent...</option>
                {agents.map(agent => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} ({agent.provider})
                  </option>
                ))}
              </select>
            </div>

            {/* Chunking Strategy */}
            <div className="bg-nexus-900/50 rounded-xl p-6 border border-white/5">
              <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider mb-4">
                Chunking Strategy
              </h3>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={useSemanticChunking}
                  onChange={(e) => setUseSemanticChunking(e.target.checked)}
                  className="w-5 h-5 rounded border-white/10 bg-nexus-800 text-nexus-accent focus:ring-nexus-accent"
                />
                <div>
                  <div className="text-white font-medium">Semantic Chunking</div>
                  <div className="text-sm text-gray-400">
                    {useSemanticChunking ? 'Topic-aware (better for poems)' : 'Time-based (faster)'}
                  </div>
                </div>
              </label>
            </div>

            {/* Upload Zone */}
            <div
              className={`
                h-64 border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-6 text-center transition-all cursor-pointer
                ${isDragging ? 'border-nexus-accent bg-nexus-accent/5' : 'border-white/10 hover:border-white/30 bg-white/5'}
                ${!selectedAgent ? 'opacity-50 cursor-not-allowed' : ''}
              `}
              onDragOver={(e) => { e.preventDefault(); if (selectedAgent) setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => selectedAgent && fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".json,.txt,.md,.csv"
                onChange={handleFileSelect}
                disabled={!selectedAgent}
              />
              <div className="w-16 h-16 rounded-full bg-nexus-900 flex items-center justify-center mb-4">
                <Upload className="w-8 h-8 text-gray-400" />
              </div>
              <h3 className="text-lg font-medium text-white mb-2">
                {selectedAgent ? 'Drop Chat Logs Here' : 'Select an Agent First'}
              </h3>
              <p className="text-sm text-gray-500">
                Supports JSON exports from ChatGPT/Claude, or plain text
              </p>
            </div>
          </div>

          {/* Right: Info */}
          <div className="lg:col-span-2 bg-nexus-800/30 rounded-2xl border border-white/5 p-8">
            <div className="flex items-center gap-3 mb-6">
              <Sparkles className="w-6 h-6 text-nexus-accent" />
              <h3 className="text-xl font-bold text-white">How It Works</h3>
            </div>
            
            <div className="space-y-4">
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-nexus-accent/20 flex items-center justify-center text-nexus-accent font-bold">
                  1
                </div>
                <div>
                  <h4 className="text-white font-medium mb-1">Upload Conversation</h4>
                  <p className="text-gray-400 text-sm">
                    Drop a ChatGPT or Claude JSON export. We support various formats.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-nexus-accent/20 flex items-center justify-center text-nexus-accent font-bold">
                  2
                </div>
                <div>
                  <h4 className="text-white font-medium mb-1">AI Extraction</h4>
                  <p className="text-gray-400 text-sm">
                    DSPy-powered AI analyzes the conversation, detects creative content (poems, stories), and extracts rich, contextual memories.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-nexus-accent/20 flex items-center justify-center text-nexus-accent font-bold">
                  3
                </div>
                <div>
                  <h4 className="text-white font-medium mb-1">Review & Approve</h4>
                  <p className="text-gray-400 text-sm">
                    High-confidence memories are auto-approved. Review proposed memories and select which to save.
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-nexus-accent/20 flex items-center justify-center text-nexus-accent font-bold">
                  4
                </div>
                <div>
                  <h4 className="text-white font-medium mb-1">Vector Storage</h4>
                  <p className="text-gray-400 text-sm">
                    Memories are embedded and stored in Qdrant for semantic search. Your agent can now recall these moments.
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-8 p-4 bg-nexus-accent/10 border border-nexus-accent/30 rounded-lg">
              <div className="flex items-start gap-3">
                <Brain className="w-5 h-5 text-nexus-accent flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-nexus-accent font-medium text-sm mb-1">Semantic Chunking</p>
                  <p className="text-gray-300 text-xs">
                    Uses AI embeddings to detect topic shifts and preserve creative content (poems, stories) intact. 
                    Better for non-linear conversations and ADHD-friendly memory extraction.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* VIEW: Processing */}
      {viewMode === 'processing' && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Loader2 className="w-16 h-16 text-nexus-accent animate-spin mx-auto mb-6" />
            <h3 className="text-2xl font-bold text-white mb-2">Processing Conversation</h3>
            <p className="text-gray-400">
              Extracting memories using {useSemanticChunking ? 'semantic' : 'time-based'} chunking...
            </p>
            <p className="text-gray-500 text-sm mt-4">This may take 30-60 seconds for large files</p>
          </div>
        </div>
      )}

      {/* VIEW: Review */}
      {viewMode === 'review' && harvestResult && (
        <div className="flex-1 flex flex-col">
          {/* Stats */}
          <div className="grid grid-cols-5 gap-4 mb-6">
            <div className="bg-green-500/10 border border-green-500/50 rounded-xl p-4">
              <div className="text-green-400 text-2xl font-bold">{harvestResult.auto_approved}</div>
              <div className="text-green-300 text-sm">Auto-Approved</div>
            </div>
            <div className="bg-yellow-500/10 border border-yellow-500/50 rounded-xl p-4">
              <div className="text-yellow-400 text-2xl font-bold">{harvestResult.proposed}</div>
              <div className="text-yellow-300 text-sm">For Review</div>
            </div>
            <div className="bg-purple-500/10 border border-purple-500/50 rounded-xl p-4">
              <div className="text-purple-400 text-2xl font-bold">{selectedDecisions.size}</div>
              <div className="text-purple-300 text-sm">Selected</div>
            </div>
            <div className="bg-gray-500/10 border border-gray-500/50 rounded-xl p-4">
              <div className="text-gray-400 text-2xl font-bold">{harvestResult.skipped}</div>
              <div className="text-gray-300 text-sm">Skipped</div>
            </div>
            <div className="bg-nexus-accent/10 border border-nexus-accent/50 rounded-xl p-4">
              <div className="text-nexus-accent text-2xl font-bold">
                {harvestResult.auto_approved + selectedDecisions.size}
              </div>
              <div className="text-nexus-cosy text-sm">Will Be Saved</div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex gap-3">
              <button
                onClick={selectAll}
                className="px-4 py-2 bg-nexus-accent/20 hover:bg-nexus-accent/30 text-nexus-accent rounded-lg transition-colors text-sm font-medium"
              >
                Select All
              </button>
              <button
                onClick={deselectAll}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg transition-colors text-sm font-medium"
              >
                Deselect All
              </button>
            </div>
            <button
              onClick={handleSaveMemories}
              disabled={isSaving || (harvestResult.auto_approved === 0 && selectedDecisions.size === 0)}
              className="px-6 py-3 bg-nexus-accent hover:bg-nexus-accent/80 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium flex items-center gap-2"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <CheckCircle className="w-5 h-5" />
                  Save {harvestResult.auto_approved + selectedDecisions.size} Memories
                </>
              )}
            </button>
          </div>

          {/* Memory List */}
          <div className="flex-1 bg-nexus-800/30 rounded-2xl border border-white/5 overflow-hidden flex flex-col">
            {/* Tabs */}
            <div className="border-b border-white/5">
              <div className="flex items-center gap-2 p-2">
                <button
                  onClick={() => setReviewTab('to-save')}
                  className={`flex-1 px-4 py-3 rounded-lg font-medium transition-colors ${
                    reviewTab === 'to-save'
                      ? 'bg-nexus-accent text-white'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    <span>Will Be Saved ({harvestResult.auto_approved + selectedDecisions.size})</span>
                  </div>
                </button>
                <button
                  onClick={() => setReviewTab('all')}
                  className={`flex-1 px-4 py-3 rounded-lg font-medium transition-colors ${
                    reviewTab === 'all'
                      ? 'bg-nexus-accent text-white'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-center gap-2">
                    <FileText className="w-4 h-4" />
                    <span>All Extracted ({harvestResult.total_processed})</span>
                  </div>
                </button>
              </div>
            </div>

            {/* Tab Content - Scrollable */}
            <div 
              className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0 memory-lab-scrollbar"
              style={{
                scrollbarWidth: 'thin',
                scrollbarColor: 'rgba(255,255,255,0.3) rgba(0,0,0,0.1)',
                maxHeight: '100%'
              }}
            >
              {/* "Will Be Saved" Tab - Show only what will actually be saved */}
              {reviewTab === 'to-save' && (
                <>
                  {/* Info message */}
                  <div className="p-3 bg-nexus-accent/10 border border-nexus-accent/30 rounded-lg">
                    <p className="text-nexus-accent text-sm">
                      These {harvestResult.auto_approved + selectedDecisions.size} memories will be saved to Qdrant when you click "Save Memories" below.
                    </p>
                  </div>

                  {/* Auto-approved memories (always saved) */}
                  {harvestResult.auto_approved_decisions.map((decision, idx) => (
                    <div
                      key={`auto-${idx}`}
                      className="p-4 bg-green-500/5 border border-green-500/30 rounded-xl"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <CheckCircle className="w-5 h-5 text-green-400" />
                          <span className="text-green-400 font-medium text-sm">Auto-Approved</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                            {decision.importance}
                          </span>
                          {decision.memory_domain && (
                            <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 text-xs">
                              {decision.memory_domain}
                            </span>
                          )}
                          <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-medium">
                            {(decision.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <p className="text-gray-200 text-sm leading-relaxed break-words whitespace-pre-wrap">{decision.memory_content}</p>
                      {decision.memory_subtype && (
                        <div className="mt-2 flex items-center gap-2">
                          <span className="text-gray-500 text-xs">Type:</span>
                          <span className="px-2 py-0.5 rounded bg-nexus-800 text-gray-300 text-xs">
                            {decision.memory_subtype}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Selected proposed memories (user approved) */}
                  {harvestResult.proposed_decisions
                    .filter((_, idx) => selectedDecisions.has(idx))
                    .map((decision, originalIdx) => {
                      const idx = harvestResult.proposed_decisions.indexOf(decision);
                      return (
                        <div
                          key={`selected-${idx}`}
                          className="p-4 bg-nexus-accent/10 border border-nexus-accent/50 rounded-xl cursor-pointer"
                          onClick={() => toggleDecision(idx)}
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <Check className="w-5 h-5 text-nexus-accent" />
                              <span className="text-nexus-accent font-medium text-sm">Selected</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                                {decision.importance}
                              </span>
                              {decision.memory_domain && (
                                <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 text-xs">
                                  {decision.memory_domain}
                                </span>
                              )}
                              <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-medium">
                                {(decision.confidence * 100).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                          <p className="text-gray-200 text-sm leading-relaxed break-words whitespace-pre-wrap">{decision.memory_content}</p>
                          {decision.memory_subtype && (
                            <div className="mt-2 flex items-center gap-2">
                              <span className="text-gray-500 text-xs">Type:</span>
                              <span className="px-2 py-0.5 rounded bg-nexus-800 text-gray-300 text-xs">
                                {decision.memory_subtype}
                              </span>
                            </div>
                          )}
                          <p className="text-gray-500 text-xs mt-2">Click to deselect</p>
                        </div>
                      );
                    })}

                  {harvestResult.auto_approved === 0 && selectedDecisions.size === 0 && (
                    <div className="text-center text-gray-600 mt-20">
                      <AlertCircle className="w-12 h-12 mx-auto mb-4 opacity-20" />
                      <p>No memories selected to save</p>
                      <p className="text-sm mt-2">Switch to "All Extracted" to review and select memories</p>
                    </div>
                  )}
                </>
              )}

              {/* "All Extracted" Tab - Show everything for review */}
              {reviewTab === 'all' && (
                <>
                  {/* Auto-approved memories */}
                  {harvestResult.auto_approved_decisions.map((decision, idx) => (
                <div
                  key={`auto-${idx}`}
                  className="p-4 bg-green-500/5 border border-green-500/30 rounded-xl"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-green-400" />
                      <span className="text-green-400 font-medium text-sm">Auto-Approved</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                        {decision.importance}
                      </span>
                      <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-medium">
                        {(decision.confidence * 100).toFixed(0)}% confident
                      </span>
                    </div>
                  </div>
                  <p className="text-gray-200 text-sm leading-relaxed">{decision.memory_content}</p>
                  {decision.reasoning && (
                    <p className="text-gray-500 text-xs mt-2 italic">{decision.reasoning}</p>
                  )}
                </div>
              ))}

              {/* Proposed memories (user can select) */}
              {harvestResult.proposed_decisions.map((decision, idx) => (
                <div
                  key={`proposed-${idx}`}
                  className={`p-4 border rounded-xl cursor-pointer transition-all ${
                    selectedDecisions.has(idx)
                      ? 'bg-nexus-accent/10 border-nexus-accent/50'
                      : 'bg-white/5 border-white/10 hover:border-white/30'
                  }`}
                  onClick={() => toggleDecision(idx)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {selectedDecisions.has(idx) ? (
                        <Check className="w-5 h-5 text-nexus-accent" />
                      ) : (
                        <Eye className="w-5 h-5 text-gray-400" />
                      )}
                      <span className="text-gray-300 font-medium text-sm">
                        {selectedDecisions.has(idx) ? 'Selected' : 'Click to Select'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                        {decision.importance}
                      </span>
                      {decision.memory_domain && (
                        <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 text-xs">
                          {decision.memory_domain}
                        </span>
                      )}
                      <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-medium">
                        {(decision.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <p className="text-gray-200 text-sm leading-relaxed">{decision.memory_content}</p>
                  {decision.memory_subtype && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-gray-500 text-xs">Type:</span>
                      <span className="px-2 py-0.5 rounded bg-nexus-800 text-gray-300 text-xs">
                        {decision.memory_subtype}
                      </span>
                    </div>
                  )}
                </div>
              ))}

              {/* Proposed memories (user can select) */}
              {harvestResult.proposed_decisions.map((decision, idx) => (
                <div
                  key={`proposed-all-${idx}`}
                  className={`p-4 border rounded-xl cursor-pointer transition-all ${
                    selectedDecisions.has(idx)
                      ? 'bg-nexus-accent/10 border-nexus-accent/50'
                      : 'bg-white/5 border-white/10 hover:border-white/30'
                  }`}
                  onClick={() => toggleDecision(idx)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {selectedDecisions.has(idx) ? (
                        <Check className="w-5 h-5 text-nexus-accent" />
                      ) : (
                        <Eye className="w-5 h-5 text-gray-400" />
                      )}
                      <span className="text-gray-300 font-medium text-sm">
                        {selectedDecisions.has(idx) ? 'Selected for Save' : 'Click to Select'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                        {decision.importance}
                      </span>
                      {decision.memory_domain && (
                        <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 text-xs">
                          {decision.memory_domain}
                        </span>
                      )}
                      <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-medium">
                        {(decision.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <p className="text-gray-200 text-sm leading-relaxed">{decision.memory_content}</p>
                  {decision.memory_subtype && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-gray-500 text-xs">Type:</span>
                      <span className="px-2 py-0.5 rounded bg-nexus-800 text-gray-300 text-xs">
                        {decision.memory_subtype}
                      </span>
                    </div>
                  )}
                  {decision.reasoning && (
                    <p className="text-gray-500 text-xs mt-2 italic">Why: {decision.reasoning}</p>
                  )}
                </div>
              ))}

              {/* Skipped info */}
              {harvestResult.skipped > 0 && (
                <div className="p-4 bg-gray-500/5 border border-gray-500/20 rounded-lg">
                  <div className="flex items-center gap-3">
                    <EyeOff className="w-5 h-5 text-gray-500" />
                    <div>
                      <p className="text-gray-400 text-sm font-medium">
                        {harvestResult.skipped} memories skipped
                      </p>
                      <p className="text-gray-500 text-xs">
                        Low confidence (&lt;50%) - likely greetings or filler content
                      </p>
                    </div>
                  </div>
                </div>
              )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* VIEW: Saved */}
      {viewMode === 'saved' && (
        <div className="flex-1 flex flex-col">
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-xl font-bold text-white">
                Memories Saved Successfully!
              </h3>
            </div>
            <button
              onClick={() => {
                setViewMode('upload');
                setHarvestResult(null);
                setSelectedDecisions(new Set());
                setReviewTab('to-save');
              }}
              className="px-4 py-2 bg-nexus-accent hover:bg-nexus-accent/80 text-white rounded-lg transition-colors"
            >
              Upload Another
            </button>
          </div>

          {/* Search */}
          <div className="mb-6 flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search memories semantically..."
                className="w-full bg-nexus-800 border border-white/10 rounded-lg pl-12 pr-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-nexus-accent"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={isSearching || !searchQuery.trim()}
              className="px-6 py-3 bg-nexus-accent hover:bg-nexus-accent/80 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
            >
              {isSearching ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Search'}
            </button>
          </div>

          {/* Memory List */}
          <div className="flex-1 bg-nexus-800/30 rounded-2xl border border-white/5 overflow-hidden flex flex-col">
            <div className="p-4 border-b border-white/5">
              <h3 className="text-white font-medium">
                {searchResults.length > 0 ? `Search Results (${searchResults.length})` : `All Memories (${savedMemories.length})`}
              </h3>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0 memory-lab-scrollbar" style={{
              scrollbarWidth: 'thin',
              scrollbarColor: 'rgba(255,255,255,0.3) rgba(0,0,0,0.1)',
              maxHeight: '100%'
            }}>
              {(searchResults.length > 0 ? searchResults : savedMemories).map((item: any, idx: number) => {
                const memory = 'memory' in item ? item.memory : item;
                const score = 'score' in item ? item.score : null;
                
                return (
                  <div
                    key={idx}
                    className="p-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <FileText className="w-5 h-5 text-nexus-accent" />
                        <span className="text-gray-300 font-medium text-sm">
                          {memory.subtype || 'Memory'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {score && (
                          <span className="px-2 py-1 rounded bg-nexus-accent/20 text-nexus-accent text-xs font-medium">
                            {(score * 100).toFixed(0)}% match
                          </span>
                        )}
                        <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                          {memory.importance}
                        </span>
                        {memory.memory_domain && (
                          <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 text-xs">
                            {memory.memory_domain}
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="text-gray-200 text-sm leading-relaxed break-words whitespace-pre-wrap">{memory.content}</p>
                    {memory.summary && memory.summary !== memory.content.slice(0, 200) && (
                      <p className="text-gray-500 text-xs mt-2 italic">{memory.summary}</p>
                    )}
                  </div>
                );
              })}
              {savedMemories.length === 0 && searchResults.length === 0 && (
                <div className="text-center text-gray-600 mt-20">
                  <Database className="w-12 h-12 mx-auto mb-4 opacity-20" />
                  <p>No memories found</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* VIEW: Saved */}
      {viewMode === 'saved' && (
        <div className="flex-1 flex flex-col">
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <h3 className="text-xl font-bold text-white">
                Memories Saved Successfully!
              </h3>
            </div>
            <button
              onClick={() => {
                setViewMode('upload');
                setHarvestResult(null);
                setSelectedDecisions(new Set());
              }}
              className="px-4 py-2 bg-nexus-accent hover:bg-nexus-accent/80 text-white rounded-lg transition-colors"
            >
              Upload Another
            </button>
          </div>

          {/* Search */}
          <div className="mb-6 flex gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search memories semantically..."
                className="w-full bg-nexus-800 border border-white/10 rounded-lg pl-12 pr-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-nexus-accent"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={isSearching || !searchQuery.trim()}
              className="px-6 py-3 bg-nexus-accent hover:bg-nexus-accent/80 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-medium"
            >
              {isSearching ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Search'}
            </button>
          </div>

          {/* Memory List */}
          <div className="flex-1 bg-nexus-800/30 rounded-2xl border border-white/5 overflow-hidden flex flex-col">
            <div className="p-4 border-b border-white/5">
              <h3 className="text-white font-medium">
                {searchResults.length > 0 ? `Search Results (${searchResults.length})` : `All Memories (${savedMemories.length})`}
              </h3>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0 memory-lab-scrollbar" style={{
              scrollbarWidth: 'thin',
              scrollbarColor: 'rgba(255,255,255,0.3) rgba(0,0,0,0.1)',
              maxHeight: '100%'
            }}>
              {(searchResults.length > 0 ? searchResults : savedMemories).map((item: any, idx: number) => {
                const memory = 'memory' in item ? item.memory : item;
                const score = 'score' in item ? item.score : null;
                
                return (
                  <div
                    key={idx}
                    className="p-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <FileText className="w-5 h-5 text-nexus-accent" />
                        <span className="text-gray-300 font-medium text-sm">
                          {memory.subtype || 'Memory'}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {score && (
                          <span className="px-2 py-1 rounded bg-nexus-accent/20 text-nexus-accent text-xs font-medium">
                            {(score * 100).toFixed(0)}% match
                          </span>
                        )}
                        <span className="px-2 py-1 rounded bg-white/10 text-gray-300 text-xs">
                          {memory.importance}
                        </span>
                        {memory.memory_domain && (
                          <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 text-xs">
                            {memory.memory_domain}
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="text-gray-200 text-sm leading-relaxed break-words whitespace-pre-wrap">{memory.content}</p>
                    {memory.summary && memory.summary !== memory.content.slice(0, 200) && (
                      <p className="text-gray-500 text-xs mt-2 italic">{memory.summary}</p>
                    )}
                  </div>
                );
              })}
              {savedMemories.length === 0 && searchResults.length === 0 && (
                <div className="text-center text-gray-600 mt-20">
                  <Database className="w-12 h-12 mx-auto mb-4 opacity-20" />
                  <p>No memories found</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
