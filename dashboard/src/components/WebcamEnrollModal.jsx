import React, { useState, useRef, useEffect } from 'react';
import { 
  X, Upload, Camera, Check, AlertTriangle, ShieldCheck, 
  Sparkles, RefreshCw, UserCheck
} from 'lucide-react';
import apiService from '../services/api';

export const WebcamEnrollModal = ({ 
  initialImageBlob = null, 
  prefillName = '', 
  onClose, 
  onSuccess 
}) => {
  const [name, setName] = useState(prefillName);
  const [clearance, setClearance] = useState('Level 2 (Personnel)');
  const [imageFile, setImageFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [useWebcam, setUseWebcam] = useState(false);
  const [webcamStream, setWebcamStream] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);
  const [conflictData, setConflictData] = useState(null);

  const videoRef = useRef(null);
  const fileInputRef = useRef(null);

  // If initial image blob was supplied (from camera snapshot)
  useEffect(() => {
    if (initialImageBlob) {
      setImageFile(initialImageBlob);
      setPreviewUrl(URL.createObjectURL(initialImageBlob));
    }
  }, [initialImageBlob]);

  // Clean up webcam on unmount
  useEffect(() => {
    return () => {
      if (webcamStream) {
        webcamStream.getTracks().forEach(track => track.stop());
      }
    };
  }, [webcamStream]);

  // Start webcam
  const startWebcam = async () => {
    try {
      setUseWebcam(true);
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { width: 640, height: 480, facingMode: 'user' } 
      });
      setWebcamStream(stream);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err) {
      setStatus({ 
        type: 'error', 
        message: 'Could not access webcam. Please check browser permissions.' 
      });
      setUseWebcam(false);
    }
  };

  const stopWebcam = () => {
    if (webcamStream) {
      webcamStream.getTracks().forEach(track => track.stop());
      setWebcamStream(null);
    }
    setUseWebcam(false);
  };

  // Capture webcam photo
  const captureWebcam = () => {
    if (!videoRef.current) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth || 640;
    canvas.height = videoRef.current.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
    
    canvas.toBlob((blob) => {
      if (blob) {
        setImageFile(blob);
        setPreviewUrl(URL.createObjectURL(blob));
        stopWebcam();
      }
    }, 'image/jpeg', 0.95);
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setImageFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      if (useWebcam) stopWebcam();
    }
  };

  const handleSubmit = async (e, force = false, updateId = null) => {
    if (e) e.preventDefault();
    if (!name.trim()) {
      setStatus({ type: 'error', message: 'Full identity name is required.' });
      return;
    }
    if (!imageFile) {
      setStatus({ type: 'error', message: 'A face portrait photo is required.' });
      return;
    }

    setLoading(true);
    setStatus(null);
    setConflictData(null);

    try {
      const response = await apiService.registerPerson(name.trim(), imageFile, force, updateId);
      if (response?.success) {
        setStatus({ 
          type: 'success', 
          message: `Biometric identity successfully enrolled for "${name}"!` 
        });
        setTimeout(() => {
          if (onSuccess) onSuccess();
          onClose();
        }, 1200);
      } else if (response?.conflict) {
        setConflictData(response.conflict);
      } else {
        setStatus({ 
          type: 'error', 
          message: response?.error || 'Face embeddings could not be extracted. Try a sharper frontal image.' 
        });
      }
    } catch (err) {
      setStatus({ type: 'error', message: 'Server communication error.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-[#0e141c] border border-cyan-500/40 rounded-2xl shadow-[0_0_50px_rgba(6,182,212,0.15)] overflow-hidden">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-[#090d12] border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <ShieldCheck size={20} />
            </div>
            <div>
              <h3 className="font-mono text-sm font-bold tracking-wider text-slate-100 uppercase">
                Biometric Enrollment Core
              </h3>
              <p className="text-xs font-mono text-slate-400">
                Register AI face embeddings into the Ghost Trail watchlist
              </p>
            </div>
          </div>
          <button
            onClick={() => { stopWebcam(); onClose(); }}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 max-h-[80vh] overflow-y-auto">
          {/* Conflict Notification State */}
          {conflictData ? (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                  <div className="text-xs space-y-1">
                    <span className="font-bold block text-sm text-amber-300">
                      Similarity Conflict Detected
                    </span>
                    {conflictData.name.startsWith('Guest') ? (
                      <p>
                        This face matches prior unassigned profile <strong>{conflictData.name}</strong> with <strong>{(conflictData.score * 100).toFixed(1)}%</strong> confidence. Would you like to merge and promote this guest profile to official identity <strong>"{name}"</strong>?
                      </p>
                    ) : (
                      <p>
                        This face closely resembles existing enrolled person <strong>{conflictData.name}</strong> with <strong>{(conflictData.score * 100).toFixed(1)}%</strong> match. Force new duplicate registration anyway?
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {conflictData.thumbnail && (
                <div className="flex justify-center py-2">
                  <div className="relative w-24 h-24 rounded-full overflow-hidden border-2 border-amber-400/80 shadow-lg">
                    <img 
                      src={conflictData.thumbnail} 
                      alt={conflictData.name} 
                      className="w-full h-full object-cover"
                    />
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setConflictData(null)}
                  className="px-4 py-2 rounded-lg font-mono text-xs text-slate-400 hover:text-slate-200 bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={loading}
                  onClick={(e) => 
                    conflictData.name.startsWith('Guest') 
                      ? handleSubmit(e, true, conflictData.id) 
                      : handleSubmit(e, true, null)
                  }
                  className="px-5 py-2 rounded-lg font-mono text-xs font-bold text-black bg-amber-400 hover:bg-amber-300 transition-colors shadow-lg"
                >
                  {loading ? 'Processing...' : (conflictData.name.startsWith('Guest') ? 'Promote & Link Guest' : 'Force Register')}
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Status banner */}
              {status && (
                <div className={`p-3 rounded-lg text-xs font-mono flex items-center gap-2 border ${
                  status.type === 'success' 
                    ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300' 
                    : 'bg-rose-950/40 border-rose-500/40 text-rose-300'
                }`}>
                  {status.type === 'success' ? <Check size={16} /> : <AlertTriangle size={16} />}
                  <span>{status.message}</span>
                </div>
              )}

              {/* Full Name */}
              <div>
                <label className="block text-xs font-mono text-slate-300 uppercase tracking-wider mb-1.5">
                  Subject Full Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ganesh, Lakshya, Chief of Security"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[#090d12] border border-slate-700 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 text-slate-100 font-mono text-sm placeholder:text-slate-600 outline-none transition-colors"
                />
              </div>

              {/* Clearance / Role */}
              <div>
                <label className="block text-xs font-mono text-slate-300 uppercase tracking-wider mb-1.5">
                  Access Clearance Level
                </label>
                <select
                  value={clearance}
                  onChange={(e) => setClearance(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-[#090d12] border border-slate-700 focus:border-cyan-500 text-slate-100 font-mono text-sm outline-none cursor-pointer"
                >
                  <option value="Level 4 (Director)">Level 4 (Director / VIP - Full Access)</option>
                  <option value="Level 3 (Security Officer)">Level 3 (Security Officer / SOC Staff)</option>
                  <option value="Level 2 (Personnel)">Level 2 (Authorized Personnel / Employee)</option>
                  <option value="Level 1 (Contractor)">Level 1 (Contractor / Escorted Only)</option>
                </select>
              </div>

              {/* Portrait Capture Option */}
              <div>
                <label className="block text-xs font-mono text-slate-300 uppercase tracking-wider mb-2">
                  Facial Biometric Portrait
                </label>

                {/* Webcam Live Capture View */}
                {useWebcam ? (
                  <div className="space-y-3">
                    <div className="relative rounded-xl overflow-hidden bg-black aspect-video border border-cyan-500/50 flex items-center justify-center">
                      <video
                        ref={videoRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-full object-cover -scale-x-100"
                        onLoadedMetadata={() => videoRef.current?.play()}
                      />
                      {/* Face target guide oval */}
                      <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                        <div className="w-40 h-52 border-2 border-dashed border-cyan-400/70 rounded-[50%] shadow-[0_0_20px_rgba(6,182,212,0.3)]" />
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={captureWebcam}
                        className="flex-1 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-mono text-xs font-bold flex items-center justify-center gap-2 transition-colors shadow-lg"
                      >
                        <Camera size={14} /> Capture Face Frame
                      </button>
                      <button
                        type="button"
                        onClick={stopWebcam}
                        className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono text-xs"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div>
                    {previewUrl ? (
                      <div className="relative p-3 rounded-xl bg-[#090d12] border border-slate-700 flex items-center gap-4">
                        <img
                          src={previewUrl}
                          alt="Face Preview"
                          className="w-20 h-20 rounded-lg object-cover border border-cyan-500/40"
                        />
                        <div className="flex-1 font-mono text-xs space-y-1">
                          <span className="text-emerald-400 font-semibold flex items-center gap-1">
                            <Check size={14} /> Image Selected
                          </span>
                          <p className="text-slate-400 text-[11px]">
                            Portrait ready for feature extraction & OSNet embedding.
                          </p>
                          <button
                            type="button"
                            onClick={() => { setImageFile(null); setPreviewUrl(null); }}
                            className="text-rose-400 hover:text-rose-300 text-[11px] underline"
                          >
                            Remove / Change Photo
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-3">
                        {/* Drag and drop / file upload */}
                        <div
                          onClick={() => fileInputRef.current?.click()}
                          className="p-5 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/70 bg-[#090d12]/50 hover:bg-cyan-950/20 cursor-pointer flex flex-col items-center justify-center gap-2 text-center transition-all group"
                        >
                          <Upload className="w-6 h-6 text-slate-400 group-hover:text-cyan-400 transition-colors" />
                          <span className="font-mono text-xs text-slate-300">
                            Upload Photo File
                          </span>
                          <span className="text-[10px] text-slate-500">
                            JPG, PNG up to 10MB
                          </span>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            onChange={handleFileChange}
                            className="hidden"
                          />
                        </div>

                        {/* Webcam capture option */}
                        <div
                          onClick={startWebcam}
                          className="p-5 rounded-xl border border-dashed border-slate-700 hover:border-cyan-500/70 bg-[#090d12]/50 hover:bg-cyan-950/20 cursor-pointer flex flex-col items-center justify-center gap-2 text-center transition-all group"
                        >
                          <Camera className="w-6 h-6 text-slate-400 group-hover:text-cyan-400 transition-colors" />
                          <span className="font-mono text-xs text-slate-300">
                            Live Webcam Capture
                          </span>
                          <span className="text-[10px] text-slate-500">
                            Use local camera
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Submit buttons */}
              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => { stopWebcam(); onClose(); }}
                  className="px-4 py-2.5 rounded-lg font-mono text-xs text-slate-400 hover:text-slate-200 bg-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || !imageFile || !name.trim()}
                  className="px-6 py-2.5 rounded-lg font-mono text-xs font-bold text-black bg-cyan-400 hover:bg-cyan-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-[0_0_20px_rgba(6,182,212,0.3)] flex items-center gap-2"
                >
                  {loading ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      Computing Embeddings...
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} />
                      Enroll Identity
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};

export default WebcamEnrollModal;
