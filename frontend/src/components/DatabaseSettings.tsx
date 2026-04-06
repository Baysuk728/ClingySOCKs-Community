/**
 * Database Settings Component — BYOD (Bring Your Own Database)
 *
 * Uses the FastAPI /vault/database endpoints for database management.
 */
import React, { useState, useEffect } from 'react';
import {
    Database, CheckCircle2, XCircle, Loader2,
    ExternalLink, AlertCircle, Server, Play, Zap,
} from 'lucide-react';
import {
    DatabaseProvider,
    DATABASE_PROVIDERS,
    getDatabaseConfig,
    saveDatabaseConfig,
    testDatabaseConnection,
    initDatabase,
    activateDatabase,
    getDatabaseStatus,
    DatabaseConfigResponse,
    DatabaseStatus,
} from '../services/vaultApi';

interface DatabaseSettingsProps {
    userId: string;
}

export const DatabaseSettings: React.FC<DatabaseSettingsProps> = ({ userId }) => {
    const [provider, setProvider] = useState<DatabaseProvider>('supabase');
    const [connectionString, setConnectionString] = useState('');
    const [schema, setSchema] = useState('public');
    const [testing, setTesting] = useState(false);
    const [saving, setSaving] = useState(false);
    const [initializing, setInitializing] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
    const [config, setConfig] = useState<DatabaseConfigResponse | null>(null);
    const [loadingConfig, setLoadingConfig] = useState(true);
    const [dbStatus, setDbStatus] = useState<DatabaseStatus | null>(null);
    const [activating, setActivating] = useState(false);

    // Load existing config + database status on mount
    useEffect(() => {
        loadConfig();
        loadDbStatus();
    }, [userId]);

    const loadConfig = async () => {
        setLoadingConfig(true);
        try {
            const data = await getDatabaseConfig(userId);
            setConfig(data);
            if (data.configured && data.provider) {
                setProvider(data.provider as DatabaseProvider);
                setSchema(data.schema || 'public');
            }
        } catch (error) {
            console.error('Failed to load database config:', error);
        } finally {
            setLoadingConfig(false);
        }
    };

    const loadDbStatus = async () => {
        try {
            const status = await getDatabaseStatus();
            setDbStatus(status);
        } catch (error) {
            console.error('Failed to load database status:', error);
        }
    };

    const handleTestConnection = async () => {
        if (!connectionString) {
            setTestResult({ success: false, message: 'Please enter a connection string' });
            return;
        }
        setTesting(true);
        setTestResult(null);
        try {
            const result = await testDatabaseConnection(connectionString);
            setTestResult({
                success: result.success,
                message: result.success
                    ? `Connected! Latency: ${result.latency_ms}ms`
                    : result.error || 'Connection failed',
            });
        } catch (error: any) {
            setTestResult({ success: false, message: error.message || 'Connection test failed' });
        } finally {
            setTesting(false);
        }
    };

    const handleSave = async () => {
        if (!connectionString) {
            setTestResult({ success: false, message: 'Please enter a connection string' });
            return;
        }
        setSaving(true);
        try {
            const result = await saveDatabaseConfig(userId, provider, connectionString, schema);
            if (result.success) {
                setTestResult({ success: true, message: 'Database configuration saved and encrypted!' });
                setConnectionString(''); // Clear for security
                await loadConfig(); // Refresh config status
            } else {
                setTestResult({ success: false, message: result.error || 'Failed to save' });
            }
        } catch (error: any) {
            setTestResult({ success: false, message: error.message || 'Failed to save configuration' });
        } finally {
            setSaving(false);
        }
    };

    const handleInitDatabase = async () => {
        setInitializing(true);
        setTestResult(null);
        try {
            const result = await initDatabase(userId);
            if (result.success) {
                setTestResult({
                    success: true,
                    message: `Database initialized! ${result.tables_created || 'All'} tables created.`
                        + (result.activated ? ' Now active as primary database.' : ''),
                });
                await loadConfig();    // Refresh config status
                await loadDbStatus();  // Refresh active DB status
            } else {
                setTestResult({ success: false, message: result.error || 'Initialization failed' });
            }
        } catch (error: any) {
            setTestResult({ success: false, message: error.message || 'Initialization failed' });
        } finally {
            setInitializing(false);
        }
    };

    const handleActivateDatabase = async () => {
        setActivating(true);
        setTestResult(null);
        try {
            const result = await activateDatabase(userId);
            if (result.success) {
                setTestResult({ success: true, message: 'Database activated as primary database!' });
                await loadDbStatus();
            } else {
                setTestResult({ success: false, message: result.error || 'Activation failed' });
            }
        } catch (error: any) {
            setTestResult({ success: false, message: error.message || 'Activation failed' });
        } finally {
            setActivating(false);
        }
    };

    if (loadingConfig) {
        return (
            <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 text-nexus-accent animate-spin" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Active database status */}
            {dbStatus && (
                <div className={`flex items-center justify-between gap-3 p-4 rounded-xl border ${
                    dbStatus.source === 'vault'
                        ? 'bg-green-500/5 border-green-500/20'
                        : dbStatus.source === 'none'
                            ? 'bg-red-500/5 border-red-500/20'
                            : dbStatus.mode === 'prod'
                                ? 'bg-amber-500/5 border-amber-500/20'
                                : 'bg-white/5 border-white/10'
                }`}>
                    <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                            !dbStatus.connected ? 'bg-red-500' : dbStatus.source === 'vault' ? 'bg-green-500' : 'bg-amber-500'
                        }`} />
                        <div className="min-w-0">
                            {dbStatus.source === 'none' ? (
                                <>
                                    <p className="text-sm font-medium text-red-400">
                                        No database connected
                                    </p>
                                    <p className="text-xs text-red-400/70 mt-0.5">
                                        VAULT_MODE=prod — configure a database below to get started
                                    </p>
                                </>
                            ) : (
                                <>
                                    <p className={`text-sm font-medium ${
                                        dbStatus.source === 'vault' ? 'text-green-400' : 'text-gray-300'
                                    }`}>
                                        Active DB: <code className="font-mono text-xs opacity-80">{dbStatus.host}</code>
                                    </p>
                                    <p className="text-xs text-gray-500 mt-0.5">
                                        Source: {dbStatus.source === 'vault' ? 'Vault (BYOD)' : '.env fallback (dev mode)'}
                                        {dbStatus.source === 'env' && dbStatus.mode === 'prod' && (
                                            <span className="text-amber-400 ml-1">— configure a BYOD database below</span>
                                        )}
                                    </p>
                                </>
                            )}
                        </div>
                    </div>
                    {/* If config is initialized but DB source is not vault, show activate button */}
                    {config?.configured && config?.initialized && dbStatus.source !== 'vault' && (
                        <button
                            onClick={handleActivateDatabase}
                            disabled={activating}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-nexus-accent/10 text-nexus-accent rounded-lg hover:bg-nexus-accent/20 transition-colors font-medium shrink-0 disabled:opacity-50"
                        >
                            {activating
                                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Activating…</>
                                : <><Zap className="w-3.5 h-3.5" /> Activate</>
                            }
                        </button>
                    )}
                </div>
            )}

            {/* Per-user config status */}
            {config?.configured && (
                <div className={`flex items-center gap-3 p-4 rounded-xl border ${config.initialized
                        ? 'bg-green-500/5 border-green-500/20'
                        : 'bg-amber-500/5 border-amber-500/20'
                    }`}>
                    <div className={`w-2.5 h-2.5 rounded-full ${config.initialized ? 'bg-green-500' : 'bg-amber-500'}`} />
                    <div className="flex-1">
                        <p className={`text-sm font-medium ${config.initialized ? 'text-green-400' : 'text-amber-400'}`}>
                            {config.initialized
                                ? `Connected — ${config.provider} (schema: ${config.schema})`
                                : `Configured — ${config.provider} (not yet initialized)`
                            }
                        </p>
                        {!config.initialized && (
                            <p className="text-xs text-amber-400/70 mt-0.5">
                                Click "Initialize Tables" below to create the required database schema.
                            </p>
                        )}
                    </div>
                    {config.configured && !config.initialized && (
                        <button
                            onClick={handleInitDatabase}
                            disabled={initializing}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-amber-500/10 text-amber-400 rounded-lg hover:bg-amber-500/20 transition-colors font-medium disabled:opacity-50"
                        >
                            {initializing
                                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Initializing…</>
                                : <><Play className="w-3.5 h-3.5" /> Initialize Tables</>
                            }
                        </button>
                    )}
                </div>
            )}

            {/* Info banner */}
            <div className="bg-blue-500/5 border border-blue-500/10 rounded-xl p-4">
                <p className="text-sm text-blue-400/70">
                    Connect your own PostgreSQL database (requires pgvector extension).
                    All conversations, memories, and data will be stored there — not on our servers.
                </p>
            </div>

            {/* Provider Selection */}
            <div>
                <label className="block text-sm text-gray-400 mb-2">Database Provider</label>
                <div className="grid grid-cols-2 gap-3">
                    {(Object.keys(DATABASE_PROVIDERS) as DatabaseProvider[]).map((p) => {
                        const meta = DATABASE_PROVIDERS[p];
                        return (
                            <button
                                key={p}
                                onClick={() => setProvider(p)}
                                className={`p-3 rounded-lg border transition-all text-left ${provider === p
                                        ? 'bg-nexus-accent/10 border-nexus-accent text-nexus-accent'
                                        : 'bg-nexus-900 border-white/10 text-gray-400 hover:border-white/20'
                                    }`}
                            >
                                <div className="font-medium capitalize flex items-center gap-2">
                                    <Server className="w-4 h-4" />
                                    {meta.name}
                                </div>
                                <div className="text-xs mt-1 opacity-70">{meta.description}</div>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Connection String */}
            <div>
                <label className="block text-sm text-gray-400 mb-2">
                    Connection String
                    {config?.configured && (
                        <span className="text-green-400 ml-2">✓ Already saved</span>
                    )}
                </label>
                <input
                    type="password"
                    value={connectionString}
                    onChange={(e) => { setConnectionString(e.target.value); setTestResult(null); }}
                    placeholder="postgresql://user:password@host:5432/database"
                    className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 text-white text-sm focus:border-nexus-accent outline-none font-mono"
                />
                <p className="text-xs text-gray-600 mt-2">
                    🔒 Encrypted with AES-256-GCM before storage. Your connection string is never exposed.
                </p>
            </div>

            {/* Schema */}
            <div>
                <label className="block text-sm text-gray-400 mb-2">Schema</label>
                <input
                    type="text"
                    value={schema}
                    onChange={(e) => setSchema(e.target.value)}
                    placeholder="public"
                    className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 text-white focus:border-nexus-accent outline-none text-sm"
                />
            </div>

            {/* Buttons */}
            <div className="flex flex-wrap gap-3">
                <button
                    onClick={handleTestConnection}
                    disabled={testing || !connectionString}
                    className="flex items-center gap-2 bg-white/5 text-white px-5 py-2.5 rounded-xl font-medium hover:bg-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                    {testing
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Testing…</>
                        : <><Database className="w-4 h-4" /> Test Connection</>
                    }
                </button>

                <button
                    onClick={handleSave}
                    disabled={saving || !connectionString}
                    className="flex items-center gap-2 bg-nexus-accent text-nexus-900 px-5 py-2.5 rounded-xl font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                    {saving
                        ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                        : <><CheckCircle2 className="w-4 h-4" /> Save &amp; Encrypt</>
                    }
                </button>

                {config?.configured && !config?.initialized && (
                    <button
                        onClick={handleInitDatabase}
                        disabled={initializing}
                        className="flex items-center gap-2 bg-blue-500/10 text-blue-400 px-5 py-2.5 rounded-xl font-medium hover:bg-blue-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                    >
                        {initializing
                            ? <><Loader2 className="w-4 h-4 animate-spin" /> Initializing…</>
                            : <><Play className="w-4 h-4" /> Initialize Tables</>
                        }
                    </button>
                )}
            </div>

            {/* Test Result */}
            {testResult && (
                <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${testResult.success
                        ? 'bg-green-500/10 border border-green-500/20 text-green-400'
                        : 'bg-red-500/10 border border-red-500/20 text-red-400'
                    }`}>
                    {testResult.success ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <XCircle className="w-4 h-4 shrink-0" />}
                    <span>{testResult.message}</span>
                </div>
            )}

            {/* Provider links */}
            <div className="flex flex-wrap gap-3 pt-2">
                {(Object.entries(DATABASE_PROVIDERS) as [DatabaseProvider, typeof DATABASE_PROVIDERS[DatabaseProvider]][])
                    .filter(([, meta]) => meta.docsUrl)
                    .map(([key, meta]) => (
                        <a
                            key={key}
                            href={meta.docsUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors"
                        >
                            <ExternalLink className="w-3 h-3" />
                            {meta.name}
                        </a>
                    ))
                }
            </div>
        </div>
    );
};
