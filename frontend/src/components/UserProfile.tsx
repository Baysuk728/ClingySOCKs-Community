import React, { useState, useEffect } from 'react';
import { User, Save, Loader2, AlertCircle, CheckCircle2, FileText, Brain, ScrollText, Lock, LockOpen } from 'lucide-react';
import { useAuth } from './AuthProvider';
import { UserDossier, saveUserDossier, getUserDossier, getLockedFields, updateLockedFields } from '../services/userProfileService';

type TabView = 'dossier' | 'memory_twin' | 'harvest_logs';

interface ProfileSection {
    title: string;
    description?: string;
    fields: ProfileField[];
}

interface ProfileField {
    key: string;
    label: string;
    type: 'text' | 'textarea' | 'number';
    placeholder?: string;
    isArray?: boolean; // Indicates field should be stored as array of strings
}

const PROFILE_SECTIONS: ProfileSection[] = [
    {
        title: 'Identity',
        description: 'Basic information about who you are',
        fields: [
            { key: 'name', label: 'Name', type: 'text', placeholder: 'Your full name' },
            { key: 'pronouns', label: 'Pronouns', type: 'text', placeholder: 'e.g., they/them, she/her' },
            { key: 'age_range', label: 'Age Range', type: 'text', placeholder: 'e.g., 30s, 18-25' },
            { key: 'location', label: 'Location', type: 'text', placeholder: 'City, Country' },
            { key: 'languages', label: 'Languages', type: 'text', placeholder: 'Comma-separated (e.g., English, Spanish, French)', isArray: true },
        ]
    },
    {
        title: 'Cognition & Brain',
        description: 'How your mind works',
        fields: [
            { key: 'neurotype', label: 'Neurotype', type: 'text', placeholder: 'e.g., ADHD, ASD, neurotypical' },
            { key: 'thinking_patterns', label: 'Thinking Patterns', type: 'text', placeholder: 'Comma-separated (e.g., hyperfocus, pattern-matching)', isArray: true },
            { key: 'cognitive_strengths', label: 'Cognitive Strengths', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'cognitive_challenges', label: 'Cognitive Challenges', type: 'text', placeholder: 'Comma-separated', isArray: true },
        ]
    },
    {
        title: 'Attachment & Emotional',
        description: 'Your emotional landscape and relationships',
        fields: [
            { key: 'attachment_style', label: 'Attachment Style', type: 'text', placeholder: 'e.g., secure, anxious, avoidant' },
            { key: 'attachment_notes', label: 'Attachment Notes', type: 'textarea', placeholder: 'Additional context about attachment' },
            { key: 'ifs_parts', label: 'IFS Parts', type: 'text', placeholder: 'Comma-separated (e.g., inner critic, protector)', isArray: true },
            { key: 'emotional_triggers', label: 'Emotional Triggers', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'coping_mechanisms', label: 'Coping Mechanisms', type: 'text', placeholder: 'Comma-separated', isArray: true },
        ]
    },
    {
        title: 'Relationship & Family',
        description: 'Your relationships and living situation',
        fields: [
            { key: 'relationship_status', label: 'Relationship Status', type: 'text', placeholder: 'e.g., partnered, single, polyamorous' },
            { key: 'family_situation', label: 'Family Situation', type: 'textarea', placeholder: 'Family dynamics and important relationships' },
            { key: 'living_situation', label: 'Living Situation', type: 'text', placeholder: 'Where and with whom you live' },
        ]
    },
    {
        title: 'Work & Life Stage',
        description: 'Your current life circumstances',
        fields: [
            { key: 'work_situation', label: 'Work Situation', type: 'textarea', placeholder: 'What you do, how it feels, career aspirations' },
            { key: 'financial_notes', label: 'Financial Notes', type: 'textarea', placeholder: 'Financial situation and concerns' },
        ]
    },
    {
        title: 'Interests & Goals',
        description: 'What you enjoy and what drives you',
        fields: [
            { key: 'hobbies', label: 'Hobbies', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'interests', label: 'Interests', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'life_goals', label: 'Life Goals', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'longings', label: 'Longings', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'current_projects', label: 'Current Projects', type: 'text', placeholder: 'Comma-separated', isArray: true },
        ]
    },
    {
        title: 'Communication & Boundaries',
        description: 'How you prefer to communicate and your boundaries',
        fields: [
            { key: 'preferred_communication_style', label: 'Communication Style', type: 'text', placeholder: 'e.g., direct, indirect, collaborative' },
            { key: 'humor_style', label: 'Humor Style', type: 'text', placeholder: 'e.g., sarcasm, dark, puns, wholesome' },
            { key: 'support_preferences', label: 'Support Preferences', type: 'textarea', placeholder: 'What kind of emotional support helps you most' },
            { key: 'boundary_preferences', label: 'Boundaries & Limits', type: 'textarea', placeholder: 'What boundaries are important to you' },
        ]
    },
    {
        title: 'Health & Wellness',
        description: 'Physical and mental health (optional)',
        fields: [
            { key: 'medical_conditions', label: 'Medical Conditions (Optional)', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'medications', label: 'Medications (Optional)', type: 'text', placeholder: 'Comma-separated', isArray: true },
            { key: 'health_notes', label: 'Health Notes', type: 'textarea', placeholder: 'Any health context you want shared' },
        ]
    },
];

