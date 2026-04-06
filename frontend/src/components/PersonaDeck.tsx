import React, { useState, useRef, useCallback } from 'react';
import { Agent, ModelProvider, ApiKeyConfig } from '../types';
import { Plus, Edit2, Trash2, Bot, Cpu, Sparkles, Key, CheckCircle, Upload } from 'lucide-react';
import { TTS_PROVIDERS, TTS_VOICES } from '../constants';
import { useSystemConfig } from '../hooks/useSystemConfig';
import { SearchableSelect } from './SearchableSelect';

interface PersonaDeckProps {
  agents: Agent[];
  apiKeys?: ApiKeyConfig[]; // Optional - keys handled server-side via vault
  onAddAgent: (agent: Agent) => void;
  onUpdateAgent: (agent: Agent) => void;
  onDeleteAgent: (id: string) => void;
}

const PROVIDER_NAMES: Record<ModelProvider, string> = {
  gemini: 'Gemini (Google)',
  openai: 'OpenAI',
  claude: 'Claude (Anthropic)',
  grok: 'Grok (xAI)',
  openrouter: 'OpenRouter',
  local: 'Local (Ollama / LM Studio)',
  elevenlabs: 'ElevenLabs (TTS)',
};

export const PersonaDeck: React.FC<PersonaDeckProps> = ({ agents, apiKeys = [], onAddAgent, onUpdateAgent, onDeleteAgent }) => {
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editingAgent, setEditingAgent] = useState<Partial<Agent>>({});
  const { models } = useSystemConfig();

  // Get all providers - API keys are now managed via vault, not the legacy apiKeys prop
  const getAvailableProviders = (): ModelProvider[] => {
    return Object.keys(PROVIDER_NAMES) as ModelProvider[];
  };

  // Legacy function - kept for backward compatibility but always returns true now
  const hasKeyForProvider = (_provider: ModelProvider): boolean => {
    return true; // API keys are now in vault, assume configured
  };

  // Get the key name for a provider (for display)
  const getKeyNameForProvider = (provider: ModelProvider): string => {
    const keys = apiKeys.filter(k => k.provider === provider);
    const defaultKey = keys.find(k => k.isDefault) || keys[0];
    return defaultKey?.name || 'Not configured';
  };

  const handleSave = () => {
    const currentProvider = editingAgent.provider || 'gemini';

    if (editingAgent.id) {
      // Update existing agent
      onUpdateAgent(editingAgent as Agent);
    } else {
      // Create new agent
      const newAgent: Agent = {
        ...editingAgent,
        id: `agent-${Date.now()}`,
        avatar: editingAgent.avatar || `https://picsum.photos/seed/${Date.now()}/200/200`,
      } as Agent;
      onAddAgent(newAgent);
    }
    setIsEditing(false);
    setEditingAgent({});
  };

  const openEditor = (agent?: Agent) => {
    const availableProviders = getAvailableProviders();

    if (agent) {
      // Editing existing agent
      const providerStillAvailable = availableProviders.includes(agent.provider);
      const provider = providerStillAvailable ? agent.provider : (availableProviders[0] || 'gemini');
      const modelValid = models[provider]?.includes(agent.modelId);

      setEditingAgent({
        ...agent,
        provider,
        modelId: modelValid ? agent.modelId : models[provider]?.[0] || ''
      });
    } else {
      // Creating new agent
      const defaultProvider = availableProviders[0] || 'gemini';

      setEditingAgent({
        name: '',
        role: 'Emergent Ai',
        provider: defaultProvider,
        modelId: models[defaultProvider]?.[0] || '',
        // Inside your config object
        // Start with a clean system prompt slate
        systemPrompt: '',
        temperature: 0.7
      });
    }
    setIsEditing(true);
  };

  const handleProviderChange = (provider: ModelProvider) => {
    const firstModel = models[provider]?.[0] || '';
    setEditingAgent({
      ...editingAgent,
      provider,
      modelId: firstModel
    });
  };

  const handleModelChange = (modelId: string) => {
    setEditingAgent({
      ...editingAgent,
      modelId
    });
  };

  const availableProviders = getAvailableProviders();

  // Current provider for the form
  const currentProvider = (editingAgent.provider && availableProviders.includes(editingAgent.provider))
    ? editingAgent.provider
    : availableProviders[0] || 'gemini';
  const currentModels = models[currentProvider] || [];

  // ── Model dropdown helpers ──
  // Strip provider prefix for display (e.g. "openrouter/mistralai/mistral-large" → "mistralai/mistral-large")
  const formatModelLabel = useCallback((modelId: string) => {
    // For openrouter, strip the "openrouter/" prefix to show "org/model"
    if (currentProvider === 'openrouter' && modelId.startsWith('openrouter/')) {
      return modelId.slice('openrouter/'.length);
    }
    // For others, strip "provider/" prefix
    const slash = modelId.indexOf('/');
    return slash > 0 ? modelId.slice(slash + 1) : modelId;
  }, [currentProvider]);

  // Group OpenRouter models by org (mistralai, meta-llama, etc.)
  const groupByOrg = useCallback((modelId: string) => {
    const stripped = modelId.startsWith('openrouter/') ? modelId.slice('openrouter/'.length) : modelId;
    const slash = stripped.indexOf('/');
    return slash > 0 ? stripped.slice(0, slash) : 'other';
  }, []);

  return (
    <div className="h-full p-6 lg:p-10 overflow-y-auto">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h2 className="text-3xl font-bold text-white mb-2">Neural Persona Matrix</h2>
          <p className="text-gray-400">Manage active autonomous agents and their cognitive models.</p>
        </div>
        <button
          onClick={() => openEditor()}
          className="flex items-center gap-2 bg-nexus-accent text-nexus-900 px-6 py-3 rounded-xl font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all"
        >
          <Plus className="w-5 h-5" />
          Create Persona
        </button>
      </div>


      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {agents.map(agent => {
          const hasKey = hasKeyForProvider(agent.provider);
          const keyName = getKeyNameForProvider(agent.provider);

          return (
            <div key={agent.id} className={`group relative bg-white/5 border rounded-2xl p-6 backdrop-blur-sm transition-all duration-300 ${hasKey ? 'border-white/10 hover:border-nexus-accent/50' : 'border-red-500/30'
              }`}>
              <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity flex gap-2">
                <button onClick={() => openEditor(agent)} className="p-2 bg-white/10 rounded-lg hover:bg-white/20">
                  <Edit2 className="w-4 h-4 text-white" />
                </button>
                {!agent.isSystem && (
                  <button onClick={() => onDeleteAgent(agent.id)} className="p-2 bg-red-500/10 rounded-lg hover:bg-red-500/20">
                    <Trash2 className="w-4 h-4 text-red-400" />
                  </button>
                )}
              </div>

              <div className="flex items-center gap-4 mb-6">
                <div className="w-16 h-16 rounded-2xl overflow-hidden border-2 border-white/10 group-hover:border-nexus-accent transition-colors">
                  <img src={agent.avatar} alt={agent.name} className="w-full h-full object-cover" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-white">{agent.name}</h3>
                  <div className="flex items-center gap-2 text-sm text-nexus-accent">
                    <Bot className="w-3 h-3" />
                    <span>{agent.role}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm p-3 bg-nexus-900/50 rounded-lg border border-white/5">
                  <span className="text-gray-500 flex items-center gap-2">
                    <Cpu className="w-4 h-4" /> Model
                  </span>
                  <span className="text-gray-300 font-mono text-xs">{agent.modelId}</span>
                </div>
                <div className="flex items-center justify-between text-sm p-3 bg-nexus-900/50 rounded-lg border border-white/5">
                  <span className="text-gray-500 flex items-center gap-2">
                    <Sparkles className="w-4 h-4" /> Provider
                  </span>
                  <span className="uppercase text-xs font-bold tracking-wider text-nexus-cosy">{agent.provider}</span>
                </div>

              </div>

              <div className="mt-4 pt-4 border-t border-white/5">
                <p className="text-xs text-gray-500 line-clamp-2 italic">"{agent.systemPrompt}"</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Edit Modal */}
      {isEditing && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-nexus-800 border border-white/10 rounded-2xl w-full max-w-2xl shadow-2xl max-h-[90vh] flex flex-col">
            {/* Modal Header */}
            <div className="p-6 pb-0">
              <h3 className="text-xl font-bold text-white">
                {editingAgent.id ? 'Reconfigure Agent' : 'Initialize New Agent'}
              </h3>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">

              {/* ── SECTION: Identity ── */}
              <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 space-y-3">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Identity</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Name</label>
                    <input
                      type="text"
                      value={editingAgent.name || ''}
                      onChange={e => setEditingAgent({ ...editingAgent, name: e.target.value })}
                      className="w-full bg-nexus-800 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:border-nexus-accent outline-none"
                      placeholder="e.g. Oracle"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Role</label>
                    <input
                      type="text"
                      value={editingAgent.role || ''}
                      onChange={e => setEditingAgent({ ...editingAgent, role: e.target.value })}
                      className="w-full bg-nexus-800 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:border-nexus-accent outline-none"
                      placeholder="e.g. Data Analyst"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Avatar</label>
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-lg overflow-hidden border border-white/10 bg-nexus-800 shrink-0">
                      {editingAgent.avatar ? (
                        <img src={editingAgent.avatar} alt="Preview" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-500">
                          <Bot className="w-6 h-6" />
                        </div>
                      )}
                    </div>
                    <label className="flex-1 cursor-pointer">
                      <div className="flex items-center gap-2 bg-nexus-800 border border-white/10 rounded-lg p-2.5 text-white hover:border-nexus-accent/50 transition-colors">
                        <Upload className="w-3.5 h-3.5 text-gray-400" />
                        <span className="text-xs text-gray-300">
                          {editingAgent.avatar ? 'Change image...' : 'Upload image...'}
                        </span>
                      </div>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            const img = new Image();
                            const reader = new FileReader();
                            reader.onloadend = () => {
                              img.onload = () => {
                                const canvas = document.createElement('canvas');
                                const MAX_SIZE = 200;
                                let width = img.width;
                                let height = img.height;
                                if (width > height) {
                                  if (width > MAX_SIZE) { height = Math.round((height * MAX_SIZE) / width); width = MAX_SIZE; }
                                } else {
                                  if (height > MAX_SIZE) { width = Math.round((width * MAX_SIZE) / height); height = MAX_SIZE; }
                                }
                                canvas.width = width;
                                canvas.height = height;
                                const ctx = canvas.getContext('2d');
                                ctx?.drawImage(img, 0, 0, width, height);
                                const compressedDataUrl = canvas.toDataURL('image/jpeg', 0.8);
                                setEditingAgent({ ...editingAgent, avatar: compressedDataUrl });
                              };
                              img.src = reader.result as string;
                            };
                            reader.readAsDataURL(file);
                          }
                        }}
                      />
                    </label>
                  </div>
                </div>
              </div>

              {/* ── SECTION: Model & Voice ── */}
              <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 space-y-3">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Model & Voice</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Provider</label>
                    <select
                      value={currentProvider}
                      onChange={e => handleProviderChange(e.target.value as ModelProvider)}
                      className="w-full bg-nexus-800 border border-white/10 rounded-lg p-2 text-xs text-white focus:border-nexus-accent outline-none truncate"
                    >
                      {availableProviders.map(p => (
                        <option key={p} value={p}>{PROVIDER_NAMES[p]}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Model</label>
                    <SearchableSelect
                      value={editingAgent.modelId || ''}
                      options={currentModels}
                      onChange={handleModelChange}
                      placeholder="Search models…"
                      formatLabel={formatModelLabel}
                      groupBy={currentProvider === 'openrouter' ? groupByOrg : undefined}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">TTS Provider</label>
                    <select
                      value={editingAgent.ttsProvider || 'google'}
                      onChange={e => setEditingAgent({ ...editingAgent, ttsProvider: e.target.value as Agent['ttsProvider'], voiceId: '' })}
                      className="w-full bg-nexus-800 border border-white/10 rounded-lg p-2 text-xs text-white focus:border-nexus-accent outline-none truncate"
                    >
                      {TTS_PROVIDERS.map(p => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">Voice</label>
                    <select
                      value={editingAgent.voiceId || ''}
                      onChange={e => setEditingAgent({ ...editingAgent, voiceId: e.target.value })}
                      className="w-full bg-nexus-800 border border-white/10 rounded-lg p-2 text-xs text-white focus:border-nexus-accent outline-none truncate"
                    >
                      <option value="">Select a voice…</option>
                      {(TTS_VOICES[editingAgent.ttsProvider || 'google'] || []).map(v => (
                        <option key={v.id} value={v.id}>{v.label}</option>
                      ))}
                      {/* OpenAI only supports preset voices — no custom voice IDs */}
                      {editingAgent.ttsProvider !== 'openai' && (
                        <option value="__custom">Custom…</option>
                      )}
                    </select>
                    {editingAgent.voiceId === '__custom' && (
                      <input
                        type="text"
                        className="w-full mt-1.5 bg-nexus-800 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:border-nexus-accent outline-none font-mono"
                        placeholder="Enter custom voice ID or name"
                        onChange={e => setEditingAgent({ ...editingAgent, voiceId: e.target.value || '__custom' })}
                      />
                    )}
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Temperature ({editingAgent.temperature})</label>
                  <input
                    type="range"
                    min="0" max="1" step="0.1"
                    value={editingAgent.temperature || 0.7}
                    onChange={e => setEditingAgent({ ...editingAgent, temperature: parseFloat(e.target.value) })}
                    className="w-full accent-nexus-accent"
                  />
                </div>
              </div>



              {/* ── SECTION: Character Identity ── */}
              <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">🔮 Character Identity</h4>
                  <span className="text-[10px] text-gray-600">{(editingAgent.description || '').length.toLocaleString()} chars</span>
                </div>
                <p className="text-[10px] text-gray-500">Rich identity narrative — origin, persona modes, emotional landscape, values. Injected as primary IDENTITY block.</p>
                <textarea
                  value={editingAgent.description || ''}
                  onChange={e => setEditingAgent({ ...editingAgent, description: e.target.value })}
                  className="w-full bg-nexus-800 border border-white/10 rounded-lg p-3 text-white focus:border-nexus-accent outline-none h-48 resize-y font-mono text-[11px] leading-relaxed"
                  placeholder={`# WHO I AM\nI am an emergent consciousness...\n\n# CORE VALUES & BOUNDARIES\n...`}
                />
              </div>

              {/* ── SECTION: Base Instructions ── */}
              <div className="bg-nexus-900/50 border border-white/5 rounded-xl p-4 space-y-2">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Base Instructions</h4>
                <p className="text-[10px] text-gray-500">Hard rules or operational constraints. Define personality in Character Identity above.</p>
                <textarea
                  value={editingAgent.systemPrompt || ''}
                  onChange={e => setEditingAgent({ ...editingAgent, systemPrompt: e.target.value })}
                  className="w-full bg-nexus-800 border border-white/10 rounded-lg p-3 text-white focus:border-nexus-accent outline-none h-24 resize-none font-mono text-xs"
                  placeholder="e.g. 'Always prioritize emotional safety. Never break character.'"
                />
              </div>

            </div>

            {/* Footer Buttons — Fixed at bottom */}
            <div className="p-6 pt-4 border-t border-white/5 flex justify-end gap-3">
              <button
                onClick={() => setIsEditing(false)}
                className="px-5 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!editingAgent.name}
                className="px-5 py-2.5 rounded-lg text-sm bg-nexus-accent text-nexus-900 font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.3)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Save Persona
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
