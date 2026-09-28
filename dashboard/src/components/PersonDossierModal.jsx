import React, { useMemo } from 'react';
import { 
  X, ShieldCheck, Clock, MapPin, Camera, AlertTriangle, 
  Trash2, ArrowRight, UserCheck, Activity
} from 'lucide-react';

export const PersonDossierModal = ({ person, sightings = [], onClose, onDelete }) => {
  if (!person) return null;

  // Filter sightings for this person
  const personSightings = useMemo(() => {
    return sightings
      .filter(s => s.name?.toLowerCase() === person.name?.toLowerCase())
      .sort((a, b) => b.timestamp - a.timestamp);
  }, [sightings, person.name]);

  // Unique cameras visited
  const camerasVisited = useMemo(() => {
    return [...new Set(personSightings.map(s => s.camera_name || s.camera))];
  }, [personSightings]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-[#0e141c] border border-cyan-500/40 rounded-2xl shadow-[0_0_50px_rgba(6,182,212,0.2)] overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-[#090d12] border-b border-slate-800">
          <div className="flex items-center gap-3">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-widest bg-cyan-950 text-cyan-400 border border-cyan-500/40 uppercase">
              BIOMETRIC DOSSIER
            </span>
            <span className="text-xs font-mono text-slate-400">
              ID #{person.id}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Identity Header Card */}
          <div className="flex items-start gap-5 p-4 rounded-xl bg-[#090d12] border border-slate-800">
            <div className="relative w-24 h-24 rounded-xl overflow-hidden border-2 border-cyan-400/80 flex-shrink-0 shadow-lg">
              <img
                src={person.thumbnail}
                alt={person.name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  e.target.src = 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150&auto=format&fit=crop&q=80';
                }}
              />
              <div className="absolute bottom-1 right-1">
                <span className="flex h-2.5 w-2.5 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                </span>
              </div>
            </div>

            <div className="flex-1 space-y-1">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-mono font-bold text-slate-100 uppercase tracking-wide">
                  {person.name}
                </h2>
                <span className="px-2.5 py-1 rounded-full text-xs font-mono font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5">
                  <ShieldCheck size={14} />
                  {person.status || 'Authorized'}
                </span>
              </div>

              <p className="text-xs font-mono text-cyan-400">
                {person.clearance || 'Level 2 (Personnel)'}
              </p>

              <div className="grid grid-cols-2 gap-4 pt-3 font-mono text-xs text-slate-400 border-t border-slate-800/80 mt-2">
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase">Last Detected</span>
                  <span className="text-slate-200">
                    {new Date(person.last_seen).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block uppercase">Match Confidence</span>
                  <span className="text-emerald-400 font-bold">
                    {((person.confidence || 0.92) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Cross-Camera Journey Breadcrumbs */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-mono text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Activity size={14} className="text-cyan-400" />
                Cross-Camera Tracking Breadcrumbs
              </h4>
              <span className="text-[11px] font-mono text-slate-500">
                {camerasVisited.length} Zones Traversed
              </span>
            </div>

            {camerasVisited.length > 0 ? (
              <div className="p-3.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center gap-2 overflow-x-auto">
                {camerasVisited.map((cam, idx) => (
                  <React.Fragment key={cam}>
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 text-xs font-mono text-slate-200 whitespace-nowrap">
                      <Camera size={13} className="text-cyan-400" />
                      <span>{cam}</span>
                    </div>
                    {idx < camerasVisited.length - 1 && (
                      <ArrowRight size={14} className="text-slate-600 flex-shrink-0" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-[#090d12] border border-slate-800 text-center font-mono text-xs text-slate-500">
                No multi-camera path recorded for this session.
              </div>
            )}
          </div>

          {/* Sighting Timeline */}
          <div>
            <h4 className="font-mono text-xs font-bold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Clock size={14} className="text-amber-400" />
              Recent Sighting Logs ({personSightings.length})
            </h4>

            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {personSightings.length > 0 ? (
                personSightings.map(sighting => (
                  <div
                    key={sighting.id}
                    className="p-3 rounded-lg bg-[#090d12] border border-slate-800 hover:border-slate-700 flex items-center justify-between text-xs font-mono transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-cyan-400" />
                      <div>
                        <div className="text-slate-200 font-semibold">
                          {sighting.camera_name || sighting.camera}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          BBox: [{sighting.bbox?.join(', ')}]
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-slate-300">
                        {new Date(sighting.timestamp > 1e12 ? sighting.timestamp : sighting.timestamp * 1000).toLocaleTimeString()}
                      </div>
                      <div className="text-[10px] text-emerald-400">
                        {((sighting.confidence || 0.9) * 100).toFixed(0)}% Match
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-4 rounded-xl bg-[#090d12] border border-slate-800 text-center font-mono text-xs text-slate-500">
                  No historical sightings logged today.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-4 bg-[#090d12] border-t border-slate-800">
          <button
            onClick={() => {
              if (window.confirm(`Permanently remove ${person.name} and delete their biometric embeddings?`)) {
                onDelete(person.id, person.name);
                onClose();
              }
            }}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 border border-rose-500/30 font-mono text-xs transition-colors"
          >
            <Trash2 size={14} /> Delete Profile
          </button>

          <button
            onClick={onClose}
            className="px-5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 font-mono text-xs text-slate-200 transition-colors"
          >
            Close Dossier
          </button>
        </div>
      </div>
    </div>
  );
};

export default PersonDossierModal;
