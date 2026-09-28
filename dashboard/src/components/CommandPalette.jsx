import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Search, Camera, Shield, Database, Activity, 
  Settings, Volume2, VolumeX, UserPlus, FileText, 
  AlertTriangle, Radio, X 
} from 'lucide-react';
import soundManager from '../services/audioAlert';

export const CommandPalette = ({ isOpen, onClose, onOpenEnroll }) => {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onClose(prev => !prev);
      } else if (e.key === 'Escape' && isOpen) {
        onClose(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const actions = [
    { id: 'nav-cams', label: 'Go to Live Multi-Camera Grid', category: 'Navigation', icon: Camera, run: () => navigate('/dashboard') },
    { id: 'nav-persons', label: 'Open Enrolled Profiles Database', category: 'Navigation', icon: Database, run: () => navigate('/persons') },
    { id: 'nav-tracking', label: 'View Re-ID Tracking & Analytics', category: 'Navigation', icon: Activity, run: () => navigate('/tracking') },
    { id: 'nav-alerts', label: 'Review Active Security Incidents', category: 'Navigation', icon: AlertTriangle, run: () => navigate('/alerts') },
    { id: 'nav-map', label: 'Open 2D Tactical Operations Map', category: 'Navigation', icon: Radio, run: () => navigate('/map') },
    { id: 'nav-settings', label: 'Adjust Ghost Trail & AI Core Settings', category: 'Navigation', icon: Settings, run: () => navigate('/settings') },
    { id: 'action-enroll', label: 'Enroll New Biometric Profile (Webcam / Upload)', category: 'Quick Action', icon: UserPlus, run: () => { onClose(false); if (onOpenEnroll) onOpenEnroll(); } },
    { id: 'action-mute', label: soundManager.isMuted() ? 'Unmute Tactical Alarm Audio' : 'Mute Tactical Alarm Audio', category: 'System Audio', icon: soundManager.isMuted() ? Volume2 : VolumeX, run: () => soundManager.toggleMute() },
    { id: 'action-test-siren', label: 'Test Audio Siren Alert', category: 'System Audio', icon: AlertTriangle, run: () => soundManager.playCriticalAlert() },
  ];

  const filtered = actions.filter(a => 
    a.label.toLowerCase().includes(query.toLowerCase()) || 
    a.category.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="relative w-full max-w-xl bg-[#0e141c] border border-cyan-500/40 rounded-2xl shadow-[0_0_60px_rgba(6,182,212,0.2)] overflow-hidden">
        
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-slate-800 bg-[#090d12]">
          <Search size={18} className="text-cyan-400 flex-shrink-0" />
          <input
            type="text"
            autoFocus
            placeholder="Type a command or search (e.g. 'cams', 'enroll', 'settings', 'mute')..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-transparent border-none text-slate-100 placeholder:text-slate-500 font-mono text-sm outline-none"
          />
          <button
            onClick={() => onClose(false)}
            className="px-2 py-0.5 rounded text-[11px] font-mono text-slate-400 hover:text-white bg-slate-800"
          >
            ESC
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {filtered.length > 0 ? (
            filtered.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    item.run();
                    onClose(false);
                  }}
                  className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl hover:bg-cyan-950/40 hover:border-cyan-500/30 border border-transparent text-left group transition-all"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-slate-900 group-hover:bg-cyan-500/10 text-slate-400 group-hover:text-cyan-400 transition-colors">
                      <Icon size={16} />
                    </div>
                    <div>
                      <div className="text-sm font-mono text-slate-200 group-hover:text-cyan-200">
                        {item.label}
                      </div>
                      <div className="text-[10px] font-mono text-slate-500">
                        {item.category}
                      </div>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono text-slate-600 group-hover:text-cyan-400/80">
                    ENTER ↵
                  </span>
                </button>
              );
            })
          ) : (
            <div className="py-8 text-center font-mono text-xs text-slate-500">
              No matching commands or actions found.
            </div>
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="px-4 py-2 bg-[#090d12] border-t border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <span>Ghost Trail Security Command System</span>
          <span>Tip: Press <kbd className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">Ctrl+K</kbd> anywhere</span>
        </div>
      </div>
    </div>
  );
};

export default CommandPalette;
