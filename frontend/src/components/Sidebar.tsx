import React, { useState, useEffect } from 'react';
import { MessageSquare, Users, Brain, Settings, Download, UserCircle2, Layers, GitBranch, Sparkles } from 'lucide-react';
import { ViewMode } from '../types';

interface SidebarProps {
  currentView: ViewMode;
  onViewChange: (view: ViewMode) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentView, onViewChange }) => {
  const navItems = [
    { id: 'chat' as ViewMode, icon: MessageSquare, label: 'Chats' },
    { id: 'personas' as ViewMode, icon: Users, label: 'Agents' },
    { id: 'memory' as ViewMode, icon: Brain, label: 'Memory' },
    { id: 'context' as ViewMode, icon: Layers, label: 'Context' },
    { id: 'graph' as ViewMode, icon: GitBranch, label: 'Graph' },
    { id: 'subconscious' as ViewMode, icon: Sparkles, label: 'Subconscious' },
    { id: 'profile' as ViewMode, icon: UserCircle2, label: 'Profile' },
    { id: 'settings' as ViewMode, icon: Settings, label: 'Settings' },
  ];

  return (
    <>
      {/* Desktop Sidebar - hidden on mobile */}
      <div className="hidden md:flex w-20 lg:w-64 h-full bg-nexus-800/50 backdrop-blur-xl border-r border-white/5 flex-col justify-between shrink-0">
        <div>
          <div className="h-20 flex items-center justify-center lg:justify-start lg:px-4 border-b border-white/5">
            <img src="/ClingySOCKs.png" alt="Logo" className="w-10 h-10 object-contain drop-shadow-[0_0_8px_rgba(0,242,255,0.4)]" />
            <span className="hidden lg:block ml-3 font-bold text-lg tracking-wider text-white">ClingySOCKs</span>
          </div>

          <nav className="mt-8 flex flex-col gap-2 px-3">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`flex items-center p-3 rounded-xl transition-all duration-300 group
                  ${currentView === item.id
                    ? 'bg-nexus-accent/10 text-nexus-accent shadow-[0_0_20px_rgba(0,242,255,0.15)]'
                    : 'text-gray-400 hover:bg-white/5 hover:text-white'
                  }`}
              >
                <item.icon className={`w-6 h-6 ${currentView === item.id ? 'animate-glow' : ''}`} />
                <span className="hidden lg:block ml-4 font-medium">{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="p-6 hidden lg:block">
          <div className="bg-nexus-900/80 rounded-xl p-4 border border-white/5">
            <div className="text-xs text-gray-500 uppercase tracking-widest mb-2">System Status</div>
            <div className="flex items-center gap-2 text-sm text-green-400">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
              Online
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Bottom Navigation */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 bg-nexus-800/95 backdrop-blur-xl border-t border-white/10 z-50 safe-area-inset-bottom">
        <nav className="flex justify-around items-center h-16 px-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`flex flex-col items-center justify-center py-2 px-3 rounded-xl transition-all
                ${currentView === item.id
                  ? 'text-nexus-accent'
                  : 'text-gray-500'
                }`}
            >
              <item.icon className="w-5 h-5" />
              <span className="text-[10px] mt-1 font-medium">{item.label}</span>
            </button>
          ))}
          {/* Install App Button */}
          <InstallButton />
        </nav>
      </div>
    </>
  );
};

// Install App Button Component
const InstallButton: React.FC = () => {
  const [installPrompt, setInstallPrompt] = useState<any>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setInstallPrompt(e);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleInstall = async () => {
    if (installPrompt) {
      installPrompt.prompt();
      await installPrompt.userChoice;
      setInstallPrompt(null);
    } else {
      alert('To install:\n\nAndroid: Tap browser menu (⋮) → "Add to Home screen"\n\niOS: Tap Share → "Add to Home Screen"');
    }
  };

  return (
    <button
      onClick={handleInstall}
      className="flex flex-col items-center justify-center py-2 px-3 rounded-xl transition-all text-green-400"
    >
      <Download className="w-5 h-5" />
      <span className="text-[10px] mt-1 font-medium">Install</span>
    </button>
  );
};

