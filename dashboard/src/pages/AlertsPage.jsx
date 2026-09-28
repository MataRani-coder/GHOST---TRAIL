import React, { useState, useEffect } from 'react';
import { 
  AlertTriangle, ShieldCheck, Clock, Camera, Trash2, 
  ShieldAlert, UserPlus, Check, Volume2, VolumeX,
  Radio, RefreshCw, Eye, CheckCircle2, X 
} from 'lucide-react';
import apiService from '../services/api';
import wsService from '../services/websocket';
import soundManager from '../services/audioAlert';
import WebcamEnrollModal from '../components/WebcamEnrollModal';

export const AlertsPage = () => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterSeverity, setFilterSeverity] = useState('ALL');
  const [isMuted, setIsMuted] = useState(soundManager.isMuted());
  
  // Enroll modal for promoting guest from alert
  const [enrollModalGuest, setEnrollModalGuest] = useState(null);

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const data = await apiService.getAlerts();
      setAlerts(data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    const handleNewAlert = (alert) => {
      setAlerts(prev => [alert, ...prev]);
    };
    wsService.on('alert', handleNewAlert);
    return () => wsService.off('alert', handleNewAlert);
  }, []);

  const handleDismiss = async (alertId) => {
    await apiService.dismissAlert(alertId);
    setAlerts(prev => prev.map(a => 
      (String(a.id) === String(alertId) || String(a.timestamp) === String(alertId)) 
        ? { ...a, status: 'dismissed' } 
        : a
    ));
  };

  const handleClearAll = async () => {
    if (window.confirm('Clear all security incident records from log?')) {
      await apiService.clearAllAlerts();
      setAlerts([]);
    }
  };

  const toggleMute = () => {
    const nextMuted = soundManager.toggleMute();
    setIsMuted(nextMuted);
    if (!nextMuted) soundManager.playPing();
  };

  const isAcceptedAlert = (alert) =>
    alert.type === 'face_verification_accepted' ||
    alert.alert_type === 'face_verification_accepted' ||
    alert.risk_tier === 'verified';

  const filteredAlerts = alerts.filter(a => {
    if (filterSeverity === 'ALL') return true;
    if (filterSeverity === 'ACTIVE') return (a.status !== 'dismissed' && a.status !== 'resolved') && !isAcceptedAlert(a);
    if (filterSeverity === 'DISMISSED') return a.status === 'dismissed' || a.status === 'resolved';
    if (filterSeverity === 'HIGH_RISK') return a.risk_tier === 'high_risk';
    return (a.severity || 'critical').toUpperCase() === filterSeverity;
  });

  const activeCount = alerts.filter(a => a.status === 'active').length;

  return (
    <div className="space-y-6">
      
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-widest bg-rose-950 text-rose-400 border border-rose-500/40 uppercase">
              SECURITY OPERATIONS CENTER
            </span>
            <span className="text-xs font-mono text-slate-500">
              {activeCount} Active Incidents
            </span>
          </div>
          <h2 className="text-2xl font-mono font-bold tracking-tight text-slate-100 uppercase">
            Security Incident Logs & Alerts
          </h2>
          <p className="text-xs font-mono text-slate-400">
            Real-time perimeter alarms, unknown target detections, and threat object triggers
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={toggleMute}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-mono transition-all ${
              isMuted 
                ? 'bg-slate-900 border-slate-800 text-slate-500' 
                : 'bg-rose-950/40 border-rose-500/40 text-rose-300 shadow-[0_0_15px_rgba(239,68,68,0.2)]'
            }`}
          >
            {isMuted ? <VolumeX size={15} /> : <Volume2 size={15} />}
            <span>{isMuted ? 'Alarms Muted' : 'Sirens Armed'}</span>
          </button>

          <button
            onClick={() => soundManager.playCriticalAlert()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-rose-500/60 text-xs font-mono text-slate-300 hover:text-white transition-all"
          >
            <Radio size={14} className="text-rose-400" />
            <span>Test Siren</span>
          </button>

          {alerts.length > 0 && (
            <button
              onClick={handleClearAll}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-slate-600 text-xs font-mono text-slate-400 hover:text-slate-200 transition-all"
            >
              <Trash2 size={14} />
              <span>Clear Log</span>
            </button>
          )}
        </div>
      </div>

      {/* ── FILTER TOOLBAR ──────────────────────────────────────────────────── */}
      <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl flex items-center justify-between">
        <div className="flex items-center gap-2">
          {['ALL', 'ACTIVE', 'HIGH_RISK', 'DISMISSED'].map((filter) => (
            <button
              key={filter}
              onClick={() => setFilterSeverity(filter)}
              className={`px-3.5 py-1.5 rounded-xl font-mono text-xs font-semibold transition-all ${
                filterSeverity === filter
                  ? 'bg-cyan-500 text-black shadow-md'
                  : 'text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800'
              }`}
            >
              {filter === 'HIGH_RISK' ? 'HIGH RISK' : filter}
            </button>
          ))}
        </div>

        <button
          onClick={fetchAlerts}
          className="flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-white"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          <span>Sync Feed</span>
        </button>
      </div>

      {/* ── ALERTS FEED ─────────────────────────────────────────────────────── */}
      <div className="space-y-4">
        {filteredAlerts.length > 0 ? (
          filteredAlerts.map((alert) => {
            const isDismissed = alert.status === 'dismissed' || alert.status === 'resolved';
            const isAccepted = isAcceptedAlert(alert);
            const alertId = alert.id || alert.timestamp;

            return (
              <div
                key={alertId}
                className={`p-5 rounded-2xl border transition-all shadow-xl font-mono ${
                  isDismissed
                    ? 'bg-[#090d12]/60 border-slate-800/80 opacity-60'
                    : isAccepted
                      ? 'bg-[#0e141c] border-emerald-500/40 shadow-[0_0_25px_rgba(16,185,129,0.12)]'
                      : 'bg-[#0e141c] border-rose-500/40 shadow-[0_0_25px_rgba(239,68,68,0.12)]'
                }`}
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="flex items-start gap-4">
                    <div className={`p-3 rounded-xl border flex-shrink-0 mt-0.5 ${
                      isDismissed
                        ? 'bg-slate-900 border-slate-800 text-slate-500'
                        : isAccepted
                          ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-400 shadow-md'
                          : 'bg-rose-950/60 border-rose-500/50 text-rose-400 shadow-md animate-pulse'
                    }`}>
                      {isAccepted ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          isDismissed
                            ? 'bg-slate-800 text-slate-400 border border-slate-700'
                            : isAccepted
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/50'
                              : 'bg-rose-950 text-rose-300 border border-rose-500/50'
                        }`}>
                          {alert.alert_type || alert.type || 'SECURITY INTRUSION'}
                        </span>

                        <span className="px-2 py-0.5 rounded text-[10px] bg-slate-900 text-cyan-400 border border-slate-800 uppercase">
                          CHANNEL: {alert.camera_id?.toUpperCase() || 'CAM_2'}
                        </span>

                        {alert.risk_tier && (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                            alert.risk_tier === 'high_risk'
                              ? 'bg-red-950 text-red-300 border-red-500/50'
                              : alert.risk_tier === 'verified'
                                ? 'bg-emerald-950 text-emerald-300 border-emerald-500/50'
                                : 'bg-amber-950 text-amber-300 border-amber-500/50'
                          }`}>
                            {alert.risk_tier === 'high_risk' ? 'High Risk' : alert.risk_tier === 'verified' ? 'Accepted' : 'Suspicious'}
                          </span>
                        )}

                        <span className="text-[11px] text-slate-500 flex items-center gap-1">
                          <Clock size={12} />
                          {new Date((alert.timestamp > 1e12 ? alert.timestamp : alert.timestamp * 1000) || Date.now()).toLocaleTimeString()}
                        </span>
                      </div>

                      <h3 className="text-sm font-bold text-slate-100">
                        {alert.message || 'Unknown Person Detected in Monitored Sector'}
                      </h3>

                      {alert.person_name && (
                        <div className="text-[11px] text-red-300 font-semibold">
                          PERSON: {alert.person_name} {alert.person_id ? `(ID #${alert.person_id})` : ''}
                        </div>
                      )}

                      {alert.detail && (
                        <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
                          {alert.detail}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-800 justify-end">
                    {/* Enroll target option */}
                    {!isAccepted && (
                      <button
                        onClick={() => setEnrollModalGuest({
                          name: alert.detail?.match(/Guest \d+/)?.[0] || 'Unknown Guest'
                        })}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-900 text-xs transition-colors shadow-sm"
                      >
                        <UserPlus size={13} />
                        <span>Enroll Face</span>
                      </button>
                    )}

                    {/* Accepted faces are audit events, not alarms. */}
                    {isAccepted ? (
                      <span className="text-[11px] text-emerald-300 font-semibold px-2 py-1">
                        VERIFIED AUDIT EVENT
                      </span>
                    ) : !isDismissed ? (
                      <button
                        onClick={() => handleDismiss(alertId)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition-colors"
                      >
                        <Check size={13} />
                        <span>Acknowledge</span>
                      </button>
                    ) : (
                      <span className="text-[11px] text-slate-500 font-semibold px-2 py-1">
                        RESOLVED
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="py-20 text-center rounded-2xl bg-[#0e141c] border border-slate-800 font-mono space-y-3">
            <ShieldCheck size={40} className="mx-auto text-emerald-400" />
            <h3 className="text-base text-slate-200 font-bold uppercase">
              No Security Incidents Active
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              All sectors are currently secure. Threat logs will stream here instantly upon AI perimeter detection.
            </p>
          </div>
        )}
      </div>

      {/* Guest Enrollment Modal */}
      {enrollModalGuest && (
        <WebcamEnrollModal
          prefillName={enrollModalGuest.name}
          onClose={() => setEnrollModalGuest(null)}
          onSuccess={() => {
            setEnrollModalGuest(null);
            fetchAlerts();
          }}
        />
      )}
    </div>
  );
};

export default AlertsPage;
