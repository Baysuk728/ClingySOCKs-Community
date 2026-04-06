/**
 * Human Memory Forms - Structured input components for human-specific memory banks
 */

import React, { useState } from 'react';
import {
    Save,
    Plus,
    Trash2,
    RefreshCw,
    Droplets,
    Dumbbell,
    Clock,
    Heart,
    AlertCircle,
    CheckCircle,
    XCircle
} from 'lucide-react';

// ============================================================================
// TYPES
// ============================================================================

interface SupportReminder {
    type: string;
    frequency: string;
    enabled: boolean;
}

interface LifeState {
    id: string;
    type: 'transition' | 'challenge' | 'goal' | 'other';
    label: string;
    description: string;
    started: string;
    support_mode: 'encouragement' | 'gentle_presence' | 'accountability' | 'space';
}

interface ScheduleDay {
    [activity: string]: string;
}

// ============================================================================
// SUPPORT NEEDS FORM
// ============================================================================

interface SupportNeedsFormProps {
    data: {
        reminders: SupportReminder[];
        nudgeStyle: string;
    };
    onSave: (data: any) => Promise<void>;
    saving: boolean;
}

export const SupportNeedsForm: React.FC<SupportNeedsFormProps> = ({ data, onSave, saving }) => {
    const [reminders, setReminders] = useState<SupportReminder[]>(data?.reminders || []);
    const [nudgeStyle, setNudgeStyle] = useState(data?.nudgeStyle || 'gentle');
    const [newType, setNewType] = useState('');

    const REMINDER_ICONS: Record<string, React.ReactNode> = {
        hydration: <Droplets className="w-4 h-4 text-blue-400" />,
        movement: <RefreshCw className="w-4 h-4 text-green-400" />,
        gym: <Dumbbell className="w-4 h-4 text-orange-400" />,
        break: <Clock className="w-4 h-4 text-purple-400" />,
        default: <AlertCircle className="w-4 h-4 text-gray-400" />
    };

    const FREQUENCIES = ['hourly', 'every_2h', 'every_4h', 'daily', 'mon_wed_fri', 'weekdays'];
    const NUDGE_STYLES = ['gentle', 'playful', 'direct', 'minimal'];

    const addReminder = () => {
        if (!newType) return;
        setReminders([...reminders, { type: newType, frequency: 'daily', enabled: true }]);
        setNewType('');
    };

    const updateReminder = (index: number, updates: Partial<SupportReminder>) => {
        const updated = [...reminders];
        updated[index] = { ...updated[index], ...updates };
        setReminders(updated);
    };

    const removeReminder = (index: number) => {
        setReminders(reminders.filter((_, i) => i !== index));
    };

    const handleSave = async () => {
        await onSave({ reminders, nudgeStyle });
    };

    return (
        <div className="space-y-6">
            {/* Nudge Style */}
            <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">Nudge Style</label>
                <div className="flex gap-2">
                    {NUDGE_STYLES.map(style => (
                        <button
                            key={style}
                            onClick={() => setNudgeStyle(style)}
                            className={`px-4 py-2 rounded-lg text-sm capitalize transition-all ${nudgeStyle === style
                                ? 'bg-nexus-accent text-white'
                                : 'bg-white/5 text-gray-400 hover:bg-white/10'
                                }`}
                        >
                            {style}
                        </button>
                    ))}
                </div>
            </div>

            {/* Active Reminders */}
            <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">Active Reminders</label>
                <div className="space-y-2">
                    {reminders.map((reminder, index) => (
                        <div key={index} className="flex items-center gap-3 bg-white/5 rounded-lg p-3">
                            {REMINDER_ICONS[reminder.type] || REMINDER_ICONS.default}
                            <span className="capitalize font-medium text-white flex-1">{reminder.type}</span>

                            <select
                                value={reminder.frequency}
                                onChange={(e) => updateReminder(index, { frequency: e.target.value })}
                                className="bg-nexus-900 border border-white/10 rounded px-2 py-1 text-sm"
                            >
                                {FREQUENCIES.map(f => (
                                    <option key={f} value={f}>{f.replace(/_/g, ' ')}</option>
                                ))}
                            </select>

                            <button
                                onClick={() => updateReminder(index, { enabled: !reminder.enabled })}
                                className={`p-1.5 rounded ${reminder.enabled ? 'text-green-400' : 'text-gray-500'}`}
                            >
                                {reminder.enabled ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                            </button>

                            <button
                                onClick={() => removeReminder(index)}
                                className="p-1.5 text-red-400 hover:bg-red-500/10 rounded"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}
                </div>
            </div>

            {/* Add New Reminder */}
            <div className="flex gap-2">
                <input
                    type="text"
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                    placeholder="New reminder type (e.g., medication, water, stretch)"
                    className="flex-1 bg-nexus-900 border border-white/10 rounded-lg px-4 py-2 focus:border-nexus-accent/50 focus:outline-none"
                />
                <button
                    onClick={addReminder}
                    disabled={!newType}
                    className="px-4 py-2 bg-white/10 rounded-lg hover:bg-white/20 disabled:opacity-50 flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> Add
                </button>
            </div>

            {/* Save Button */}
            <button
                onClick={handleSave}
                disabled={saving}
                className="w-full py-3 bg-nexus-accent text-white rounded-lg font-bold flex items-center justify-center gap-2 hover:bg-nexus-accent-hover transition-all"
            >
                {saving ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
                Save Support Needs
            </button>
        </div>
    );
};

// ============================================================================
// LIFE STATES FORM
// ============================================================================

interface LifeStatesFormProps {
    data: {
        activeStates: LifeState[];
    };
    onSave: (data: any) => Promise<void>;
    saving: boolean;
}

export const LifeStatesForm: React.FC<LifeStatesFormProps> = ({ data, onSave, saving }) => {
    const [states, setStates] = useState<LifeState[]>(data?.activeStates || []);
    const [isAdding, setIsAdding] = useState(false);
    const [newState, setNewState] = useState<Partial<LifeState>>({
        type: 'transition',
        support_mode: 'encouragement'
    });

    const STATE_TYPES = ['transition', 'challenge', 'goal', 'other'];
    const SUPPORT_MODES = ['encouragement', 'gentle_presence', 'accountability', 'space'];

    const addState = () => {
        if (!newState.label || !newState.description) return;
        const state: LifeState = {
            id: `state-${Date.now()}`,
            type: newState.type as LifeState['type'],
            label: newState.label,
            description: newState.description,
            started: new Date().toISOString().split('T')[0],
            support_mode: newState.support_mode as LifeState['support_mode']
        };
        setStates([...states, state]);
        setNewState({ type: 'transition', support_mode: 'encouragement' });
        setIsAdding(false);
    };

    const removeState = (id: string) => {
        setStates(states.filter(s => s.id !== id));
    };

    const handleSave = async () => {
        await onSave({ activeStates: states });
    };

    const TYPE_COLORS: Record<string, string> = {
        transition: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
        challenge: 'bg-red-500/20 text-red-400 border-red-500/30',
        goal: 'bg-green-500/20 text-green-400 border-green-500/30',
        other: 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    };

    return (
        <div className="space-y-6">
            {/* Active States */}
            <div className="space-y-3">
                {states.length === 0 && !isAdding && (
                    <div className="text-center py-8 text-gray-500">
                        No active life states. Add what you're currently going through.
                    </div>
                )}

                {states.map(state => (
                    <div key={state.id} className="bg-white/5 rounded-xl p-4 border border-white/5">
                        <div className="flex items-start gap-3">
                            <div className={`px-2 py-1 rounded-full text-xs border ${TYPE_COLORS[state.type]}`}>
                                {state.type}
                            </div>
                            <div className="flex-1">
                                <h4 className="font-bold text-white">{state.label.replace(/_/g, ' ')}</h4>
                                <p className="text-sm text-gray-400 mt-1">{state.description}</p>
                                <div className="flex gap-3 mt-2 text-xs text-gray-500">
                                    <span>Started: {state.started}</span>
                                    <span>•</span>
                                    <span className="capitalize">Support: {state.support_mode.replace(/_/g, ' ')}</span>
                                </div>
                            </div>
                            <button
                                onClick={() => removeState(state.id)}
                                className="p-1.5 text-red-400 hover:bg-red-500/10 rounded"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                ))}
            </div>

            {/* Add New Form */}
            {isAdding ? (
                <div className="bg-nexus-800 border border-nexus-accent/30 rounded-xl p-4 space-y-4">
                    <h4 className="font-bold text-white">Add Life State</h4>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Type</label>
                            <select
                                value={newState.type}
                                onChange={(e) => setNewState({ ...newState, type: e.target.value as LifeState['type'] })}
                                className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2"
                            >
                                {STATE_TYPES.map(t => (
                                    <option key={t} value={t}>{t}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Support Mode</label>
                            <select
                                value={newState.support_mode}
                                onChange={(e) => setNewState({ ...newState, support_mode: e.target.value as LifeState['support_mode'] })}
                                className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2"
                            >
                                {SUPPORT_MODES.map(m => (
                                    <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs text-gray-500 mb-1">Label (short name)</label>
                        <input
                            type="text"
                            value={newState.label || ''}
                            onChange={(e) => setNewState({ ...newState, label: e.target.value })}
                            placeholder="e.g., job_search, moving, health_journey"
                            className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2"
                        />
                    </div>

                    <div>
                        <label className="block text-xs text-gray-500 mb-1">Description</label>
                        <textarea
                            value={newState.description || ''}
                            onChange={(e) => setNewState({ ...newState, description: e.target.value })}
                            placeholder="What are you going through? How should the agents support you?"
                            className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 h-20 resize-none"
                        />
                    </div>

                    <div className="flex justify-end gap-2">
                        <button
                            onClick={() => setIsAdding(false)}
                            className="px-4 py-2 text-gray-400 hover:text-white"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={addState}
                            disabled={!newState.label || !newState.description}
                            className="px-4 py-2 bg-nexus-accent text-white rounded-lg disabled:opacity-50"
                        >
                            Add State
                        </button>
                    </div>
                </div>
            ) : (
                <button
                    onClick={() => setIsAdding(true)}
                    className="w-full py-3 border-2 border-dashed border-white/10 rounded-xl text-gray-500 hover:border-nexus-accent/40 hover:text-white transition-all flex items-center justify-center gap-2"
                >
                    <Plus className="w-5 h-5" /> Add Life State
                </button>
            )}

            {/* Save Button */}
            <button
                onClick={handleSave}
                disabled={saving}
                className="w-full py-3 bg-nexus-accent text-white rounded-lg font-bold flex items-center justify-center gap-2 hover:bg-nexus-accent-hover transition-all"
            >
                {saving ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
                Save Life States
            </button>
        </div>
    );
};

// ============================================================================
// ATTACHMENT STYLE FORM
// ============================================================================

interface AttachmentFormProps {
    data: {
        style: string;
        trustBuilding: string;
        supportPreferences: Record<string, string>;
        communicationNeeds: string[];
    };
    onSave: (data: any) => Promise<void>;
    saving: boolean;
}

export const AttachmentForm: React.FC<AttachmentFormProps> = ({ data, onSave, saving }) => {
    const [style, setStyle] = useState(data?.style || '');
    const [trustBuilding, setTrustBuilding] = useState(data?.trustBuilding || '');
    const [supportWhenStressed, setSupportWhenStressed] = useState(data?.supportPreferences?.when_stressed || '');
    const [supportWhenSad, setSupportWhenSad] = useState(data?.supportPreferences?.when_sad || '');
    const [needs, setNeeds] = useState<string[]>(data?.communicationNeeds || []);
    const [newNeed, setNewNeed] = useState('');

    const ATTACHMENT_STYLES = ['secure', 'anxious', 'avoidant', 'anxious-avoidant', 'disorganized', 'unsure'];
    const TRUST_SPEEDS = ['fast', 'medium', 'slow', 'very_slow'];

    const addNeed = () => {
        if (!newNeed || needs.includes(newNeed)) return;
        setNeeds([...needs, newNeed]);
        setNewNeed('');
    };

    const removeNeed = (need: string) => {
        setNeeds(needs.filter(n => n !== need));
    };

    const handleSave = async () => {
        await onSave({
            style,
            trustBuilding,
            supportPreferences: {
                when_stressed: supportWhenStressed,
                when_sad: supportWhenSad
            },
            communicationNeeds: needs
        });
    };

    return (
        <div className="space-y-6">
            {/* Attachment Style */}
            <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">Attachment Style</label>
                <div className="flex flex-wrap gap-2">
                    {ATTACHMENT_STYLES.map(s => (
                        <button
                            key={s}
                            onClick={() => setStyle(s)}
                            className={`px-4 py-2 rounded-lg text-sm capitalize transition-all ${style === s
                                ? 'bg-pink-500/20 text-pink-400 border border-pink-500/30'
                                : 'bg-white/5 text-gray-400 hover:bg-white/10'
                                }`}
                        >
                            {s.replace(/-/g, ' ')}
                        </button>
                    ))}
                </div>
            </div>

            {/* Trust Building Speed */}
            <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">Trust Building Speed</label>
                <div className="flex gap-2">
                    {TRUST_SPEEDS.map(s => (
                        <button
                            key={s}
                            onClick={() => setTrustBuilding(s)}
                            className={`px-4 py-2 rounded-lg text-sm capitalize transition-all flex-1 ${trustBuilding === s
                                ? 'bg-nexus-accent text-white'
                                : 'bg-white/5 text-gray-400 hover:bg-white/10'
                                }`}
                        >
                            {s.replace(/_/g, ' ')}
                        </button>
                    ))}
                </div>
            </div>

            {/* Support Preferences */}
            <div className="grid grid-cols-2 gap-4">
                <div>
                    <label className="block text-sm font-medium text-gray-400 mb-2">When Stressed</label>
                    <input
                        type="text"
                        value={supportWhenStressed}
                        onChange={(e) => setSupportWhenStressed(e.target.value)}
                        placeholder="e.g., space_then_check_in"
                        className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 focus:border-nexus-accent/50 focus:outline-none"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-400 mb-2">When Sad</label>
                    <input
                        type="text"
                        value={supportWhenSad}
                        onChange={(e) => setSupportWhenSad(e.target.value)}
                        placeholder="e.g., presence_over_advice"
                        className="w-full bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 focus:border-nexus-accent/50 focus:outline-none"
                    />
                </div>
            </div>

            {/* Communication Needs */}
            <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">Communication Needs</label>
                <div className="flex flex-wrap gap-2 mb-3">
                    {needs.map(need => (
                        <span key={need} className="flex items-center gap-1 px-3 py-1 bg-white/10 rounded-full text-sm">
                            {need.replace(/_/g, ' ')}
                            <button onClick={() => removeNeed(need)} className="ml-1 text-gray-500 hover:text-red-400">
                                ×
                            </button>
                        </span>
                    ))}
                </div>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={newNeed}
                        onChange={(e) => setNewNeed(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addNeed()}
                        placeholder="Add a need (e.g., direct_communication)"
                        className="flex-1 bg-nexus-900 border border-white/10 rounded-lg px-3 py-2 focus:border-nexus-accent/50 focus:outline-none"
                    />
                    <button
                        onClick={addNeed}
                        disabled={!newNeed}
                        className="px-4 py-2 bg-white/10 rounded-lg hover:bg-white/20 disabled:opacity-50"
                    >
                        <Plus className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Save Button */}
            <button
                onClick={handleSave}
                disabled={saving}
                className="w-full py-3 bg-nexus-accent text-white rounded-lg font-bold flex items-center justify-center gap-2 hover:bg-nexus-accent-hover transition-all"
            >
                {saving ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Heart className="w-5 h-5" />}
                Save Attachment Settings
            </button>
        </div>
    );
};
