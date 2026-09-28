import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import CameraFeed from '../components/CameraFeed';
import WebcamEnrollModal from '../components/WebcamEnrollModal';
import apiService from '../services/api';
import wsService from '../services/websocket';
import {
  Camera, Activity, AlertTriangle, Cpu, Radio, 
  Grid, LayoutGrid, Maximize, Plus, Shield, CheckCircle,
  Eye, RefreshCw, X, Sliders, Crosshair, BarChart3, Settings2, Rotate3D
} from 'lucide-react';

/* ─── Metric Card ───────────────────────────────────────────────────────────── */
const MetricCard = ({ label, value, sub, icon: Icon, accent, badge }) => (
  <div className="dashboard-metric relative p-4 flex flex-col justify-between overflow-hidden group">
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-medium tracking-wide text-zinc-500">
        {label}
      </span>
      <div className={`p-2 rounded-xl border ${accent}`}>
        <Icon size={16} />
      </div>
    </div>

    <div className="mt-3 flex items-end justify-between">
      <div>
        <div className="text-2xl font-semibold text-zinc-100 tracking-tight">
          {value}
        </div>
        <div className="text-[11px] text-zinc-500 mt-1">
          {sub}
        </div>
      </div>
      {badge && (
        <span className="px-2 py-0.5 rounded-md font-mono text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
          {badge}
        </span>
      )}
    </div>
  </div>
);

