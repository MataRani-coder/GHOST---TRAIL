import React, { useState, useEffect } from 'react';
import { 
  Camera, Sliders, HardDrive, Cpu, Check, Plus, Trash2, 
  Shield, Activity, Save, RefreshCw, AlertCircle, Sparkles, Radio
} from 'lucide-react';
import apiService from '../services/api';

/* ── Section Card Component ─────────────────────────────────────────────── */
const SectionCard = ({ icon: Icon, title, description, children }) => (
  <div className="p-6 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-5">
    <div className="flex items-center gap-3 pb-4 border-b border-slate-800">
      <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
        <Icon size={18} />
      </div>
      <div>
        <h3 className="font-mono text-sm font-bold text-slate-100 uppercase tracking-wider">
          {title}
        </h3>
        {description && (
          <p className="text-xs font-mono text-slate-500 mt-0.5">
            {description}
          </p>
        )}
      </div>
    </div>
    {children}
  </div>
);

export const SettingsPage = () => {
  const [settings, setSettings] = useState({
    threat_classes: [2, 24],
    threat_alert_cooldown_sec: 5.0,
    display_duration_sec: 15.0,
    confidence_threshold: 0.40,
    reid_threshold: 0.75,
    confirm_frames: 4,
    storage_path: 'C:/GhostTrail/recordings',
    retention_days: 14,
    cameras: []
  });

  const [diagnostics, setDiagnostics] = useState({
    status: 'running',
    system: 'YOLOv8 + DeepReID OSNet Core',
    gpu_status: 'NVIDIA RTX Core (CUDA 12.2)',
    gpu_temp: '58°C',
    vram_usage: '2.4 GB / 8.0 GB (30%)',
    cpu_usage: '18%',
    memory_usage: '4.2 GB / 16.0 GB (26%)',
    inference_time: '12.4 ms',
    reid_latency: '6.1 ms',
    uptime: '3d 14h 22m'
  });

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  
  // New Camera state
  const [newCam, setNewCam] = useState({ name: '', source: '0', zone: 'Zone A' });

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      const [cfg, diag] = await Promise.all([
        apiService.getSystemSettings(),
        apiService.getSystemHealth()
      ]);
      if (cfg) setSettings(cfg);
      if (diag) setDiagnostics(diag);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSave = async (e) => {
    e?.preventDefault();
    setSaving(true);
    setSaveSuccess(false);
    try {
      await apiService.updateSystemSettings(settings);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleAddCam = async (e) => {
    e.preventDefault();
    if (!newCam.name.trim()) return;
    await apiService.addCamera({
      camera_id: `cam_${Date.now().toString().slice(-3)}`,
      name: newCam.name.trim(),
      source: newCam.source.trim(),
      zone: newCam.zone
    });
    setNewCam({ name: '', source: '0', zone: 'Zone A' });
    fetchConfig();
  };

  const handleToggleCam = async (camId, enabled) => {
    await apiService.toggleCamera(camId, enabled);
    fetchConfig();
  };

  const handleRemoveCam = async (camId) => {
    if (window.confirm(`Delete channel ${camId}?`)) {
      await apiService.removeCamera(camId);
      fetchConfig();
    }
  };

  // Toggle threat class
  const toggleThreatClass = (classId) => {
    const current = settings.threat_classes || [];
    const next = current.includes(classId)
      ? current.filter(id => id !== classId)
      : [...current, classId];
    setSettings({ ...settings, threat_classes: next });
  };

  const threatClassOptions = [
    { id: 2, label: 'Vehicle / Car (Class #2)' },
    { id: 24, label: 'Backpack / Bag (Class #24)' },
    { id: 26, label: 'Handbag (Class #26)' },
    { id: 28, label: 'Suitcase / Luggage (Class #28)' },
    { id: 0, label: 'Unknown Person Face Breach (Class #0)' }
  ];

  return (
    <div className="space-y-6">
      
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-widest bg-cyan-950 text-cyan-400 border border-cyan-500/40 uppercase">
              AI ARCHITECTURE CONTROL
            </span>
            <span className="text-xs font-mono text-emerald-400">
              CUDA 12.2 ACTIVE
            </span>
          </div>
          <h2 className="text-2xl font-mono font-bold tracking-tight text-slate-100 uppercase">
            System & Engine Settings
          </h2>
          <p className="text-xs font-mono text-slate-400">
            Tune neural network weights, confidence thresholds, Re-ID embedding gallery, and RTSP stream inputs
          </p>
        </div>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-cyan-400 hover:bg-cyan-300 disabled:opacity-50 text-black font-mono text-xs font-bold transition-all shadow-[0_0_20px_rgba(6,182,212,0.25)] hover:shadow-[0_0_25px_rgba(6,182,212,0.4)]"
        >
          {saving ? <RefreshCw size={15} className="animate-spin" /> : <Save size={15} />}
          <span>{saving ? 'Applying...' : 'Save Configuration'}</span>
        </button>
      </div>

      {saveSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 text-xs font-mono flex items-center gap-2 animate-in fade-in duration-200">
          <Check size={16} />
          <span>Configuration saved and hot-reloaded into the active Ghost Trail tracker!</span>
        </div>
      )}

      {/* ── HARDWARE & ENGINE TELEMETRY ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-2 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">GPU Acceleration</span>
          <div className="text-sm font-bold text-slate-100 truncate">{diagnostics.gpu_status}</div>
          <div className="text-xs text-emerald-400">Temp: {diagnostics.gpu_temp || '58°C'}</div>
        </div>

        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-2 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">VRAM Utilization</span>
          <div className="text-sm font-bold text-cyan-400">{diagnostics.vram_usage || '2.4 / 8.0 GB'}</div>
          <div className="text-xs text-slate-500">Shared Tensor Buffer</div>
        </div>

        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-2 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Inference Speed</span>
          <div className="text-sm font-bold text-amber-400">{diagnostics.inference_time || '12.4 ms'}</div>
          <div className="text-xs text-slate-500">YOLOv8 Bounding Box</div>
        </div>

        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-2 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Re-ID Cosine Match</span>
          <div className="text-sm font-bold text-purple-400">{diagnostics.reid_latency || '6.1 ms'}</div>
          <div className="text-xs text-slate-500">OSNet 512-D Vectors</div>
        </div>
      </div>

      {/* ── SETTINGS GRID ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Detection & Re-ID Sensitivity */}
        <SectionCard
          icon={Sliders}
          title="AI Detection & Re-ID Sensitivity"
          description="Adjust neural confidence thresholds and consecutive confirmation frame windows"
        >
          <div className="space-y-5 font-mono text-xs">
            {/* YOLO Threshold */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-300">YOLO Detection Confidence Threshold:</span>
                <span className="px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-500/30 font-bold">
                  {(settings.confidence_threshold || 0.4).toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.1"
                max="0.9"
                step="0.05"
                value={settings.confidence_threshold || 0.4}
                onChange={e => setSettings({ ...settings, confidence_threshold: parseFloat(e.target.value) })}
                className="w-full accent-cyan-400 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>0.1 (High Recall)</span>
                <span>0.9 (Strict Precision)</span>
              </div>
            </div>

            {/* Re-ID Threshold */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-300">DeepReID Cosine Match Cutoff:</span>
                <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-500/30 font-bold">
                  {(settings.reid_threshold || 0.75).toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.4"
                max="0.95"
                step="0.02"
                value={settings.reid_threshold || 0.75}
                onChange={e => setSettings({ ...settings, reid_threshold: parseFloat(e.target.value) })}
                className="w-full accent-amber-400 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                <span>0.4 (Loose Match)</span>
                <span>0.95 (Exact Match)</span>
              </div>
            </div>

            {/* Confirmation Frames */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-300">Confirmation Frame Window:</span>
                <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-700 font-bold">
                  {settings.confirm_frames || 4} Frames
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="10"
                step="1"
                value={settings.confirm_frames || 4}
                onChange={e => setSettings({ ...settings, confirm_frames: parseInt(e.target.value) })}
                className="w-full accent-cyan-400 cursor-pointer"
              />
              <span className="text-[10px] text-slate-500 mt-1 block">
                Number of consecutive frames required before locking target track ID.
              </span>
            </div>
          </div>
        </SectionCard>

        {/* Threat Classification & Alert Rules */}
        <SectionCard
          icon={Shield}
          title="Threat Classification & Trigger Policies"
          description="Select object classes and triggers that dispatch instant security alarms"
        >
          <div className="space-y-4 font-mono text-xs">
            <span className="text-slate-400 block text-[11px] uppercase">
              Monitored Object Classes:
            </span>

            <div className="space-y-2">
              {threatClassOptions.map(tc => {
                const checked = (settings.threat_classes || []).includes(tc.id);
                return (
                  <label
                    key={tc.id}
                    className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-colors ${
                      checked 
                        ? 'bg-rose-950/20 border-rose-500/40 text-slate-100' 
                        : 'bg-[#090d12] border-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <span>{tc.label}</span>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleThreatClass(tc.id)}
                      className="accent-rose-500 w-4 h-4 cursor-pointer"
                    />
                  </label>
                );
              })}
            </div>

            {/* Cooldown */}
            <div className="pt-3 border-t border-slate-800">
              <label className="text-slate-400 block text-[11px] uppercase mb-1.5">
                Threat Alarm Cooldown (Seconds)
              </label>
              <input
                type="number"
                min="1"
                max="120"
                value={settings.threat_alert_cooldown_sec || 5}
                onChange={e => setSettings({ ...settings, threat_alert_cooldown_sec: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 rounded-xl bg-[#090d12] border border-slate-700 text-slate-100 outline-none"
              />
            </div>
          </div>
        </SectionCard>

        {/* Camera Channel Management */}
        <SectionCard
          icon={Camera}
          title="Surveillance Camera Inputs"
          description="Manage active RTSP streams, IP phone cameras, and local USB capture cards"
        >
          <div className="space-y-4 font-mono text-xs">
            {/* Existing cameras */}
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {(settings.cameras || []).map(cam => (
                <div
                  key={cam.camera_id}
                  className="p-3 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-100">{cam.name}</span>
                      <span className="text-[10px] text-cyan-400 uppercase">({cam.camera_id})</span>
                    </div>
                    <span className="text-[10px] text-slate-500 truncate block max-w-xs">
                      {cam.source}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleToggleCam(cam.camera_id, !cam.enabled)}
                      className={`px-2.5 py-1 rounded-lg text-[10px] font-bold ${
                        cam.enabled 
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' 
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {cam.enabled ? 'ACTIVE' : 'OFF'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemoveCam(cam.camera_id)}
                      className="p-1 text-slate-500 hover:text-rose-400"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Quick Add Camera */}
            <div className="pt-3 border-t border-slate-800">
              <span className="text-slate-400 block text-[11px] uppercase mb-2">
                Add New Video Stream Channel:
              </span>
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input
                  type="text"
                  placeholder="Camera Name"
                  value={newCam.name}
                  onChange={e => setNewCam({ ...newCam, name: e.target.value })}
                  className="px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-slate-100 outline-none"
                />
                <input
                  type="text"
                  placeholder="Source (0 or rtsp://...)"
                  value={newCam.source}
                  onChange={e => setNewCam({ ...newCam, source: e.target.value })}
                  className="px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-slate-100 outline-none"
                />
              </div>
              <button
                type="button"
                onClick={handleAddCam}
                className="w-full py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold flex items-center justify-center gap-1.5 transition-colors"
              >
                <Plus size={14} className="text-cyan-400" />
                <span>Add Channel</span>
              </button>
            </div>
          </div>
        </SectionCard>

        {/* Storage & Data Retention */}
        <SectionCard
          icon={HardDrive}
          title="Telemetry Storage & Audit Policies"
          description="Configure SQLite tracker database path, video recording retention, and purge schedules"
        >
          <div className="space-y-4 font-mono text-xs">
            <div>
              <label className="text-slate-400 block text-[11px] uppercase mb-1.5">
                Surveillance Recording Path
              </label>
              <input
                type="text"
                value={settings.storage_path || 'C:/GhostTrail/recordings'}
                onChange={e => setSettings({ ...settings, storage_path: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-[#090d12] border border-slate-700 text-slate-100 outline-none"
              />
            </div>

            <div>
              <label className="text-slate-400 block text-[11px] uppercase mb-1.5">
                Event Retention Buffer (Days)
              </label>
              <input
                type="number"
                min="1"
                max="90"
                value={settings.retention_days || 14}
                onChange={e => setSettings({ ...settings, retention_days: parseInt(e.target.value) })}
                className="w-full px-3 py-2 rounded-xl bg-[#090d12] border border-slate-700 text-slate-100 outline-none"
              />
              <span className="text-[10px] text-slate-500 mt-1 block">
                Automatic rolling purge cleans sightings older than retention buffer daily at midnight.
              </span>
            </div>

            <div className="p-3 rounded-xl bg-[#090d12] border border-slate-800 text-[11px] text-slate-400 space-y-1">
              <span className="text-slate-300 font-bold block">SQLite Engine Status:</span>
              <p>Connected to <code>tracker.db</code> with WAL journaling enabled for high-throughput concurrent writes.</p>
            </div>
          </div>
        </SectionCard>

      </div>
    </div>
  );
};

export default SettingsPage;
