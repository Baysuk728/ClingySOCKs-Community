import React, { useState } from 'react';
import { useAuth } from './AuthProvider';
import { LogIn, UserPlus, Mail, Lock, AlertCircle, Loader2, Sparkles, Shield, Brain, Key } from 'lucide-react';

export const LoginScreen: React.FC = () => {
    const { signIn, signUp } = useAuth();
    const [isSignUp, setIsSignUp] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (isSignUp && password !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }

        if (password.length < 8) {
            setError('Password must be at least 8 characters');
            return;
        }

        setLoading(true);
        try {
            if (isSignUp) {
                await signUp(email, password);
            } else {
                await signIn(email, password);
            }
        } catch (err: any) {
            setError(err.message || 'Authentication failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-nexus-900 flex items-center justify-center p-4">
            {/* Background effects */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-nexus-accent/5 rounded-full blur-3xl" />
                <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-nexus-cosy/5 rounded-full blur-3xl" />
            </div>

            <div className="relative w-full max-w-md">
                {/* Logo/Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-32 h-32 mb-4">
                        <img src="/ClingySOCKs.png" alt="ClingySOCKs Logo" className="w-full h-full object-contain drop-shadow-[0_0_15px_rgba(0,242,255,0.3)]" />
                    </div>
                    <h1 className="text-3xl font-bold text-white mb-2">ClingySOCKs</h1>
                    <p className="text-gray-400">Your Relational Memory Engine</p>
                </div>

                {/* Login Card */}
                <div className="bg-nexus-800/80 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-bold text-white flex items-center gap-3">
                            {isSignUp ? (
                                <>
                                    <UserPlus className="w-5 h-5 text-nexus-accent" />
                                    Create Account
                                </>
                            ) : (
                                <>
                                    <LogIn className="w-5 h-5 text-nexus-accent" />
                                    Welcome Back
                                </>
                            )}
                        </h2>
                        <button 
                            type="button"
                            onClick={() => {
                                setIsSignUp(!isSignUp);
                                setError('');
                            }}
                            className="text-xs text-nexus-accent hover:text-white transition-colors"
                        >
                            {isSignUp ? 'Sign In' : 'Need an account?'}
                        </button>
                    </div>

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
                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 pl-11 text-white focus:border-nexus-accent outline-none transition-colors"
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
                                    className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 pl-11 text-white focus:border-nexus-accent outline-none transition-colors"
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
                                        className="w-full bg-nexus-900 border border-white/10 rounded-lg p-3 pl-11 text-white focus:border-nexus-accent outline-none transition-colors"
                                    />
                                </div>
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-nexus-accent text-nexus-900 py-3 rounded-lg font-bold hover:shadow-[0_0_20px_rgba(0,242,255,0.4)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-6"
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    {isSignUp ? 'Creating Account...' : 'Signing In...'}
                                </>
                            ) : (
                                isSignUp ? 'Create Account' : 'Sign In'
                            )}
                        </button>
                    </form>

                    <div className="mt-6 text-center">
                        <button 
                            type="button"
                            onClick={() => setIsSignUp(!isSignUp)}
                            className="text-gray-400 text-sm hover:text-nexus-accent transition-colors underline underline-offset-4"
                        >
                            {isSignUp ? 'Already have an account? Sign In' : 'Don\'t have an account? Sign Up'}
                        </button>
                    </div>
                </div>

                {/* Features */}
                <div className="mt-8 grid grid-cols-3 gap-4 text-center">
                    <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                        <Shield className="w-6 h-6 text-green-400 mx-auto mb-2" />
                        <p className="text-xs text-gray-400">Secure API Key Storage</p>
                    </div>
                    <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                        <Sparkles className="w-6 h-6 text-nexus-accent mx-auto mb-2" />
                        <p className="text-xs text-gray-400">Multi-AI Agents</p>
                    </div>
                    <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                        <Key className="w-6 h-6 text-nexus-cosy mx-auto mb-2" />
                        <p className="text-xs text-gray-400">Your Own Keys</p>
                    </div>
                </div>
            </div>
        </div>
    );
};