export const DashboardPage = () => {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState([]);
  const [summary, setSummary] = useState({
    activeCameras: 3,
    totalDetections: 48,
    activeAlerts: 1,
    systemHealth: 99.4,
    fps: 29.4
  });
  const [layoutMode, setLayoutMode] = useState('grid2x2'); // 'grid2x2', 'focus', 'director'
  const [focusedCameraId, setFocusedCameraId] = useState(null);
  const [liveTicker, setLiveTicker] = useState([]);
  const [enrollModalSnapshot, setEnrollModalSnapshot] = useState(null);
  const [showAddCamModal, setShowAddCamModal] = useState(false);
  const [newCamData, setNewCamData] = useState({ name: '', source: '0', zone: 'Zone A' });
  const [heroRotation, setHeroRotation] = useState(0);
  const [heroAutoRotate, setHeroAutoRotate] = useState(true);
  const [heroDragging, setHeroDragging] = useState(false);
  const heroDragRef = useRef({ x: 0, rotation: 0 });

  // Cinematic orbital hero motion. Rotation is visual-only; surveillance logic stays untouched.
  useEffect(() => {
    if (!heroAutoRotate || heroDragging) return;
    const id = setInterval(() => setHeroRotation(prev => (prev + 0.45) % 360), 42);
    return () => clearInterval(id);
  }, [heroAutoRotate, heroDragging]);

  const beginHeroDrag = (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    heroDragRef.current = { x: e.clientX, rotation: heroRotation };
    setHeroDragging(true);
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };

  const moveHeroDrag = (e) => {
    if (!heroDragging) return;
    const dx = e.clientX - heroDragRef.current.x;
    setHeroRotation((heroDragRef.current.rotation + dx * 0.55 + 3600) % 360);
  };

  const endHeroDrag = (e) => {
    if (!heroDragging) return;
    setHeroDragging(false);
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };

  const heroRad = heroRotation * Math.PI / 180;
  const heroYaw = Math.sin(heroRad) * 18;
  const heroPitch = Math.cos(heroRad * 0.72) * 2.6;
  const heroShift = Math.sin(heroRad * 0.92) * 42;
  const heroDepth = (Math.cos(heroRad) + 1) * 0.5;

  // Fetch initial cameras & summary
  const loadData = async () => {
    try {
      const [cams, sum] = await Promise.all([
        apiService.getCameras(),
        apiService.getDetectionsSummary()
      ]);
      setCameras(cams || []);
      if (sum) setSummary(sum);
      if (cams && cams.length > 0 && !focusedCameraId) {
        setFocusedCameraId(cams[0].camera_id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
    const id = setInterval(loadData, 15000);
    return () => clearInterval(id);
  }, []);

  // Listen to live WebSocket detections
  useEffect(() => {
    const handleDetection = (det) => {
      setLiveTicker(prev => [
        {
          id: `${Date.now()}-${Math.random()}`,
          camera_id: det.camera_id,
          name: det.name,
          confidence: det.confidence,
          is_known: det.is_known,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        },
        ...prev.slice(0, 7)
      ]);
    };

    const handleTelemetry = (t) => {
      if (t.fps) setSummary(prev => ({ ...prev, fps: t.fps }));
      if (t.active_cameras !== undefined) setSummary(prev => ({ ...prev, activeCameras: t.active_cameras }));
    };

    wsService.on('detection', handleDetection);
    wsService.on('telemetry', handleTelemetry);

    return () => {
      wsService.off('detection', handleDetection);
      wsService.off('telemetry', handleTelemetry);
    };
  }, []);

  // Handle snapshot to enroll
  const handleEnrollSnapshot = (blob, cameraId) => {
    setEnrollModalSnapshot(blob);
  };

  // Quick Add Camera
  const handleAddCamera = async (e) => {
    e.preventDefault();
    if (!newCamData.name.trim()) return;

    await apiService.addCamera({
      camera_id: `cam_${Date.now().toString().slice(-3)}`,
      name: newCamData.name.trim(),
      source: newCamData.source.trim(),
      zone: newCamData.zone
    });

    setShowAddCamModal(false);
    setNewCamData({ name: '', source: '0', zone: 'Zone A' });
    loadData();
  };

  // Focused camera object
  const focusedCam = useMemo(() => {
    return cameras.find(c => c.camera_id === focusedCameraId) || cameras[0];
  }, [cameras, focusedCameraId]);

  return (
    <div className="space-y-6">
      <section className="dashboard-hero cosmic-hero">
        <div className="cosmic-stars" aria-hidden="true" />
        <div className="cosmic-glow cosmic-glow-a" aria-hidden="true" />
        <div className="cosmic-glow cosmic-glow-b" aria-hidden="true" />
        <div className="orbital-arc orbital-arc-left" aria-hidden="true" />
        <div className="orbital-arc orbital-arc-right" aria-hidden="true" />
        <span className="ghost-sticker ghost-sticker-live">GHOST TRAIL · LIVE</span>
        <span className="ghost-sticker ghost-sticker-ai">AI / RE-ID / BEHAVIOR</span>

        <div className="hero-copy relative z-20">
          <div className="hero-eyebrow"><span className="hero-live-dot" /> AI SURVEILLANCE</div>
          <h1>Ghost <em>Trail</em></h1>
          <p>AI-powered video intelligence that detects, tracks and explains suspicious activity in real time.</p>
        </div>

        <div className="hero-feature-rail" aria-label="Ghost Trail capabilities">
          <button className="feature-step active" onClick={() => document.getElementById('live-cameras')?.scrollIntoView({ behavior: 'smooth' })}>
            <span className="feature-icon"><Eye size={16} /></span>
            <span><b>LIVE VIEW</b><small>Monitor in real time</small></span>
          </button>
          <button className="feature-step" onClick={() => navigate('/tracking')}>
            <span className="feature-icon"><Crosshair size={16} /></span>
            <span><b>TRACKING</b><small>Follow identities</small></span>
          </button>
          <button className="feature-step" onClick={() => navigate('/alerts')}>
            <span className="feature-icon"><AlertTriangle size={16} /></span>
            <span><b>ALERTS</b><small>Instant notifications</small></span>
          </button>
          <button className="feature-step" onClick={() => navigate('/tracking')}>
            <span className="feature-icon"><BarChart3 size={16} /></span>
            <span><b>ANALYTICS</b><small>Understand patterns</small></span>
          </button>
          <button className="feature-step" onClick={() => navigate('/settings')}>
            <span className="feature-icon"><Settings2 size={16} /></span>
            <span><b>SETTINGS</b><small>Configure system</small></span>
          </button>
        </div>

        <div
          className={`hero-orbit-system ${heroDragging ? 'is-dragging' : ''}`}
          aria-label="Interactive rotating surveillance interface"
          onPointerDown={beginHeroDrag}
          onPointerMove={moveHeroDrag}
          onPointerUp={endHeroDrag}
          onPointerCancel={endHeroDrag}
        >
          <div
            className="orbital-globe"
            aria-hidden="true"
            style={{ transform: `translate(-50%, -50%) rotateY(${heroYaw * 0.72}deg) rotateX(${heroPitch}deg)` }}
          ><div className="globe-grid" style={{ transform: `rotate(${heroRotation * 0.22}deg)` }} /></div>
          <div className="hero-orbit-ring ring-outer" style={{ transform: `translate(-50%, -50%) rotate(${heroRotation}deg) rotateX(${58 + heroPitch}deg)` }} />
          <div className="hero-orbit-ring ring-inner" style={{ transform: `translate(-50%, -50%) rotate(${-heroRotation * 0.72}deg) rotateX(${64 - heroPitch}deg)` }} />
          <div className="hero-orbit-ring ring-dashed" style={{ transform: `translate(-50%, -50%) rotate(${heroRotation * 0.48}deg) rotateX(${72 + heroPitch}deg)` }} />
          <div className="orbit-satellite satellite-a" style={{ transform: `translateY(-50%) rotate(${heroRotation}deg)` }} aria-hidden="true" />
          <div className="orbit-satellite satellite-b" style={{ transform: `translateY(-50%) rotate(${-heroRotation * 1.28 + 135}deg)` }} aria-hidden="true" />
          <div className="rotation-platform" aria-hidden="true"><i style={{ transform: `translate(-50%, -50%) rotate(${heroRotation}deg)` }} /></div>

          <button className="orbit-control orbit-left" onPointerDown={(e) => e.stopPropagation()} onClick={() => setHeroRotation(v => (v - 30 + 360) % 360)} aria-label="Rotate left">‹</button>
          <button className="orbit-control orbit-right" onPointerDown={(e) => e.stopPropagation()} onClick={() => setHeroRotation(v => (v + 30) % 360)} aria-label="Rotate right">›</button>

          <div className="orbit-node orbit-node-left"><Crosshair size={16} /><span>TRACKING</span></div>
          <div className="orbit-node orbit-node-top"><Eye size={16} /><span>LIVE VIEW</span></div>
          <div className="orbit-node orbit-node-right"><AlertTriangle size={16} /><span>ALERTS</span></div>
          <div className="orbit-node orbit-node-bottom"><BarChart3 size={16} /><span>ANALYTICS</span></div>

          <div
            className="hero-device-wrap"
            style={{
              transform: `translate(-50%, -50%) translateX(${heroShift}px) perspective(1200px) rotateY(${heroYaw}deg) rotateX(${heroPitch}deg) scale(${0.965 + heroDepth * 0.035})`,
              zIndex: 12 + Math.round(heroDepth * 3)
            }}
          >
            <div className="hero-device">
              <div className="device-topbar"><span className="device-brand">Ghost <span>Trail</span></span><div className="device-tabs"><b>LIVE</b><span>TRACKING</span><span>ALERTS</span><span>ANALYTICS</span></div><span className="device-status"><i /> {summary.activeCameras || 3} CAMERAS</span></div>
              <div className="device-body">
                <div className="device-cams">
                  {['CAM 01','CAM 02','CAM 03','CAM 04'].map((cam, i) => <div className={`device-cam ${i === 0 ? 'selected' : ''}`} key={cam}><span className="cam-thumb" /><span>{cam}</span><small>{['Main Gate','Lobby','Parking','Corridor'][i]}</small></div>)}
                </div>
                <div className="device-feed">
                  <div className="feed-header"><span>CAM 01 · MAIN GATE</span><span>16:32:18 · LIVE</span></div>
                  <div className="feed-scene"><div className="scan-grid" /><div className="person person-one"><span>ID: 042</span></div><div className="person person-two"><span>ID: 015</span></div><div className="feed-crosshair" /></div>
                </div>
              </div>
              <div className="device-metrics"><span><b>{summary.totalDetections || 48}</b> People tracked</span><span><b>{summary.activeAlerts || 1}</b> Active alerts</span><span><b>{summary.fps || 29.4}</b> FPS</span></div>
            </div>
          </div>

          <div
            className="hero-tablet"
            aria-hidden="true"
            style={{
              transform: `translate(-50%, -50%) translateX(${-heroShift * 0.72}px) translateY(${Math.cos(heroRad) * 5}px) perspective(1000px) rotateY(${-14 - heroYaw * 0.78}deg) rotateZ(${1 + Math.sin(heroRad) * 1.2}deg) scale(${0.94 + (1 - heroDepth) * 0.08})`,
              zIndex: 8 + Math.round((1 - heroDepth) * 4)
            }}
          >
            <div className="tablet-grid" />
            <span className="tablet-label tablet-label-a">CAM 02</span>
            <span className="tablet-label tablet-label-b">CAM 03</span>
            <span className="tablet-label tablet-label-c">CAM 01</span>
          </div>

          <div
            className="hero-phone"
            onPointerDown={(e) => e.stopPropagation()}
            style={{
              transform: `translate(-50%, -50%) translateX(${Math.sin(heroRad + 1.25) * 28}px) translateY(${Math.cos(heroRad * 1.1) * 7}px) perspective(900px) rotateY(${8 + heroYaw * 0.62}deg) rotateZ(${Math.sin(heroRad) * 2}deg) scale(${0.96 + Math.sin(heroRad + 0.8) * 0.035})`,
              zIndex: 15 + Math.round(Math.sin(heroRad + 0.8) * 2)
            }}
          >
            <div className="phone-top">Ghost <span>Trail</span><i>LIVE</i></div>
            <div className="phone-feed"><div className="phone-person" /></div>
            <strong>Real-time<br />intelligence.</strong>
            <button onClick={() => navigate('/alerts')}>View alerts →</button>
          </div>

          <div className="hero-rotate-bar" onPointerDown={(e) => e.stopPropagation()}>
            <button onClick={() => setHeroRotation(v => (v - 15 + 360) % 360)}>‹</button>
            <Rotate3D size={15} />
            <span>ROTATE VIEW</span>
            <button onClick={() => setHeroRotation(v => (v + 15) % 360)}>›</button>
            <button className={heroAutoRotate ? 'auto-on' : ''} onClick={() => setHeroAutoRotate(v => !v)}>{heroAutoRotate ? 'AUTO' : 'PAUSED'}</button>
            <small className="drag-hint">DRAG</small>
          </div>
        </div>

        <div className="hero-bottom-panel">
          <div className="hero-actions">
            <button className="hero-primary" onClick={() => document.getElementById('live-cameras')?.scrollIntoView({ behavior: 'smooth' })}>Open command center <span>↗</span></button>
            <button className="hero-secondary" onClick={() => setLayoutMode('focus')}>Watch live <span>▶</span></button>
          </div>
          <div className="hero-mini-stats">
            <div><strong>{summary.activeCameras || 3}</strong><span>Cameras online</span></div>
            <div><strong>{summary.totalDetections || 48}</strong><span>People tracked</span></div>
            <div><strong>{summary.activeAlerts || 1}</strong><span>Active alerts</span></div>
            <div><strong>{summary.fps || 29.4}</strong><span>FPS</span></div>
          </div>
        </div>
      </section>

      {/* Ratio-inspired technical telemetry strip */}
      <div className="ghost-telemetry-strip" aria-label="Ghost Trail system telemetry">
        <div className="ghost-telemetry-track">
          <span>// GHOST TRAIL ACTIVE</span>
          <span>// ZERO-TRUST CAMERA PIPELINE</span>
          <span>// REAL-TIME PERSON RE-ID</span>
          <span>// BEHAVIOR ANOMALY ENGINE</span>
          <span>// LIVE TELEMETRY</span>
          <span>// GHOST TRAIL ACTIVE</span>
          <span>// ZERO-TRUST CAMERA PIPELINE</span>
          <span>// REAL-TIME PERSON RE-ID</span>
          <span>// BEHAVIOR ANOMALY ENGINE</span>
          <span>// LIVE TELEMETRY</span>
        </div>
      </div>

      {/* ── TOP TELEMETRY HUD METRICS ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Cameras online"
          value={`${summary.activeCameras || 3} / ${cameras.length || 4}`}
          sub="Live channels"
          icon={Camera}
          accent="text-cyan-400 bg-cyan-950/40 border-cyan-500/30"
          badge="1080P"
        />

        <MetricCard
          label="People detected"
          value={summary.totalDetections || 48}
          sub="Tracks recorded"
          icon={Activity}
          accent="text-emerald-400 bg-emerald-950/40 border-emerald-500/30"
          badge="Re-ID OSNet"
        />

        <MetricCard
          label="Active alerts"
          value={summary.activeAlerts || 1}
          sub="Needs attention"
          icon={AlertTriangle}
          accent="text-rose-400 bg-rose-950/40 border-rose-500/30"
          badge={summary.activeAlerts ? 'ALERT ACTIVE' : 'NOMINAL'}
        />

        <MetricCard
          label="AI performance"
          value={`${summary.fps || 29.4} FPS`}
          sub="Real-time inference"
          icon={Cpu}
          accent="text-amber-400 bg-amber-950/40 border-amber-500/30"
          badge="CUDA Core"
        />
      </div>

      {/* ── LIVE DETECTION TICKER BAR ────────────────────────────────────────── */}
      <div className="sentinel-card p-3 flex items-center gap-4 overflow-hidden">
        <div className="flex items-center gap-2 text-xs font-medium text-zinc-400 flex-shrink-0">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
          <span>Live activity</span>
        </div>

        <div className="flex-1 flex items-center gap-3 overflow-x-auto text-xs font-mono no-scrollbar">
          {liveTicker.length > 0 ? (
            liveTicker.map((t) => (
              <div
                key={t.id}
                onClick={() => {
                  setFocusedCameraId(t.camera_id);
                  setLayoutMode('focus');
                }}
                className={`flex items-center gap-2 px-3 py-1 rounded-lg border cursor-pointer whitespace-nowrap transition-all ${
                  t.is_known 
                    ? 'bg-slate-900 border-slate-700/80 text-slate-200 hover:border-emerald-500/50' 
                    : 'bg-rose-950/40 border-rose-500/40 text-rose-300 hover:bg-rose-900/40'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${t.is_known ? 'bg-emerald-400' : 'bg-rose-500 animate-pulse'}`} />
                <span className="font-bold">{t.name}</span>
                <span className="text-[10px] text-slate-400">{t.camera_id?.toUpperCase()}</span>
                <span className="text-[10px] text-cyan-400">{(t.confidence * 100).toFixed(0)}%</span>
                <span className="text-[10px] text-slate-500">{t.time}</span>
              </div>
            ))
          ) : (
            <div className="text-slate-500 text-xs font-mono">
              Listening for live biometric face detections & YOLO bounding box telemetry...
            </div>
          )}
        </div>
      </div>

      {/* ── SURVEILLANCE MATRIX CONTROLS ─────────────────────────────────────── */}
      <div id="live-cameras" className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold tracking-tight text-zinc-100 flex items-center gap-2">
            <Radio size={16} className="text-cyan-400" />
            Live cameras
          </h2>
          <span className="text-xs font-mono text-slate-500">
            {cameras.length} connected cameras
          </span>
        </div>

        {/* Layout Switcher & Channel Actions */}
        <div className="flex items-center gap-2">
          {/* Layout Buttons */}
          <div className="flex bg-slate-900 border border-slate-800 rounded-xl p-1">
            <button
              onClick={() => setLayoutMode('grid2x2')}
              title="2x2 Multi-View Grid"
              className={`p-1.5 rounded-lg text-xs transition-colors ${
                layoutMode === 'grid2x2' 
                  ? 'bg-cyan-500 text-black font-bold shadow-md' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <LayoutGrid size={16} />
            </button>

            <button
              onClick={() => setLayoutMode('director')}
              title="Director Mode (1 Large + Thumbnails)"
              className={`p-1.5 rounded-lg text-xs transition-colors ${
                layoutMode === 'director' 
                  ? 'bg-cyan-500 text-black font-bold shadow-md' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Grid size={16} />
            </button>

            <button
              onClick={() => setLayoutMode('focus')}
              title="1x1 Single Channel Focus"
              className={`p-1.5 rounded-lg text-xs transition-colors ${
                layoutMode === 'focus' 
                  ? 'bg-cyan-500 text-black font-bold shadow-md' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Maximize size={16} />
            </button>
          </div>

          {/* Quick Add Camera Feed */}
          <button
            onClick={() => setShowAddCamModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 border border-slate-700/80 hover:border-cyan-500/50 text-xs font-mono text-slate-300 hover:text-white transition-all shadow-sm"
          >
            <Plus size={14} className="text-cyan-400" />
            <span>Add camera</span>
          </button>
        </div>
      </div>

      {/* ── CAMERA VIDEO FEEDS CONTAINER ────────────────────────────────────── */}
      {layoutMode === 'grid2x2' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {cameras.map(cam => (
            <CameraFeed
              key={cam.camera_id}
              camera={cam}
              isFocused={focusedCameraId === cam.camera_id}
              onToggleFocus={() => {
                setFocusedCameraId(cam.camera_id);
                setLayoutMode('focus');
              }}
              onEnrollSnapshot={handleEnrollSnapshot}
            />
          ))}
        </div>
      )}

      {layoutMode === 'director' && focusedCam && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Main Hero Feed (2 cols) */}
          <div className="lg:col-span-2">
            <CameraFeed
              camera={focusedCam}
              isFocused={true}
              onEnrollSnapshot={handleEnrollSnapshot}
            />
          </div>

          {/* Side Thumbnail Feeds (1 col) */}
          <div className="space-y-4 max-h-[640px] overflow-y-auto pr-1">
            {cameras
              .filter(c => c.camera_id !== focusedCam.camera_id)
              .map(cam => (
                <div 
                  key={cam.camera_id}
                  onClick={() => setFocusedCameraId(cam.camera_id)}
                  className="cursor-pointer transition-transform hover:scale-[1.01]"
                >
                  <CameraFeed
                    camera={cam}
                    onEnrollSnapshot={handleEnrollSnapshot}
                  />
                </div>
              ))}
          </div>
        </div>
      )}

      {layoutMode === 'focus' && focusedCam && (
        <div className="space-y-4">
          <div className="flex items-center justify-between px-2">
            <span className="text-xs font-mono text-cyan-400">
              Focused camera: <strong>{focusedCam.name}</strong> ({focusedCam.camera_id})
            </span>
            <button
              onClick={() => setLayoutMode('grid2x2')}
              className="text-xs font-mono text-slate-400 hover:text-white underline"
            >
              Back to all cameras
            </button>
          </div>

          <div className="max-w-5xl mx-auto">
            <CameraFeed
              camera={focusedCam}
              isFocused={true}
              onEnrollSnapshot={handleEnrollSnapshot}
            />
          </div>
        </div>
      )}

      {/* Snapshot to Enroll Modal */}
      {enrollModalSnapshot && (
        <WebcamEnrollModal
          initialImageBlob={enrollModalSnapshot}
          onClose={() => setEnrollModalSnapshot(null)}
          onSuccess={() => {
            setEnrollModalSnapshot(null);
          }}
        />
      )}

      {/* Add Camera Modal */}
      {showAddCamModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-in fade-in duration-150">
          <div className="w-full max-w-md bg-[#0e141c] border border-cyan-500/40 rounded-2xl shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="font-mono text-sm font-bold text-slate-100 uppercase">
                Add camera
              </h3>
              <button onClick={() => setShowAddCamModal(false)}>
                <X size={18} className="text-slate-400 hover:text-white" />
              </button>
            </div>

            <form onSubmit={handleAddCamera} className="space-y-4 font-mono text-xs">
              <div>
                <label className="block text-slate-400 uppercase mb-1">Camera Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. North Perimeter Gate"
                  value={newCamData.name}
                  onChange={e => setNewCamData({ ...newCamData, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-slate-100 outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 uppercase mb-1">Stream source</label>
                <input
                  type="text"
                  required
                  placeholder="0 (USB cam) or rtsp://... or http://..."
                  value={newCamData.source}
                  onChange={e => setNewCamData({ ...newCamData, source: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-slate-100 outline-none focus:border-cyan-500"
                />
                <span className="text-[10px] text-slate-500 mt-1 block">
                  Supports local webcam index (0, 1), RTSP, or HTTP MJPEG URL.
                </span>
              </div>

              <div>
                <label className="block text-slate-400 uppercase mb-1">Location</label>
                <select
                  value={newCamData.zone}
                  onChange={e => setNewCamData({ ...newCamData, zone: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-slate-100 outline-none focus:border-cyan-500"
                >
                  <option value="Zone A">Zone A - Main Lobby & Entrance</option>
                  <option value="Zone B">Zone B - East Perimeter & Exterior</option>
                  <option value="Zone C">Zone C - Server Vault & Labs</option>
                  <option value="Zone D">Zone D - Loading Dock & Logistics</option>
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddCamModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-lg bg-cyan-400 text-black font-bold shadow-lg"
                >
                  Connect camera
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
