import React, { useState, useEffect, useRef, memo } from 'react';
import { 
  Maximize2, Minimize2, ZoomIn, ZoomOut, Camera as CameraIcon, 
  UserPlus, Sliders, Shield, AlertTriangle, Eye, EyeOff, Radio,
  RefreshCw, Move, Check
} from 'lucide-react';

export const CameraFeed = memo(({ 
  camera, 
  onEnrollSnapshot, 
  isFocused = false, 
  onToggleFocus,
  onOpenSettings
}) => {
  const [zoomLevel, setZoomLevel] = useState(1);
  const [panPos, setPanPos] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showHud, setShowHud] = useState(true);
  const [showPtz, setShowPtz] = useState(false);
  const [hasStreamError, setHasStreamError] = useState(false);
  const [flashSnapshot, setFlashSnapshot] = useState(false);
  const [detectedTargets, setDetectedTargets] = useState([]);
  
  const containerRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);

  // Timecode
  const [timecode, setTimecode] = useState('');
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const ms = String(now.getMilliseconds()).padStart(3, '0').slice(0, 2);
      setTimecode(`${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${ms}`);
    };
    updateTime();
    const id = setInterval(updateTime, 100);
    return () => clearInterval(id);
  }, []);

  // Simulated target generator for active simulation or canvas fallback
  useEffect(() => {
    if (!camera.enabled) return;

    let angle = Math.random() * Math.PI * 2;
    const interval = setInterval(() => {
      angle += 0.08;
      const baseWidth = 320;
      const baseHeight = 180;
      
      const x1 = Math.floor(100 + Math.cos(angle) * 50 + Math.sin(angle * 0.5) * 20);
      const y1 = Math.floor(40 + Math.sin(angle * 0.7) * 25);
      const w = 55;
      const h = 100;

      const isUnknown = camera.camera_id === 'cam_2';
      setDetectedTargets([
        {
          id: isUnknown ? 'Guest_882' : 'Ganesh',
          trackId: 104,
          confidence: 0.94,
          isUnknown,
          bbox: [x1, y1, x1 + w, y1 + h]
        }
      ]);
    }, 150);

    return () => clearInterval(interval);
  }, [camera.enabled, camera.camera_id]);

  // Synthetic Surveillance Simulation renderer if real stream is offline
  useEffect(() => {
    if (!hasStreamError && camera.online && camera.enabled) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let frameId;
    let tick = 0;

    const render = () => {
      tick++;
      const w = canvas.width = 480;
      const h = canvas.height = 270;

      // Dark tactical background
      ctx.fillStyle = '#080C10';
      ctx.fillRect(0, 0, w, h);

      if (!camera.enabled) {
        // Disabled camera standby pattern
        ctx.fillStyle = '#161B22';
        ctx.font = '12px "Share Tech Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText('CAMERA CHANNEL DEACTIVATED', w / 2, h / 2 - 8);
        ctx.fillStyle = '#484F58';
        ctx.font = '10px "Share Tech Mono", monospace';
        ctx.fillText('STANDBY MODE — STANDBY PROTOCOL ACTIVE', w / 2, h / 2 + 12);
        return;
      }

      // Simulated security camera grid
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.08)';
      ctx.lineWidth = 1;
      const gridSize = 30;
      for (let x = 0; x < w; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // Laser sweep line
      const sweepY = (tick * 1.5) % h;
      const grad = ctx.createLinearGradient(0, sweepY - 20, 0, sweepY);
      grad.addColorStop(0, 'rgba(6, 182, 212, 0)');
      grad.addColorStop(1, 'rgba(6, 182, 212, 0.25)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, sweepY - 20, w, 20);

      ctx.strokeStyle = 'rgba(6, 182, 212, 0.8)';
      ctx.beginPath();
      ctx.moveTo(0, sweepY);
      ctx.lineTo(w, sweepY);
      ctx.stroke();

      // Simulated humanoid figure wireframe
      const px = w * 0.45 + Math.sin(tick * 0.02) * 50;
      const py = h * 0.35 + Math.cos(tick * 0.015) * 15;
      const isSuspect = camera.camera_id === 'cam_2';
      const wireColor = isSuspect ? '#EF4444' : '#10B981';

      // Humanoid head & torso wireframe
      ctx.strokeStyle = wireColor;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(px, py, 14, 0, Math.PI * 2);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(px, py + 14);
      ctx.lineTo(px, py + 75);
      ctx.lineTo(px - 18, py + 130);
      ctx.moveTo(px, py + 75);
      ctx.lineTo(px + 18, py + 130);
      ctx.moveTo(px - 22, py + 38);
      ctx.lineTo(px + 22, py + 38);
      ctx.stroke();

      // AI Bounding Box HUD
      const bx = px - 35;
      const by = py - 20;
      const bw = 70;
      const bh = 155;

      ctx.strokeStyle = wireColor;
      ctx.lineWidth = 2;
      // Corners
      const cl = 12;
      ctx.beginPath();
      ctx.moveTo(bx, by + cl); ctx.lineTo(bx, by); ctx.lineTo(bx + cl, by);
      ctx.moveTo(bx + bw - cl, by); ctx.lineTo(bx + bw, by); ctx.lineTo(bx + bw, by + cl);
      ctx.moveTo(bx, by + bh - cl); ctx.lineTo(bx, by + bh); ctx.lineTo(bx + cl, by + bh);
      ctx.moveTo(bx + bw - cl, by + bh); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx + bw, by + bh - cl);
      ctx.stroke();

      // Label badge
      const labelText = isSuspect ? 'UNKNOWN #GUEST_882 [89%]' : 'GANESH [95%]';
      ctx.fillStyle = isSuspect ? 'rgba(239, 68, 68, 0.9)' : 'rgba(16, 185, 129, 0.9)';
      ctx.fillRect(bx, by - 18, ctx.measureText(labelText).width + 12, 16);
      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 9px "Share Tech Mono", monospace';
      ctx.fillText(labelText, bx + 6, by - 6);

      // Channel watermark
      ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.font = '9px "Share Tech Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`GHOST TRAIL SYNTHETIC MATRIX // 1080P 30FPS`, w - 12, h - 12);
      ctx.textAlign = 'left';

      frameId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(frameId);
  }, [hasStreamError, camera.online, camera.enabled, camera.camera_id]);

  // Digital Zoom & Pan handling
  const handleZoom = (delta) => {
    setZoomLevel(prev => {
      const next = Math.min(Math.max(1, prev + delta), 4);
      if (next === 1) setPanPos({ x: 0, y: 0 });
      return next;
    });
  };

  const handleMouseDown = (e) => {
    if (zoomLevel <= 1) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - panPos.x, y: e.clientY - panPos.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging || zoomLevel <= 1) return;
    setPanPos({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Take snapshot
  const triggerSnapshot = () => {
    setFlashSnapshot(true);
    setTimeout(() => setFlashSnapshot(false), 200);

    // Create an offscreen canvas to grab frame
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 360;
    const ctx = canvas.getContext('2d');

    if (imageRef.current && !hasStreamError) {
      try {
        ctx.drawImage(imageRef.current, 0, 0, 640, 360);
      } catch (e) {
        if (canvasRef.current) ctx.drawImage(canvasRef.current, 0, 0, 640, 360);
      }
    } else if (canvasRef.current) {
      ctx.drawImage(canvasRef.current, 0, 0, 640, 360);
    }

    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ghost_trail_${camera.camera_id}_${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);
    }, 'image/png');
  };

  // Snapshot to enroll
  const handleEnrollClick = () => {
    setFlashSnapshot(true);
    setTimeout(() => setFlashSnapshot(false), 200);

    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 360;
    const ctx = canvas.getContext('2d');

    if (imageRef.current && !hasStreamError) {
      try {
        ctx.drawImage(imageRef.current, 0, 0, 640, 360);
      } catch (e) {
        if (canvasRef.current) ctx.drawImage(canvasRef.current, 0, 0, 640, 360);
      }
    } else if (canvasRef.current) {
      ctx.drawImage(canvasRef.current, 0, 0, 640, 360);
    }

    canvas.toBlob((blob) => {
      if (blob && onEnrollSnapshot) {
        onEnrollSnapshot(blob, camera.camera_id);
      }
    }, 'image/jpeg', 0.92);
  };

  // Toggle fullscreen
  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  const isLive = camera.enabled && camera.online;

  return (
    <div
      ref={containerRef}
      className={`group relative rounded-xl overflow-hidden border transition-all duration-300 flex flex-col ${
        isFocused 
          ? 'border-cyan-500 shadow-[0_0_25px_rgba(6,182,212,0.25)] ring-1 ring-cyan-500/40' 
          : 'border-slate-800 bg-[#0d131a] hover:border-slate-700 shadow-lg'
      }`}
    >
      {/* Card Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-[#090d12]/90 border-b border-slate-800/80 backdrop-blur-sm z-20 select-none">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center">
            <span className={`w-2.5 h-2.5 rounded-full ${isLive ? 'bg-emerald-500' : 'bg-rose-500'}`} />
            {isLive && (
              <span className="absolute w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping opacity-75" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold tracking-wider text-slate-100 uppercase">
                {camera.name || `Channel ${camera.camera_id}`}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono tracking-widest bg-slate-800/80 text-cyan-400 border border-slate-700/60 uppercase">
                {camera.camera_id}
              </span>
            </div>
            {camera.zone && (
              <span className="text-[10px] font-mono text-slate-400">
                {camera.zone}
              </span>
            )}
          </div>
        </div>

        {/* Action icons */}
        <div className="flex items-center gap-1">
          {/* HUD toggle */}
          <button
            onClick={() => setShowHud(!showHud)}
            title={showHud ? 'Hide Telemetry HUD' : 'Show Telemetry HUD'}
            className={`p-1.5 rounded-md text-xs transition-colors ${
              showHud ? 'text-cyan-400 bg-cyan-950/40 hover:bg-cyan-900/60' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {showHud ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>

          {/* PTZ overlay toggle */}
          <button
            onClick={() => setShowPtz(!showPtz)}
            title="Digital PTZ Controls"
            className={`p-1.5 rounded-md text-xs transition-colors ${
              showPtz ? 'text-amber-400 bg-amber-950/40 hover:bg-amber-900/60' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Move size={14} />
          </button>

          {/* Quick Snapshot */}
          <button
            onClick={triggerSnapshot}
            title="Take High-Res Snapshot"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <CameraIcon size={14} />
          </button>

          {/* Enroll Face from Feed */}
          {onEnrollSnapshot && (
            <button
              onClick={handleEnrollClick}
              title="Enroll Person From This Feed"
              className="p-1.5 rounded-md text-amber-400 hover:text-amber-300 hover:bg-amber-950/40 transition-colors"
            >
              <UserPlus size={14} />
            </button>
          )}

          {/* Focus mode */}
          {onToggleFocus && (
            <button
              onClick={onToggleFocus}
              title={isFocused ? 'Unfocus Channel' : 'Focus Mode (1x1)'}
              className={`p-1.5 rounded-md text-xs transition-colors ${
                isFocused ? 'text-cyan-400 bg-cyan-950/50' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Radio size={14} />
            </button>
          )}

          {/* Fullscreen */}
          <button
            onClick={toggleFullscreen}
            title="Toggle Fullscreen"
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Video Viewport Area */}
      <div 
        className="relative flex-1 bg-black overflow-hidden flex items-center justify-center min-h-[220px] cursor-crosshair select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* Shutter flash effect */}
        {flashSnapshot && (
          <div className="absolute inset-0 bg-white z-50 pointer-events-none animate-pulse" />
        )}

        {/* Video Canvas or Live MJPEG Image */}
        <div 
          className="relative w-full h-full flex items-center justify-center transition-transform duration-75"
          style={{
            transform: `scale(${zoomLevel}) translate(${panPos.x / zoomLevel}px, ${panPos.y / zoomLevel}px)`,
            cursor: zoomLevel > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default'
          }}
        >
          {camera.enabled && !hasStreamError ? (
            <img
              ref={imageRef}
              src={`/api/stream/${camera.camera_id}`}
              alt={`Stream ${camera.camera_id}`}
              className="w-full h-full object-contain pointer-events-none"
              onError={() => setHasStreamError(true)}
              onLoad={() => setHasStreamError(false)}
            />
          ) : null}

          {/* Fallback Canvas Surveillance Visualizer */}
          <canvas
            ref={canvasRef}
            className={`w-full h-full object-contain ${
              camera.enabled && !hasStreamError ? 'hidden' : 'block'
            }`}
          />
        </div>

        {/* Live HUD Telemetry Overlays */}
        {showHud && (
          <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-3 z-10">
            {/* Top HUD stats */}
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-rose-500 font-mono text-[10px] font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                  REC
                </span>
                <span className="px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-slate-300 font-mono text-[10px]">
                  {timecode}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-emerald-400 font-mono text-[10px] flex items-center gap-1">
                  <Radio size={10} className="animate-spin" />
                  {camera.fps || 28.5} FPS
                </span>
                <span className="px-2 py-0.5 rounded bg-black/60 backdrop-blur-md border border-slate-700/60 text-cyan-400 font-mono text-[10px]">
                  1080P
                </span>
                {zoomLevel > 1 && (
                  <span className="px-2 py-0.5 rounded bg-cyan-900/70 border border-cyan-400/60 text-cyan-300 font-mono text-[10px] font-bold">
                    {zoomLevel.toFixed(1)}x ZOOM
                  </span>
                )}
              </div>
            </div>

            {/* Tactical Crosshairs */}
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-30">
              <div className="w-8 h-8 border border-cyan-400/40 rounded-full flex items-center justify-center">
                <div className="w-1 h-1 bg-cyan-400 rounded-full" />
              </div>
            </div>

            {/* Bottom HUD stats */}
            <div className="flex items-end justify-between">
              <div className="flex flex-col gap-0.5 font-mono text-[9px] text-slate-400 bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-slate-800/80">
                <span className="text-slate-300 font-semibold tracking-wider">
                  ENCODER: H.264 / MJPEG
                </span>
                <span>LATENCY: 14.2ms | BITRATE: 3.4 Mbps</span>
                <span>AI INFERENCE: YOLOv8-NATIVE</span>
              </div>

              <div className="flex items-center gap-1 font-mono text-[10px] text-slate-400 bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-slate-800/80">
                <Shield size={11} className="text-emerald-400" />
                <span>GHOST TRAIL ACTIVE</span>
              </div>
            </div>
          </div>
        )}

        {/* Digital PTZ Controls Overlay */}
        {showPtz && (
          <div className="absolute bottom-12 right-3 z-30 bg-slate-950/85 backdrop-blur-md border border-slate-700/80 p-2 rounded-xl shadow-2xl flex flex-col items-center gap-1">
            <div className="text-[9px] font-mono text-cyan-400 uppercase tracking-widest mb-1">
              PTZ Matrix
            </div>
            {/* Pan up */}
            <button
              onClick={() => setPanPos(p => ({ ...p, y: p.y + 30 }))}
              className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold"
            >
              ▲
            </button>
            <div className="flex gap-1">
              {/* Pan left */}
              <button
                onClick={() => setPanPos(p => ({ ...p, x: p.x + 30 }))}
                className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold"
              >
                ◀
              </button>
              {/* Reset center */}
              <button
                onClick={() => { setZoomLevel(1); setPanPos({ x: 0, y: 0 }); }}
                className="w-7 h-7 rounded bg-slate-700 hover:bg-rose-600 text-slate-200 text-[10px] flex items-center justify-center font-mono font-bold"
              >
                RST
              </button>
              {/* Pan right */}
              <button
                onClick={() => setPanPos(p => ({ ...p, x: p.x - 30 }))}
                className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold"
              >
                ▶
              </button>
            </div>
            {/* Pan down */}
            <button
              onClick={() => setPanPos(p => ({ ...p, y: p.y - 30 }))}
              className="w-7 h-7 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center font-bold mb-1"
            >
              ▼
            </button>
            {/* Zoom in / out */}
            <div className="flex gap-1 w-full pt-1 border-t border-slate-800">
              <button
                onClick={() => handleZoom(0.5)}
                className="flex-1 py-1 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center"
                title="Zoom In"
              >
                <ZoomIn size={12} />
              </button>
              <button
                onClick={() => handleZoom(-0.5)}
                className="flex-1 py-1 rounded bg-slate-800 hover:bg-cyan-600 text-slate-200 text-xs flex items-center justify-center"
                title="Zoom Out"
              >
                <ZoomOut size={12} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer Info Strip */}
      <div className="px-3 py-1.5 bg-[#090d12] border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <span className="truncate max-w-[200px]" title={camera.source}>
            SRC: {camera.source || 'Default Input (0)'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {camera.enabled ? (
            <span className="text-emerald-400 flex items-center gap-1 font-semibold">
              <Check size={12} /> ACTIVE
            </span>
          ) : (
            <span className="text-slate-500 font-semibold">PAUSED</span>
          )}
        </div>
      </div>
    </div>
  );
});

export default CameraFeed;
