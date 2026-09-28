import React, { useState, useEffect, useRef } from 'react';
import { 
  Shield, Camera, Radio, AlertTriangle, Layers, 
  Compass, Crosshair, ZoomIn, ZoomOut, RefreshCw 
} from 'lucide-react';

export const TacticalMap = ({ 
  cameras = [], 
  sightings = [], 
  onSelectCamera 
}) => {
  const [selectedZone, setSelectedZone] = useState(null);
  const [viewMode, setViewMode] = useState('radar'); // 'radar' or 'blueprint'
  const canvasRef = useRef(null);

  // Entities on map
  const [targets, setTargets] = useState([
    { id: 't1', name: 'Ganesh', zone: 'Zone A', x: 0.28, y: 0.35, isSuspect: false, speed: 0.002, dir: 0.8 },
    { id: 't2', name: 'Lakshya', zone: 'Zone B', x: 0.68, y: 0.55, isSuspect: false, speed: 0.0015, dir: 2.1 },
    { id: 't3', name: 'Guest_882', zone: 'Zone B', x: 0.75, y: 0.32, isSuspect: true, speed: 0.003, dir: 1.4 },
    { id: 't4', name: 'Ansh', zone: 'Zone C', x: 0.38, y: 0.78, isSuspect: false, speed: 0.001, dir: 3.5 },
  ]);

  // Canvas radar animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let frameId;
    let angle = 0;

    const render = () => {
      angle += 0.025;
      const w = canvas.width = canvas.parentElement.clientWidth || 600;
      const h = canvas.height = canvas.parentElement.clientHeight || 400;

      // Dark canvas background
      ctx.fillStyle = '#080C10';
      ctx.fillRect(0, 0, w, h);

      // Blueprint / Facility Grid
      ctx.strokeStyle = 'rgba(15, 23, 42, 0.9)';
      ctx.lineWidth = 1;
      const step = 28;
      for (let x = 0; x < w; x += step) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y < h; y += step) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }

      // Facility Architectural Walls & Zones
      const drawZone = (x, y, zw, zh, label, accent, active) => {
        ctx.fillStyle = active ? `${accent}18` : 'rgba(15, 23, 42, 0.5)';
        ctx.fillRect(x, y, zw, zh);
        ctx.strokeStyle = active ? accent : 'rgba(51, 65, 85, 0.7)';
        ctx.lineWidth = active ? 2 : 1;
        ctx.strokeRect(x, y, zw, zh);

        ctx.fillStyle = active ? accent : '#64748B';
        ctx.font = 'bold 11px "Share Tech Mono", monospace';
        ctx.fillText(label.toUpperCase(), x + 10, y + 20);
      };

      // 4 Main Zones
      drawZone(w * 0.05, h * 0.1, w * 0.42, h * 0.38, 'Zone A: Main Lobby & Reception', '#06B6D4', selectedZone === 'Zone A');
      drawZone(w * 0.52, h * 0.1, w * 0.43, h * 0.38, 'Zone B: East Perimeter & Alley', '#F59E0B', selectedZone === 'Zone B');
      drawZone(w * 0.05, h * 0.53, w * 0.42, h * 0.4, 'Zone C: Server Vault & Lab', '#10B981', selectedZone === 'Zone C');
      drawZone(w * 0.52, h * 0.53, w * 0.43, h * 0.4, 'Zone D: Loading Dock & Logistics', '#8B5CF6', selectedZone === 'Zone D');

      // Camera FOV Cones
      const camPositions = [
        { id: 'cam_1', x: w * 0.1, y: h * 0.15, angle: 0.8, color: '#06B6D4', label: 'CAM-01' },
        { id: 'cam_2', x: w * 0.9, y: h * 0.15, angle: 2.4, color: '#F59E0B', label: 'CAM-02' },
        { id: 'cam_3', x: w * 0.1, y: h * 0.85, angle: -0.8, color: '#10B981', label: 'CAM-03' },
        { id: 'cam_4', x: w * 0.9, y: h * 0.85, angle: -2.4, color: '#8B5CF6', label: 'CAM-04' },
      ];

      camPositions.forEach(c => {
        // Draw FOV cone
        ctx.save();
        ctx.translate(c.x, c.y);
        ctx.rotate(c.angle);

        const coneRadius = 90;
        const coneAngle = Math.PI / 3;

        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, coneRadius, -coneAngle / 2, coneAngle / 2);
        ctx.closePath();
        ctx.fillStyle = `${c.color}20`;
        ctx.fill();
        ctx.strokeStyle = `${c.color}60`;
        ctx.stroke();

        ctx.restore();

        // Camera Icon Base
        ctx.fillStyle = c.color;
        ctx.beginPath();
        ctx.arc(c.x, c.y, 6, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 9px "Share Tech Mono", monospace';
        ctx.fillText(c.label, c.x - 14, c.y - 10);
      });

      // Radar Sweep Effect (Centered)
      if (viewMode === 'radar') {
        const cx = w / 2;
        const cy = h / 2;
        const radarR = Math.min(w, h) * 0.42;

        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, radarR, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(6, 182, 212, 0.25)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Range rings
        [0.3, 0.6, 1].forEach(frac => {
          ctx.beginPath();
          ctx.arc(cx, cy, radarR * frac, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(6, 182, 212, 0.12)';
          ctx.stroke();
        });

        // Sweep cone
        const sweepGrad = ctx.createConicGradient(angle, cx, cy);
        sweepGrad.addColorStop(0, 'rgba(6, 182, 212, 0)');
        sweepGrad.addColorStop(0.85, 'rgba(6, 182, 212, 0)');
        sweepGrad.addColorStop(1, 'rgba(6, 182, 212, 0.35)');
        ctx.fillStyle = sweepGrad;
        ctx.beginPath();
        ctx.arc(cx, cy, radarR, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
      }

      // Moving Target Pings
      targets.forEach(t => {
        const tx = t.x * w;
        const ty = t.y * h;

        // Ping wave
        const pingColor = t.isSuspect ? '#EF4444' : '#10B981';
        ctx.fillStyle = pingColor;
        ctx.beginPath();
        ctx.arc(tx, ty, 5, 0, Math.PI * 2);
        ctx.fill();

        // Pulsing halo
        const haloR = 6 + (Math.sin(angle * 4) * 3 + 3);
        ctx.strokeStyle = pingColor;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(tx, ty, haloR, 0, Math.PI * 2);
        ctx.stroke();

        // Label
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 9px "Share Tech Mono", monospace';
        ctx.fillText(t.name.toUpperCase(), tx + 8, ty - 4);
      });

      frameId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(frameId);
  }, [targets, selectedZone, viewMode]);

  return (
    <div className="relative w-full h-[520px] rounded-2xl overflow-hidden border border-slate-800 bg-[#080C10] shadow-2xl flex flex-col">
      {/* Map Control Bar */}
      <div className="flex items-center justify-between px-5 py-3 bg-[#090d12] border-b border-slate-800 z-10 select-none">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Crosshair size={18} />
          </div>
          <div>
            <h3 className="font-mono text-sm font-bold text-slate-100 uppercase tracking-wider">
              Tactical Facility 2D Operations Map
            </h3>
            <p className="text-[11px] font-mono text-slate-400">
              Live spatial coverage & target positioning telemetry
            </p>
          </div>
        </div>

        {/* View mode toggle & zone filters */}
        <div className="flex items-center gap-2">
          <div className="flex bg-slate-900 border border-slate-700/80 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('radar')}
              className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                viewMode === 'radar' 
                  ? 'bg-cyan-500 text-black font-bold' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Radar Sweep
            </button>
            <button
              onClick={() => setViewMode('blueprint')}
              className={`px-3 py-1 rounded-md text-xs font-mono transition-colors ${
                viewMode === 'blueprint' 
                  ? 'bg-cyan-500 text-black font-bold' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Blueprint Only
            </button>
          </div>

          {/* Clear filter */}
          {selectedZone && (
            <button
              onClick={() => setSelectedZone(null)}
              className="px-2.5 py-1 rounded-md bg-slate-800 text-xs font-mono text-slate-300 hover:text-white"
            >
              Clear Zone
            </button>
          )}
        </div>
      </div>

      {/* Map Canvas */}
      <div className="relative flex-1 w-full h-full overflow-hidden">
        <canvas ref={canvasRef} className="w-full h-full block cursor-pointer" />

        {/* Tactical Legend Overlay */}
        <div className="absolute bottom-4 left-4 p-3 rounded-xl bg-black/75 backdrop-blur-md border border-slate-800 text-[11px] font-mono space-y-1.5 z-10 pointer-events-none">
          <span className="text-slate-400 font-bold block mb-1 uppercase tracking-wider text-[10px]">
            Target Classification
          </span>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="text-slate-200">Authorized Personnel</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
            <span className="text-rose-400 font-semibold">Unidentified Guest / Intrusion</span>
          </div>
          <div className="flex items-center gap-2 pt-1 border-t border-slate-800">
            <span className="w-2.5 h-2.5 rounded bg-cyan-400/40 border border-cyan-400" />
            <span className="text-cyan-300">Camera FOV Cone</span>
          </div>
        </div>

        {/* Live Target Counts */}
        <div className="absolute top-4 right-4 p-3 rounded-xl bg-black/75 backdrop-blur-md border border-slate-800 text-[11px] font-mono space-y-1 z-10">
          <div className="flex items-center justify-between gap-4">
            <span className="text-slate-400">TRACKED TARGETS:</span>
            <span className="text-cyan-400 font-bold">{targets.length}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-slate-400">ACTIVE FOV CAMERAS:</span>
            <span className="text-emerald-400 font-bold">4 Channels</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TacticalMap;