export const UserProfile: React.FC = () => {
    const { user } = useAuth();
    const [currentTab, setCurrentTab] = useState<TabView>('dossier');
    const [dossier, setDossier] = useState<any>({});
    const [lockedFields, setLockedFields] = useState<Set<string>>(new Set());
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
    const [errorMessage, setErrorMessage] = useState('');

    // Load dossier on mount
    useEffect(() => {
        loadDossier();
    }, []);

    const loadDossier = async () => {
        setLoading(true);
        try {
            console.log('📋 Loading user profile...');
            const [data, locked] = await Promise.all([
                getUserDossier(),
                getLockedFields()
            ]);
            console.log('✅ Profile loaded:', data);
            console.log('✅ Locked fields:', locked);
            
            if (data) {
                setDossier(data);
            } else {
                console.warn('⚠️ No profile data returned');
            }
            if (locked) {
                setLockedFields(new Set(locked));
            }
        } catch (error) {
            console.error('❌ Failed to load dossier:', error);
            setErrorMessage(`Failed to load profile: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        setSaveStatus('idle');
        setErrorMessage('');

        try {
            console.log('💾 Saving profile...', dossier);
            console.log('🔒 Saving locked fields...', Array.from(lockedFields));
            
            await Promise.all([
                saveUserDossier(dossier),
                updateLockedFields(Array.from(lockedFields))
            ]);
            
            console.log('✅ Profile saved successfully');
            setSaveStatus('success');
            setTimeout(() => setSaveStatus('idle'), 3000);
        } catch (error) {
            console.error('❌ Failed to save profile:', error);
            setSaveStatus('error');
            setErrorMessage(`Failed to save profile: ${error instanceof Error ? error.message : String(error)}`);
        } finally {
            setSaving(false);
        }
    };

    const toggleFieldLock = (fieldKey: string) => {
        const newLocked = new Set(lockedFields);
        if (newLocked.has(fieldKey)) {
            newLocked.delete(fieldKey);
        } else {
            newLocked.add(fieldKey);
        }
        setLockedFields(newLocked);
    };

    const renderDossierContent = () => {
        if (loading) {
            return (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="w-8 h-8 text-nexus-accent animate-spin" />
                </div>
            );
        }

        return (
            <div className="space-y-8">
                {/* Info Box */}
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4">
                    <h4 className="text-blue-400 font-medium mb-2 flex items-center gap-2">
                        <FileText className="w-4 h-4" />
                        About Your Dossier
                    </h4>
                    <p className="text-sm text-blue-400/70">
                        Your dossier is injected into agent context to help them understand you better. You can lock fields to prevent the harvest system from overwriting them during memory extraction. Empty fields won't be sent to agents.
                    </p>
                </div>

                {/* Sections */}
                {PROFILE_SECTIONS.map((section) => (
                    <div key={section.title}>
                        <div className="mb-4">
                            <h3 className="text-lg font-bold text-white">{section.title}</h3>
                            {section.description && (
                                <p className="text-sm text-gray-400">{section.description}</p>
                            )}
                        </div>

                        <div className="space-y-4">
                            {section.fields.map((field) => (
                                <div key={field.key} className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <label className="block text-sm text-gray-300 font-medium">
                                            {field.label}
                                        </label>
                                        <button
                                            onClick={() => toggleFieldLock(field.key)}
                                            className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-all hover:bg-white/10"
                                            title={lockedFields.has(field.key) ? 'Locked - won\'t be updated by harvester' : 'Unlocked - can be updated by harvester'}
                                        >
                                            {lockedFields.has(field.key) ? (
                                                <>
                                                    <Lock className="w-4 h-4 text-yellow-500" />
                                                    <span className="text-yellow-500">Locked</span>
                                                </>
                                            ) : (
                                                <>
                                                    <LockOpen className="w-4 h-4 text-gray-500" />
                                                    <span className="text-gray-500">Unlocked</span>
                                                </>
                                            )}
                                        </button>
                                    </div>

                                    {field.type === 'textarea' ? (
                                        <textarea
                                            value={field.isArray ? (dossier[field.key] as string[])?.join(', ') || '' : dossier[field.key] || ''}
                                            onChange={e => {
                                                const value = e.target.value;
                                                if (field.isArray) {
                                                    const arrayValue = value.split(',').map(v => v.trim()).filter(v => v);
                                                    setDossier({ ...dossier, [field.key]: arrayValue });
                                                } else {
                                                    setDossier({ ...dossier, [field.key]: value });
                                                }
                                            }}
                                            placeholder={field.placeholder}
                                            rows={3}
                                            className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 text-white placeholder-gray-600 focus:border-nexus-accent outline-none resize-none"
                                        />
                                    ) : (
                                        <input
                                            type={field.type}
                                            value={field.isArray ? (dossier[field.key] as string[])?.join(', ') || '' : dossier[field.key] || ''}
                                            onChange={e => {
                                                const value = e.target.value;
                                                if (field.isArray) {
                                                    const arrayValue = value.split(',').map(v => v.trim()).filter(v => v);
                                                    setDossier({ ...dossier, [field.key]: arrayValue });
                                                } else {
                                                    setDossier({ ...dossier, [field.key]: value });
                                                }
                                            }}
                                            placeholder={field.placeholder}
                                            className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 text-white placeholder-gray-600 focus:border-nexus-accent outline-none"
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                ))}

                {/* Save Button */}
                <div className="flex items-center gap-4 pt-6 border-t border-white/10">
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 bg-nexus-accent text-nexus-900 px-6 py-3 rounded-xl font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {saving ? (
                            <>
                                <Loader2 className="w-5 h-5 animate-spin" />
                                Saving...
                            </>
                        ) : (
                            <>
                                <Save className="w-5 h-5" />
                                Save Changes
                            </>
                        )}
                    </button>

                    {/* Save Status */}
                    {saveStatus === 'success' && (
                        <div className="flex items-center gap-2 text-green-400">
                            <CheckCircle2 className="w-5 h-5" />
                            <span>Saved successfully!</span>
                        </div>
                    )}
                    {saveStatus === 'error' && (
                        <div className="flex items-center gap-2 text-red-400">
                            <AlertCircle className="w-5 h-5" />
                            <span>{errorMessage}</span>
                        </div>
                    )}
                </div>
            </div>
        );
    };

    const renderContent = () => {
        switch (currentTab) {
            case 'dossier':
                return renderDossierContent();

            /* Commented out for later use
            case 'memory_twin':
                return (
                    <div className="text-center py-16">
                        <Brain className="w-16 h-16 text-nexus-accent mx-auto mb-4 opacity-30" />
                        <h3 className="text-xl font-bold text-white mb-2">Memory Twin (Coming Soon)</h3>
                        <p className="text-gray-400 max-w-md mx-auto">
                            This will display your memory twin - an AI-generated summary of how agents perceive you based on conversations.
                        </p>
                    </div>
                );

            case 'harvest_logs':
                return (
                    <div className="text-center py-16">
                        <ScrollText className="w-16 h-16 text-nexus-accent mx-auto mb-4 opacity-30" />
                        <h3 className="text-xl font-bold text-white mb-2">Harvest Logs (Coming Soon)</h3>
                        <p className="text-gray-400 max-w-md mx-auto">
                            This will show a history of memory harvests and what was extracted from your conversations.
                        </p>
                    </div>
                );
            */
        }
    };

    return (
        <div className="h-full p-6 lg:p-10 overflow-y-auto">
            <div className="max-w-4xl mx-auto">
                {/* Header */}
                <div className="flex justify-between items-end mb-8">
                    <div>
                        <h2 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                            <User className="w-8 h-8 text-nexus-accent" />
                            User Profile
                        </h2>
                        <p className="text-gray-400">Manage your personal information and memory settings.</p>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-400">
                        <User className="w-4 h-4" />
                        <span>{user?.email}</span>
                    </div>
                </div>

                {/* Tab Navigation */}
                <div className="flex gap-2 mb-6 border-b border-white/10 overflow-x-auto">
                    <button
                        onClick={() => setCurrentTab('dossier')}
                        className={`px-6 py-3 font-medium transition-all border-b-2 whitespace-nowrap ${currentTab === 'dossier'
                                ? 'text-nexus-accent border-nexus-accent'
                                : 'text-gray-400 border-transparent hover:text-white'
                            }`}
                    >
                        <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4" />
                            User Dossier
                        </div>
                    </button>
                    {/* Commented out for later use
                    <button
                        onClick={() => setCurrentTab('memory_twin')}
                        className={`px-6 py-3 font-medium transition-all border-b-2 whitespace-nowrap ${currentTab === 'memory_twin'
                                ? 'text-nexus-accent border-nexus-accent'
                                : 'text-gray-400 border-transparent hover:text-white'
                            }`}
                    >
                        <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4" />
                            Memory Twin
                        </div>
                    </button>
                    <button
                        onClick={() => setCurrentTab('harvest_logs')}
                        className={`px-6 py-3 font-medium transition-all border-b-2 whitespace-nowrap ${currentTab === 'harvest_logs'
                                ? 'text-nexus-accent border-nexus-accent'
                                : 'text-gray-400 border-transparent hover:text-white'
                            }`}
                    >
                        <div className="flex items-center gap-2">
                            <ScrollText className="w-4 h-4" />
                            Harvest Logs
                        </div>
                    </button>
                    */}
                </div>

                {/* Tab Content */}
                <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
                    {renderContent()}
                </div>
            </div>
        </div>
    );
};
