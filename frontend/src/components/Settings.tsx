/**
 * Settings Page — BYOK (Bring Your Own Key) + BYOD (Bring Your Own Database)
 *
 * Centralised key & database management. All keys are encrypted and stored
 * in the database via the FastAPI vault endpoints.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Key, Shield, Database, Plus, Trash2, Check,
    Loader2, LogIn, LogOut, User, ExternalLink,
    CheckCircle2, XCircle, AlertTriangle, Search,
    Zap, Mic, RefreshCw, ChevronDown, ChevronRight,
} from 'lucide-react';
import { useAuth } from './AuthProvider';
import { AuthModal } from './AuthModal';
import { DatabaseSettings } from './DatabaseSettings';
import {
    VaultProvider, SearchProvider,
    VAULT_PROVIDERS, SEARCH_PROVIDERS,
    VaultKeyInfo, VaultModeInfo,
    getVaultKeys, saveVaultKey, deleteVaultKey, testVaultKey,
    clearVaultCache, getVaultMode,
} from '../services/vaultApi';

// ─── Category groups for visual structure ────────────

interface ProviderGroup {
    title: string;
    icon: React.ReactNode;
    description: string;
    providers: VaultProvider[];
}

const PROVIDER_GROUPS: ProviderGroup[] = [
    {
        title: 'LLM Providers',
        icon: <Zap className="w-5 h-5" />,
        description: 'At least one key is required for chat to work. OpenRouter gives access to every model with a single key.',
        providers: ['openrouter', 'gemini', 'openai', 'anthropic', 'xai'],
    },
    {
        title: 'Voice & TTS',
        icon: <Mic className="w-5 h-5" />,
        description: 'Optional — enable text-to-speech for your companion\'s voice.',
        providers: ['elevenlabs', 'google_tts'],
    },
    {
        title: 'Web Search',
        icon: <Search className="w-5 h-5" />,
        description: 'Optional — let your AI search the web for current information.',
        providers: ['search'],
    },
];

// ─── Component ──────────────────────────────────────

export const Settings: React.FC = () => {
    const { user, logOut } = useAuth();
    const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

    // Vault key state
    const [keys, setKeys] = useState<Record<string, VaultKeyInfo>>({});
    const [loading, setLoading] = useState(false);

    // Add/Test key modal
    const [activeProvider, setActiveProvider] = useState<VaultProvider | null>(null);
    const [keyInput, setKeyInput] = useState('');
    const [searchProvider, setSearchProvider] = useState<SearchProvider>('exa');
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

    // Delete confirm
    const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

    // Section collapse state
    const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

    // Vault mode
    const [vaultMode, setVaultMode] = useState<VaultModeInfo | null>(null);

    // Load keys on auth + fetch mode
    useEffect(() => {
        // Always fetch vault mode (doesn't require auth)
        getVaultMode()
            .then(setVaultMode)
            .catch(() => setVaultMode(null));

        if (user) loadKeys();
        else setKeys({});
    }, [user]);

    const loadKeys = useCallback(async () => {
        if (!user) return;
        setLoading(true);
        try {
            const resp = await getVaultKeys(user.uid);
            setKeys(resp.keys || {});
        } catch (err) {
            console.error('Failed to load vault keys:', err);
        } finally {
            setLoading(false);
        }
    }, [user]);

    // ── Handlers ───────────────────────────────────────

    const openKeyModal = (provider: VaultProvider) => {
        setActiveProvider(provider);
        setKeyInput('');
        setTestResult(null);
        if (provider === 'search') {
            setSearchProvider('exa');
        }
    };

    const closeKeyModal = () => {
        setActiveProvider(null);
        setKeyInput('');
        setTestResult(null);
    };

    const handleTestKey = async () => {
        if (!activeProvider || !keyInput) return;
        setTesting(true);
        setTestResult(null);
        try {
            const result = await testVaultKey(activeProvider, keyInput);
            setTestResult({
                success: result.success,
                message: result.success
                    ? result.message || 'Key is valid!'
                    : result.error || 'Validation failed',
            });
        } catch (err: any) {
            setTestResult({ success: false, message: err.message || 'Test failed' });
        } finally {
            setTesting(false);
        }
    };

    const handleSaveKey = async () => {
        if (!user || !activeProvider || !keyInput) return;
        setSaving(true);
        try {
            const result = await saveVaultKey(
                user.uid,
                activeProvider,
                keyInput,
                activeProvider === 'search' ? searchProvider : undefined,
            );
            if (result.success) {
                await loadKeys();
                closeKeyModal();
            } else {
                setTestResult({ success: false, message: result.error || 'Save failed' });
            }
        } catch (err: any) {
            setTestResult({ success: false, message: err.message || 'Save failed' });
        } finally {
            setSaving(false);
        }
    };

    const handleDeleteKey = async (provider: string) => {
        if (!user) return;
        if (deleteConfirm === provider) {
            try {
                await deleteVaultKey(user.uid, provider);
                await loadKeys();
            } catch (err) {
                console.error('Failed to delete key:', err);
            }
            setDeleteConfirm(null);
        } else {
            setDeleteConfirm(provider);
            setTimeout(() => setDeleteConfirm(null), 3000);
        }
    };

    const handleClearCache = async () => {
        if (!user) return;
        try {
            await clearVaultCache(user.uid);
        } catch (err) {
            console.error('Failed to clear cache:', err);
        }
    };

    const toggleSection = (title: string) => {
        setCollapsedSections(prev => {
            const next = new Set(prev);
            if (next.has(title)) next.delete(title);
            else next.add(title);
            return next;
        });
    };

    // ── Count stats ───────────────────────────────────

    const configuredCount = Object.keys(keys).length;
    const hasLlmKey = ['openrouter', 'gemini', 'openai', 'anthropic', 'xai'].some(p => p in keys);

    // ── Unauthenticated ───────────────────────────────

    if (!user) {
        return (
            <div className="h-full p-6 lg:p-10 overflow-y-auto">
                <div className="max-w-4xl mx-auto">
                    <div className="mb-8">
                        <h2 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                            <Shield className="w-8 h-8 text-nexus-accent" />
                            Keys &amp; Database
                        </h2>
                        <p className="text-gray-400">
                            Bring your own API keys and database — ClingySOCKs never stores or provides AI credentials.
                        </p>
                    </div>

                    <div className="bg-white/5 border border-white/10 rounded-2xl p-8 text-center">
                        <LogIn className="w-16 h-16 text-nexus-accent mx-auto mb-4 opacity-50" />
                        <h3 className="text-xl font-bold text-white mb-2">Sign In Required</h3>
                        <p className="text-gray-400 mb-6 max-w-md mx-auto">
                            Sign in to securely store your API keys and database connection.
                            Everything is AES-256 encrypted in your personal vault.
                        </p>
                        <button
                            onClick={() => setIsAuthModalOpen(true)}
                            className="bg-nexus-accent text-nexus-900 px-8 py-3 rounded-xl font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all"
                        >
                            Sign In / Create Account
                        </button>
                    </div>

                    {/* Philosophy blurb */}
                    <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-cyan-500/5 border border-cyan-500/10 rounded-xl p-5">
                            <Key className="w-6 h-6 text-cyan-400 mb-3" />
                            <h4 className="text-white font-semibold mb-1">Bring Your Own Key</h4>
                            <p className="text-sm text-gray-400">
                                Use your own API keys from any provider — Gemini, OpenAI, Claude, Grok, or
                                OpenRouter for one-key access to 200+ models.
                            </p>
                        </div>
                        <div className="bg-blue-500/5 border border-blue-500/10 rounded-xl p-5">
                            <Database className="w-6 h-6 text-blue-400 mb-3" />
                            <h4 className="text-white font-semibold mb-1">Bring Your Own Database</h4>
                            <p className="text-sm text-gray-400">
                                Host your memories on your own PostgreSQL database. We never
                                see your data — you control everything.
                            </p>
                        </div>
                    </div>
                </div>
                <AuthModal isOpen={isAuthModalOpen} onClose={() => setIsAuthModalOpen(false)} />
            </div>
        );
    }

    // ── Authenticated ─────────────────────────────────

    return (
        <div className="h-full p-6 lg:p-10 overflow-y-auto">
            <div className="max-w-4xl mx-auto space-y-8">
                {/* Header */}
                <div className="flex justify-between items-end">
                    <div>
                        <h2 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                            <Shield className="w-8 h-8 text-nexus-accent" />
                            Keys &amp; Database
                        </h2>
                        <p className="text-gray-400">
                            Your keys are AES-256 encrypted and stored in your personal vault.
                        </p>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2 text-sm text-gray-400">
                            <User className="w-4 h-4" />
                            <span className="hidden sm:inline">{user.email}</span>
                        </div>
                        <button
                            onClick={logOut}
                            className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
                        >
                            <LogOut className="w-4 h-4" />
                            <span className="hidden sm:inline">Sign Out</span>
                        </button>
                    </div>
                </div>

                {/* Status Banner */}
                {vaultMode && (
                    <div className={`rounded-xl p-3 flex items-center gap-3 text-sm ${
                        vaultMode.mode === 'dev'
                            ? 'bg-amber-500/10 border border-amber-500/20'
                            : 'bg-green-500/10 border border-green-500/20'
                    }`}>
                        <span className={`px-2 py-0.5 rounded font-mono font-bold text-xs uppercase tracking-wider ${
                            vaultMode.mode === 'dev'
                                ? 'bg-amber-500/20 text-amber-400'
                                : 'bg-green-500/20 text-green-400'
                        }`}>
                            {vaultMode.mode}
                        </span>
                        <span className={vaultMode.mode === 'dev' ? 'text-amber-400/70' : 'text-green-400/70'}>
                            {vaultMode.mode === 'dev'
                                ? 'Dev mode — .env keys used as fallback when vault keys are not configured'
                                : 'Production — vault keys required, no .env fallback'
                            }
                        </span>
                    </div>
                )}

                {/* Key Status Banner */}
                {!hasLlmKey && !loading && (
                    <div className={`${
                        vaultMode?.mode === 'prod'
                            ? 'bg-red-500/10 border border-red-500/30'
                            : 'bg-amber-500/10 border border-amber-500/30'
                        } rounded-xl p-4 flex items-start gap-3`}>
                        <AlertTriangle className={`w-5 h-5 shrink-0 mt-0.5 ${
                            vaultMode?.mode === 'prod' ? 'text-red-400' : 'text-amber-400'
                        }`} />
                        <div>
                            <h4 className={`font-medium mb-1 ${
                                vaultMode?.mode === 'prod' ? 'text-red-400' : 'text-amber-400'
                            }`}>No Vault LLM Key Configured</h4>
                            <p className={`text-sm ${
                                vaultMode?.mode === 'prod' ? 'text-red-400/70' : 'text-amber-400/70'
                            }`}>
                                {vaultMode?.mode === 'prod'
                                    ? 'Production mode — users must add at least one LLM key (or OpenRouter) to start chatting.'
                                    : 'No vault keys yet — using .env fallback. Add keys here to use your own API credentials.'
                                }
                            </p>
                        </div>
                    </div>
                )}
                {hasLlmKey && !loading && (
                    <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 flex items-start gap-3">
                        <Shield className="w-5 h-5 text-green-500 shrink-0 mt-0.5" />
                        <div>
                            <h4 className="text-green-500 font-medium mb-1">Vault Active — {configuredCount} key{configuredCount !== 1 ? 's' : ''} configured</h4>
                            <p className="text-sm text-green-500/70">
                                Keys are encrypted with AES-256 and stored securely. They're decrypted only when making API calls.
                            </p>
                        </div>
                    </div>
                )}

                {/* Loading */}
                {loading && (
                    <div className="flex items-center justify-center py-16">
                        <Loader2 className="w-8 h-8 text-nexus-accent animate-spin" />
                    </div>
                )}

                {/* ── BYOK: API Keys by Category ─────────────── */}
                {!loading && (
                    <div className="space-y-6">
                        {PROVIDER_GROUPS.map(group => {
                            const isCollapsed = collapsedSections.has(group.title);
                            const groupConfigured = group.providers.filter(p => p in keys).length;

                            return (
                                <div key={group.title} className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
                                    {/* Group header */}
                                    <button
                                        onClick={() => toggleSection(group.title)}
                                        className="w-full px-6 py-4 border-b border-white/10 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className="text-nexus-accent">{group.icon}</span>
                                            <h3 className="text-lg font-bold text-white">{group.title}</h3>
                                            <span className="text-xs text-gray-500 bg-white/5 px-2 py-1 rounded">
                                                {groupConfigured}/{group.providers.length}
                                            </span>
                                        </div>
                                        {isCollapsed
                                            ? <ChevronRight className="w-5 h-5 text-gray-500" />
                                            : <ChevronDown className="w-5 h-5 text-gray-500" />
                                        }
                                    </button>

                                    {!isCollapsed && (
                                        <div className="p-4 space-y-3">
                                            <p className="text-xs text-gray-500 px-2 mb-2">{group.description}</p>

                                            {group.providers.map(provider => {
                                                const meta = VAULT_PROVIDERS[provider];
                                                const keyInfo = keys[provider];
                                                const isConfigured = !!keyInfo;

                                                return (
                                                    <div
                                                        key={provider}
                                                        className={`flex items-center justify-between p-4 rounded-xl border transition-all group ${isConfigured
                                                                ? 'bg-green-500/5 border-green-500/20'
                                                                : 'bg-nexus-900/50 border-white/5 hover:border-white/10'
                                                            }`}
                                                    >
                                                        <div className="flex items-center gap-4 flex-1 min-w-0">
                                                            <div className={`w-2 h-2 rounded-full shrink-0 ${isConfigured ? 'bg-green-500' : 'bg-gray-600'}`} />
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-2">
                                                                    <h4 className={`font-medium ${isConfigured ? 'text-white' : 'text-gray-300'}`}>
                                                                        {meta.name}
                                                                    </h4>
                                                                    {provider === 'openrouter' && !isConfigured && (
                                                                        <span className="bg-cyan-500/20 text-cyan-400 text-[10px] px-1.5 py-0.5 rounded font-medium uppercase tracking-wider">
                                                                            Recommended
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <p className="text-xs text-gray-500 mt-0.5">
                                                                    {isConfigured
                                                                        ? <>
                                                                            <code className="text-gray-400 font-mono">{keyInfo.maskedKey}</code>
                                                                            {keyInfo.searchProvider && (
                                                                                <span className="ml-2 text-yellow-400/70">({keyInfo.searchProvider})</span>
                                                                            )}
                                                                        </>
                                                                        : meta.description
                                                                    }
                                                                </p>
                                                            </div>
                                                        </div>

                                                        <div className="flex items-center gap-2">
                                                            {meta.docsUrl && (
                                                                <a
                                                                    href={meta.docsUrl}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="p-2 text-gray-500 hover:text-gray-300 transition-colors"
                                                                    title="Get API key"
                                                                    onClick={e => e.stopPropagation()}
                                                                >
                                                                    <ExternalLink className="w-4 h-4" />
                                                                </a>
                                                            )}

                                                            {isConfigured ? (
                                                                <>
                                                                    <button
                                                                        onClick={() => openKeyModal(provider)}
                                                                        className="px-3 py-1.5 text-xs bg-white/5 text-gray-300 rounded-lg hover:bg-white/10 transition-colors"
                                                                    >
                                                                        Update
                                                                    </button>
                                                                    <button
                                                                        onClick={() => handleDeleteKey(provider)}
                                                                        className={`p-2 rounded-lg transition-colors ${deleteConfirm === provider
                                                                                ? 'bg-red-500 text-white'
                                                                                : 'bg-red-500/10 hover:bg-red-500/20 text-red-400'
                                                                            }`}
                                                                        title={deleteConfirm === provider ? 'Click again to confirm' : 'Delete key'}
                                                                    >
                                                                        {deleteConfirm === provider ? <Check className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
                                                                    </button>
                                                                </>
                                                            ) : (
                                                                <button
                                                                    onClick={() => openKeyModal(provider)}
                                                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-nexus-accent/10 text-nexus-accent rounded-lg hover:bg-nexus-accent/20 transition-colors font-medium"
                                                                >
                                                                    <Plus className="w-3.5 h-3.5" />
                                                                    Add Key
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* ── BYOD: Database Section ─────────────────── */}
                <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
                    <button
                        onClick={() => toggleSection('database')}
                        className="w-full px-6 py-4 border-b border-white/10 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
                    >
                        <div className="flex items-center gap-3">
                            <Database className="w-5 h-5 text-blue-400" />
                            <h3 className="text-lg font-bold text-white">Database (BYOD)</h3>
                        </div>
                        {collapsedSections.has('database')
                            ? <ChevronRight className="w-5 h-5 text-gray-500" />
                            : <ChevronDown className="w-5 h-5 text-gray-500" />
                        }
                    </button>

                    {!collapsedSections.has('database') && (
                        <div className="p-6">
                            <DatabaseSettings userId={user.uid} />
                        </div>
                    )}
                </div>

                {/* ── Cache / System ─────────────────────────── */}
                <div className="p-5 bg-nexus-900/50 rounded-2xl border border-white/5 flex items-center justify-between">
                    <div>
                        <h4 className="text-sm font-bold text-gray-300 uppercase tracking-wider mb-1">
                            Vault Cache
                        </h4>
                        <p className="text-xs text-gray-500">
                            Keys are cached for 5 minutes. Clear if you just changed a key and it's not taking effect.
                        </p>
                    </div>
                    <button
                        onClick={handleClearCache}
                        className="flex items-center gap-2 px-4 py-2 text-sm bg-white/5 text-gray-300 rounded-lg hover:bg-white/10 transition-colors shrink-0"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Clear Cache
                    </button>
                </div>

                {/* ── Add/Update Key Modal ───────────────────── */}
                {activeProvider && (
                    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                        <div className="bg-nexus-800 border border-white/10 rounded-2xl p-8 w-full max-w-lg shadow-2xl">
                            <h3 className="text-2xl font-bold text-white mb-1 flex items-center gap-3">
                                <Key className={`w-6 h-6 ${VAULT_PROVIDERS[activeProvider].color}`} />
                                {keys[activeProvider] ? 'Update' : 'Add'} {VAULT_PROVIDERS[activeProvider].name} Key
                            </h3>
                            <p className="text-sm text-gray-500 mb-6">
                                {VAULT_PROVIDERS[activeProvider].description}
                            </p>

                            <div className="space-y-5">
                                {/* Search provider chooser */}
                                {activeProvider === 'search' && (
                                    <div>
                                        <label className="block text-sm text-gray-400 mb-2">Search Provider</label>
                                        <div className="grid grid-cols-2 gap-2">
                                            {(Object.keys(SEARCH_PROVIDERS) as SearchProvider[]).map(sp => (
                                                <button
                                                    key={sp}
                                                    onClick={() => setSearchProvider(sp)}
                                                    className={`p-2.5 rounded-lg border text-left transition-all ${searchProvider === sp
                                                            ? 'bg-nexus-accent/10 border-nexus-accent text-white'
                                                            : 'bg-nexus-900 border-white/10 text-gray-400 hover:border-white/20'
                                                        }`}
                                                >
                                                    <div className="font-medium text-sm">{SEARCH_PROVIDERS[sp].name}</div>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Key input */}
                                <div>
                                    <label className="block text-sm text-gray-400 mb-2">
                                        API Key
                                        {keys[activeProvider] && (
                                            <span className="text-green-400/70 ml-2">(current: {keys[activeProvider].maskedKey})</span>
                                        )}
                                    </label>
                                    <input
                                        type="password"
                                        value={keyInput}
                                        onChange={e => { setKeyInput(e.target.value); setTestResult(null); }}
                                        placeholder={
                                            activeProvider === 'search'
                                                ? SEARCH_PROVIDERS[searchProvider].placeholder
                                                : VAULT_PROVIDERS[activeProvider].placeholder
                                        }
                                        className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 text-white focus:border-nexus-accent outline-none font-mono text-sm"
                                        autoFocus
                                    />
                                    <p className="text-xs text-gray-600 mt-2 flex items-center gap-1.5">
                                        <Shield className="w-3 h-3" />
                                        Encrypted with AES-256-GCM before storage. Never exposed in plain text.
                                    </p>
                                </div>

                                {/* Get key link */}
                                {(VAULT_PROVIDERS[activeProvider].docsUrl || (activeProvider === 'search' && SEARCH_PROVIDERS[searchProvider]?.docsUrl)) && (
                                    <a
                                        href={activeProvider === 'search'
                                            ? SEARCH_PROVIDERS[searchProvider]?.docsUrl
                                            : VAULT_PROVIDERS[activeProvider].docsUrl
                                        }
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-sm text-nexus-accent/70 hover:text-nexus-accent flex items-center gap-1.5"
                                    >
                                        <ExternalLink className="w-3.5 h-3.5" />
                                        Get a {activeProvider === 'search' ? SEARCH_PROVIDERS[searchProvider]?.name : VAULT_PROVIDERS[activeProvider].name} API key →
                                    </a>
                                )}

                                {/* Test result */}
                                {testResult && (
                                    <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${testResult.success
                                            ? 'bg-green-500/10 border border-green-500/20 text-green-400'
                                            : 'bg-red-500/10 border border-red-500/20 text-red-400'
                                        }`}>
                                        {testResult.success
                                            ? <CheckCircle2 className="w-4 h-4 shrink-0" />
                                            : <XCircle className="w-4 h-4 shrink-0" />
                                        }
                                        <span>{testResult.message}</span>
                                    </div>
                                )}
                            </div>

                            {/* Actions */}
                            <div className="flex justify-between items-center mt-8">
                                <button
                                    onClick={handleTestKey}
                                    disabled={!keyInput || testing}
                                    className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm bg-white/5 text-gray-300 hover:bg-white/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                    {testing
                                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Testing…</>
                                        : <><CheckCircle2 className="w-4 h-4" /> Test Key</>
                                    }
                                </button>

                                <div className="flex gap-3">
                                    <button
                                        onClick={closeKeyModal}
                                        className="px-5 py-2.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        onClick={handleSaveKey}
                                        disabled={!keyInput || saving}
                                        className="px-5 py-2.5 rounded-lg bg-nexus-accent text-nexus-900 font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.3)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                    >
                                        {saving
                                            ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                                            : <><Key className="w-4 h-4" /> {keys[activeProvider] ? 'Update Key' : 'Save Key'}</>
                                        }
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
