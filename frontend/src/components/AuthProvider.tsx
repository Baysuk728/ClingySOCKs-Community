import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, onAuthChange, signIn, signUp, logOut } from '../auth';

interface AuthContextType {
    user: User | null;
    loading: boolean;
    signIn: (email: string, password: string) => Promise<void>;
    signUp: (email: string, password: string) => Promise<void>;
    logOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

interface AuthProviderProps {
    children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const unsubscribe = onAuthChange((user) => {
            setUser(user);
            setLoading(false);
        });

        return () => unsubscribe();
    }, []);

    const handleSignIn = async (email: string, password: string) => {
        await signIn(email, password);
    };

    const handleSignUp = async (email: string, password: string) => {
        await signUp(email, password);
    };

    const handleLogOut = async () => {
        await logOut();
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                loading,
                signIn: handleSignIn,
                signUp: handleSignUp,
                logOut: handleLogOut,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};
