import React, { useState, useEffect } from 'react';
import TacticalMap from '../components/TacticalMap';
import apiService from '../services/api';
import { 
  Radio, Shield, Camera, Users, AlertTriangle, 
  MapPin, Activity, CheckCircle, ExternalLink 
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const TacticalMapPage = () => {
  const [cameras, setCameras] = useState([]);
  const [sightings, setSightings] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const load = async () => {
      try {
        const [cams, logs] = await Promise.all([
          apiService.getCameras(),
          apiService.getSightings()
        ]);
        setCameras(cams || []);
        setSightings(logs || []);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-widest bg-cyan-950 text-cyan-400 border border-cyan-500/40 uppercase">
              TACTICAL OPERATIONS CENTER
            </span>
            <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              RADAR ACTIVE
            </span>
          </div>
          <h2 className="text-2xl font-mono font-bold tracking-tight text-slate-100 uppercase">
            Facility 2D Surveillance Map
          </h2>
          <p className="text-xs font-mono text-slate-400">
            Real-time entity positioning, zone surveillance cones, and boundary intrusion tracking
          </p>
        </div>

        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-cyan-500/50 text-xs font-mono text-slate-300 hover:text-white transition-all shadow-md"
        >
          <Camera size={14} className="text-cyan-400" />
          <span>Switch to Video Grid</span>
        </button>
      </div>

      {/* Main Grid: Map + Side Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Map (3 cols on large screens) */}
        <div className="lg:col-span-3">
          <TacticalMap cameras={cameras} sightings={sightings} />
        </div>

        {/* Side Panel: Zones & Live Roster (1 col) */}
        <div className="space-y-5">
          {/* Zone Status Card */}
          <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <h3 className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <MapPin size={14} className="text-cyan-400" />
                Security Zones
              </h3>
              <span className="text-[10px] font-mono text-emerald-400">
                4 SECURE
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-cyan-400 font-semibold block">Zone A</span>
                  <span className="text-[11px] text-slate-400">Main Lobby & Entrance</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-[10px]">
                  1 Active
                </span>
              </div>

              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-amber-400 font-semibold block">Zone B</span>
                  <span className="text-[11px] text-slate-400">East Perimeter & Alley</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-500/30 text-rose-400 text-[10px] animate-pulse">
                  1 Unknown
                </span>
              </div>

              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-emerald-400 font-semibold block">Zone C</span>
                  <span className="text-[11px] text-slate-400">Server Vault & Lab</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-[10px]">
                  1 Active
                </span>
              </div>

              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-purple-400 font-semibold block">Zone D</span>
                  <span className="text-[11px] text-slate-400">Loading Bay & Logistics</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">
                  Standby
                </span>
              </div>
            </div>
          </div>

          {/* Active Spatial Roster */}
          <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <h3 className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Users size={14} className="text-cyan-400" />
                Live Target Spatial Roster
              </h3>
              <span className="text-[10px] font-mono text-cyan-400">
                4 Entities
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400" />
                  <div>
                    <span className="text-slate-100 font-semibold block">Ganesh</span>
                    <span className="text-[10px] text-slate-500">Zone A (Lobby)</span>
                  </div>
                </div>
                <span className="text-[11px] text-emerald-400 font-bold">94%</span>
              </div>

              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400" />
                  <div>
                    <span className="text-slate-100 font-semibold block">Lakshya</span>
                    <span className="text-[10px] text-slate-500">Zone B (Perimeter)</span>
                  </div>
                </div>
                <span className="text-[11px] text-emerald-400 font-bold">91%</span>
              </div>

              <div className="p-2.5 rounded-xl bg-rose-950/20 border border-rose-500/40 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                  <div>
                    <span className="text-rose-300 font-bold block">Guest_882</span>
                    <span className="text-[10px] text-rose-400/80">Zone B (Unknown)</span>
                  </div>
                </div>
                <span className="text-[11px] text-rose-400 font-bold">UNREG</span>
              </div>

              <div className="p-2.5 rounded-xl bg-[#090d12] border border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400" />
                  <div>
                    <span className="text-slate-100 font-semibold block">Ansh</span>
                    <span className="text-[10px] text-slate-500">Zone C (Vault)</span>
                  </div>
                </div>
                <span className="text-[11px] text-emerald-400 font-bold">88%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TacticalMapPage;
