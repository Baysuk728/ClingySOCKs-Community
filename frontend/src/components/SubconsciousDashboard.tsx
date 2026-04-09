import React, { useState, useEffect } from 'react';
import { Brain, Zap, Link2, TrendingUp, AlertTriangle, RefreshCw, Clock, Loader2, Ghost, Lightbulb } from 'lucide-react';
import { Agent } from '../types';
import {
  getSubconsciousStatus,
  triggerSubconsciousCycle,
  SubconsciousResult,
  Orphan,
  Pattern,
  Proposal,
} from '../services/enhancedApi';

interface Props {
  agents: Agent[];
}

type Tab = 'overview' | 'orphans' | 'patterns' | 'proposals' | 'mood';

export const SubconsciousDashboard: React.FC<Props> = ({ agents }) => {
  const [selectedEntity, setSelectedEntity] = useState<string>(agents[0]?.id || '');
  const [data, setData] = useState<SubconsciousResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('overview');

  const fetchData = async (entityId: string) => {
    if (!entityId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getSubconsciousStatus(entityId);
      setData(result);
    } catch (e: any) {
      setError(e.message || 'Failed to load');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const runCycle = async () => {
    if (!selectedEntity) return;
    setRunning(true);
    setError(null);
    try {
      const result = await triggerSubconsciousCycle(selectedEntity);
      setData(result);
    } catch (e: any) {
      setError(e.message || 'Cycle failed');
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (selectedEntity) fetchData(selectedEntity);
  }, [selectedEntity]);

  useEffect(() => {
    if (agents.length && !selectedEntity) setSelectedEntity(agents[0].id);
  }, [agents]);

  const tabs: { id: Tab; label: string; icon: React.ElementType; count?: number }[] = [
    { id: 'overview', label: 'Overview', icon: Brain },
    { id: 'orphans', label: 'Orphans', icon: Ghost, count: data?.orphans?.length },
    { id: 'patterns', label: 'Patterns', icon: Link2, count: data?.patterns?.length },
    { id: 'proposals', label: 'Proposals', icon: Lightbulb, count: data?.proposals?.length },
    { id: 'mood', label: 'Mood Trends', icon: TrendingUp },
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-nexus-900 overflow-hidden">
      {/* Header */}
      <div className="border-b border-white/5 bg-nexus-800/30 backdrop-blur-xl px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center">
              <Brain className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Subconscious</h1>
              <p className="text-xs text-gray-500">Background analysis &amp; memory hygiene</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Agent Selector */}
            <select
              value={selectedEntity}
              onChange={(e) => setSelectedEntity(e.target.value)}
              className="bg-nexus-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-nexus-accent/50"
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>

            {/* Run Cycle */}
            <button
              onClick={runCycle}
              disabled={running || !selectedEntity}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 border border-purple-500/20 transition-all disabled:opacity-40"
            >
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              {running ? 'Running...' : 'Run Cycle'}
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-4">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all ${
                tab === t.id
                  ? 'bg-white/10 text-white'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
              }`}
            >
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-purple-500/20 text-purple-400 text-[10px] font-bold">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading && !data && (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 text-purple-400 animate-spin" />
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-4 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-red-400 text-sm font-medium">Error</p>
              <p className="text-red-400/70 text-xs mt-1">{error}</p>
            </div>
          </div>
        )}

        {!loading && !data && !error && (
          <EmptyState onRun={runCycle} />
        )}

        {data && tab === 'overview' && <OverviewPanel data={data} />}
        {data && tab === 'orphans' && <OrphansList orphans={data.orphans || []} error={data.orphans_error} />}
        {data && tab === 'patterns' && <PatternsList patterns={data.patterns || []} error={data.patterns_error} />}
        {data && tab === 'proposals' && <ProposalsList proposals={data.proposals || []} error={data.proposals_error} />}
        {data && tab === 'mood' && <MoodPanel trends={data.mood_trends} error={data.mood_trends_error} />}
      </div>
    </div>
  );
};

// ── Sub-Components ──

const EmptyState: React.FC<{ onRun: () => void }> = ({ onRun }) => (
  <div className="flex flex-col items-center justify-center h-64 text-center">
    <div className="w-16 h-16 rounded-full bg-purple-500/10 flex items-center justify-center mb-4">
      <Brain className="w-8 h-8 text-purple-400/50" />
    </div>
    <p className="text-gray-500 mb-4">No subconscious data yet.</p>
    <button
      onClick={onRun}
      className="px-4 py-2 rounded-lg bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 border border-purple-500/20 transition-all text-sm"
    >
      Run First Cycle
    </button>
  </div>
);

const StatCard: React.FC<{ label: string; value: string | number; icon: React.ElementType; color?: string }> = ({
  label, value, icon: Icon, color = 'purple',
}) => (
  <div className="bg-nexus-800/40 border border-white/5 rounded-xl p-4">
    <div className="flex items-center gap-2 mb-2">
      <Icon className={`w-4 h-4 text-${color}-400`} />
      <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
    </div>
    <p className="text-2xl font-bold text-white">{value}</p>
  </div>
);

const OverviewPanel: React.FC<{ data: SubconsciousResult }> = ({ data }) => {
  const moodPoints = data.mood_trends?.data_points || 0;
  return (
    <div className="space-y-6">
      {/* Timestamp */}
      {data.timestamp && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Clock className="w-3 h-3" />
          Last run: {new Date(data.timestamp).toLocaleString()}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Orphan Memories" value={data.orphans?.length || 0} icon={Ghost} color="amber" />
        <StatCard label="Hidden Patterns" value={data.patterns?.length || 0} icon={Link2} color="blue" />
        <StatCard label="Proposals" value={data.proposals?.length || 0} icon={Lightbulb} color="green" />
        <StatCard label="Mood Data Points" value={moodPoints} icon={TrendingUp} color="pink" />
      </div>

      {/* Quick Summaries */}
      {data.proposals && data.proposals.length > 0 && (
        <div className="bg-nexus-800/40 border border-white/5 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-green-400" /> Top Proposals
          </h3>
          <div className="space-y-2">
            {data.proposals.slice(0, 3).map((p, i) => (
              <div key={i} className="text-sm text-gray-400 flex items-start gap-2">
                <span className="text-green-400/60 mt-0.5">•</span>
                <span>{p.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mood Snapshot */}
      {data.mood_trends?.averages && (
        <div className="bg-nexus-800/40 border border-white/5 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-pink-400" /> Mood Snapshot ({data.mood_trends.period_days}d)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(data.mood_trends.averages).map(([dim, avg]) => {
              const trend = data.mood_trends?.trends?.[dim];
              const trendIcon = trend === 'rising' ? '↑' : trend === 'falling' ? '↓' : '→';
              const trendColor = trend === 'rising' ? 'text-green-400' : trend === 'falling' ? 'text-red-400' : 'text-gray-500';
              return (
                <div key={dim} className="text-center">
                  <div className="text-xs text-gray-500 mb-1">{dim.replace('_', ' ')}</div>
                  <div className="text-lg font-bold text-white">{(avg as number).toFixed(2)}</div>
                  <div className={`text-xs ${trendColor}`}>{trendIcon} {trend}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

const OrphansList: React.FC<{ orphans: Orphan[]; error?: string }> = ({ orphans, error }) => (
  <div className="space-y-3">
    {error && <p className="text-red-400/70 text-sm">{error}</p>}
    {orphans.length === 0 && !error && (
      <p className="text-gray-500 text-sm">No orphan memories found — your graph is well-connected!</p>
    )}
    {orphans.map((o, i) => (
      <div key={i} className="bg-nexus-800/40 border border-white/5 rounded-xl p-4 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
              {o.type}
            </span>
          </div>
          <p className="text-sm text-white font-medium">{o.label}</p>
          {o.created_at && (
            <p className="text-xs text-gray-500 mt-1">{new Date(o.created_at).toLocaleDateString()}</p>
          )}
        </div>
        <Ghost className="w-4 h-4 text-amber-400/30 shrink-0" />
      </div>
    ))}
  </div>
);

const PatternsList: React.FC<{ patterns: Pattern[]; error?: string }> = ({ patterns, error }) => (
  <div className="space-y-3">
    {error && <p className="text-red-400/70 text-sm">{error}</p>}
    {patterns.length === 0 && !error && (
      <p className="text-gray-500 text-sm">No hidden patterns detected yet — more data may reveal connections.</p>
    )}
    {patterns.map((p, i) => (
      <div key={i} className="bg-nexus-800/40 border border-white/5 rounded-xl p-4">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
            {p.node_a.split(':').pop()}
          </span>
          <Link2 className="w-3 h-3 text-blue-400/40" />
          <span className="text-xs px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
            {p.node_b.split(':').pop()}
          </span>
        </div>
        <p className="text-sm text-gray-400">{p.suggestion}</p>
        <p className="text-xs text-gray-600 mt-1">{p.shared_neighbors} shared connections</p>
      </div>
    ))}
  </div>
);

const ProposalsList: React.FC<{ proposals: Proposal[]; error?: string }> = ({ proposals, error }) => (
  <div className="space-y-3">
    {error && <p className="text-red-400/70 text-sm">{error}</p>}
    {proposals.length === 0 && !error && (
      <p className="text-gray-500 text-sm">No proposals generated — run a cycle to analyze your memory graph.</p>
    )}
    {proposals.map((p, i) => (
      <div key={i} className="bg-nexus-800/40 border border-white/5 rounded-xl p-4 flex items-start gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
          p.type === 'orphan_rescue' ? 'bg-amber-500/10' : 'bg-blue-500/10'
        }`}>
          {p.type === 'orphan_rescue'
            ? <Ghost className="w-4 h-4 text-amber-400" />
            : <Link2 className="w-4 h-4 text-blue-400" />
          }
        </div>
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${
              p.type === 'orphan_rescue'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
            }`}>
              {p.type === 'orphan_rescue' ? 'Rescue' : 'Link'}
            </span>
            {p.source_label && <span className="text-xs text-gray-500">{p.source_label}</span>}
          </div>
          <p className="text-sm text-gray-300">{p.reason}</p>
        </div>
      </div>
    ))}
  </div>
);

const MoodPanel: React.FC<{ trends?: SubconsciousResult['mood_trends']; error?: string }> = ({ trends, error }) => {
  if (error) return <p className="text-red-400/70 text-sm">{error}</p>;
  if (!trends || trends.status === 'no_data') {
    return <p className="text-gray-500 text-sm">{trends?.message || 'No mood data available.'}</p>;
  }

  const dimensionLabels: Record<string, string> = {
    energy_f: 'Energy',
    warmth: 'Warmth',
    protectiveness: 'Protectiveness',
    chaos: 'Chaos',
    melancholy: 'Melancholy',
  };

  const trendColors: Record<string, string> = {
    rising: 'text-green-400',
    falling: 'text-red-400',
    stable: 'text-gray-400',
    insufficient_data: 'text-gray-600',
  };

  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-500 flex items-center gap-2">
        <Clock className="w-3 h-3" />
        {trends.period_days} day period • {trends.data_points} data points
      </div>

      <div className="space-y-3">
        {trends.averages && Object.entries(trends.averages).map(([dim, avg]) => {
          const trend = trends.trends?.[dim] || 'stable';
          const latest = trends.latest?.[dim];
          const pct = Math.min(100, Math.max(0, (avg as number) * 100));
          return (
            <div key={dim} className="bg-nexus-800/40 border border-white/5 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white">{dimensionLabels[dim] || dim}</span>
                <span className={`text-xs ${trendColors[trend]}`}>
                  {trend === 'rising' ? '↑ Rising' : trend === 'falling' ? '↓ Falling' : trend === 'stable' ? '→ Stable' : '? No data'}
                </span>
              </div>
              {/* Bar */}
              <div className="h-2 bg-nexus-900 rounded-full overflow-hidden mb-2">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-purple-500 to-nexus-accent transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-gray-500">
                <span>Avg: {(avg as number).toFixed(3)}</span>
                {latest !== undefined && <span>Now: {latest.toFixed(3)}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
