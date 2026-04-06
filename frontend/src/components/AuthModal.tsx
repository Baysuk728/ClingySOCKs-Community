import React, { useState } from 'react';
import { useAuth } from './AuthProvider';
import { LogIn, UserPlus, Mail, Lock, AlertCircle, Loader2 } from 'lucide-react';

interface AuthModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
    const { signIn, signUp } = useAuth();
    const [isSignUp, setIsSignUp] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (isSignUp && password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        if (password.length < 6) {
            setError('Password must be at least 6 characters');
            return;
        }

        setLoading(true);
        try {
            if (isSignUp) {
                await signUp(email, password);
            } else {
                await signIn(email, password);
            }
            onClose();
        } catch (err: any) {
            setError(err.message || 'Authentication failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-nexus-800 border border-white/10 rounded-2xl p-8 w-full max-w-md shadow-2xl">
                <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
                    {isSignUp ? (
                        <>
                            <UserPlus className="w-6 h-6 text-nexus-accent" />
                            Create Account
                        </>
                    ) : (
                        <>
                            <LogIn className="w-6 h-6 text-nexus-accent" />
                            Sign In
                        </>
                    )}
                </h2>
                <p className="text-gray-400 mb-6">
                    {isSignUp
                        ? 'Create an account to securely store your API keys'
                        : 'Sign in to access your secure API keys'}
                </p>

                {error && (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                        <p className="text-sm text-red-400">{error}</p>
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm text-gray-400 mb-2">Email</label>
                        <div className="relative">
                            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="you@example.com"
                                required
                                className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 pl-11 text-white focus:border-nexus-accent outline-none"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm text-gray-400 mb-2">Password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                required
                                className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 pl-11 text-white focus:border-nexus-accent outline-none"
                            />
                        </div>
                    </div>

                    {isSignUp && (
                        <div>
                            <label className="block text-sm text-gray-400 mb-2">Confirm Password</label>
                            <div className="relative">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                                <input
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    placeholder="••••••••"
                                    required
                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 pl-11 text-white focus:border-nexus-accent outline-none"
                                />
                            </div>
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-nexus-accent text-nexus-900 py-3 rounded-lg font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                        {loading ? (
                            <>
                                <Loader2 className="w-5 h-5 animate-spin" />
                                {isSignUp ? 'Creating Account...' : 'Signing In...'}
                            </>
                        ) : (
                            <>
                                {isSignUp ? 'Create Account' : 'Sign In'}
                            </>
                        )}
                    </button>
                </form>

                <div className="mt-6 text-center">
                    <button
                        onClick={() => {
                            setIsSignUp(!isSignUp);
                            setError('');
                        }}
                        className="text-gray-400 hover:text-white transition-colors text-sm"
                    >
                        {isSignUp
                            ? 'Already have an account? Sign in'
                            : "Don't have an account? Sign up"}
                    </button>
                </div>

                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
                >
                    ×
                </button>
            </div>
        </div>
    );
};
