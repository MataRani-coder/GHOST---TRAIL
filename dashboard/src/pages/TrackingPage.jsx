import React, { useState, useEffect, useMemo } from 'react';
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts';
import { 
  RefreshCw, Download, Activity, BarChart2, Shield, 
  Clock, Filter, Search, FileSpreadsheet, FileJson,
  Camera, CheckCircle2, AlertOctagon
} from 'lucide-react';
import apiService from '../services/api';

/* ── Custom Dark Recharts Tooltip ─────────────────────────────────────────── */
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="p-3 rounded-xl bg-[#090d12]/95 border border-slate-700 shadow-2xl font-mono text-xs space-y-1">
      <div className="text-slate-400 font-bold border-b border-slate-800 pb-1">
        {label}
      </div>
      {payload.map((entry, idx) => (
        <div key={idx} className="flex items-center justify-between gap-4" style={{ color: entry.color }}>
          <span className="capitalize">{entry.name}:</span>
          <span className="font-bold">{entry.value}</span>
        </div>
      ))}
    </div>
  );
};

export const TrackingPage = () => {
  const [sightings, setSightings] = useState([]);
  const [timelineData, setTimelineData] = useState([]);
  const [cameraData, setCameraData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterCamera, setFilterCamera] = useState('ALL');
  const [filterType, setFilterType] = useState('ALL'); // 'ALL' | 'KNOWN' | 'UNKNOWN'
  const [searchQuery, setSearchQuery] = useState('');
  const [lastRefreshed, setLastRefreshed] = useState(new Date());
  const [dashboardStats, setDashboardStats] = useState({ totalSightings: 0, authorizedDetections: 0, unknownGuests: 0, highRiskDetections: 0, averageConfidence: null });

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const [logs, stats] = await Promise.all([
        apiService.getSightings(),
        apiService.getStats()
      ]);
      setSightings(logs || []);
      if (stats) {
        setTimelineData(stats.timelineData || []);
        setCameraData(stats.cameraData || []);
        setDashboardStats({
          totalSightings: stats.totalSightings || 0,
          authorizedDetections: stats.authorizedDetections || 0,
          unknownGuests: stats.unknownGuests || 0,
          highRiskDetections: stats.highRiskDetections || 0,
          averageConfidence: stats.averageConfidence
        });
      }
      setLastRefreshed(new Date());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 15000);
    return () => clearInterval(interval);
  }, []);

  // Filtered sightings
  const filteredSightings = useMemo(() => {
    return sightings.filter(s => {
      const isHighRisk = s.face_review_status === 'denied';
      const isAuthorized = s.face_review_status === 'confirmed';
      const isUnknown = !isAuthorized && !isHighRisk;
      const matchesType = filterType === 'ALL'
        || (filterType === 'KNOWN' && isAuthorized)
        || (filterType === 'HIGH_RISK' && isHighRisk)
        || (filterType === 'UNKNOWN' && isUnknown);
      const matchesCam = filterCamera === 'ALL' || s.camera === filterCamera || s.camera_name === filterCamera;
      const matchesSearch = s.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        String(s.id).includes(searchQuery);
      return matchesType && matchesCam && matchesSearch;
    });
  }, [sightings, filterType, filterCamera, searchQuery]);

  // Derived statistics
  const totalDetections = dashboardStats.totalSightings;
  const unknownCount = dashboardStats.unknownGuests;
  const knownCount = dashboardStats.authorizedDetections;
  const highRiskCount = dashboardStats.highRiskDetections;
  const avgConfidence = dashboardStats.averageConfidence != null
    ? dashboardStats.averageConfidence.toFixed(1)
    : 'N/A';

  // Export CSV
  const exportCSV = () => {
    const headers = ['ID', 'Timestamp', 'Camera', 'Identified Name', 'Confidence', 'Bounding Box'];
    const rows = filteredSightings.map(s => [
      s.id,
      new Date(s.timestamp > 1e12 ? s.timestamp : s.timestamp * 1000).toISOString(),
      s.camera_name || s.camera,
      s.name,
      `${s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : 'N/A'}`,
      `"${s.bbox?.join(',')}"`
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sentinel_sightings_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export JSON
  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(filteredSightings, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sentinel_sightings_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-widest bg-cyan-950 text-cyan-400 border border-cyan-500/40 uppercase">
              GHOST TRAIL RE-ID ANALYTICS
            </span>
            <span className="text-xs font-mono text-slate-500">
              Refreshed {lastRefreshed.toLocaleTimeString()}
            </span>
          </div>
          <h2 className="text-2xl font-mono font-bold tracking-tight text-slate-100 uppercase">
            Multi-Camera Tracking & Intelligence
          </h2>
          <p className="text-xs font-mono text-slate-400">
            Real-time Re-ID trajectory logs, bounding box coordinates, and temporal movement heatmaps
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchLogs}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-cyan-500 text-xs font-mono text-slate-300 hover:text-white transition-all shadow-sm"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin text-cyan-400' : ''} />
            <span>Refresh</span>
          </button>

          <button
            onClick={exportCSV}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-xs font-mono text-cyan-300 hover:bg-cyan-900 transition-all shadow-sm"
          >
            <FileSpreadsheet size={14} />
            <span>Export CSV</span>
          </button>

          <button
            onClick={exportJSON}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-slate-600 text-xs font-mono text-slate-300 hover:text-white transition-all shadow-sm"
          >
            <FileJson size={14} />
            <span>JSON</span>
          </button>
        </div>
      </div>

      {/* ── STATS CARDS ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-1 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Total Sighting Logs</span>
          <div className="text-2xl font-bold text-slate-100">{totalDetections}</div>
          <span className="text-[11px] text-cyan-400">Persisted telemetry for today</span>
        </div>

        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-1 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Authorized Detections</span>
          <div className="text-2xl font-bold text-emerald-400">{knownCount}</div>
          <span className="text-[11px] text-slate-500">{((knownCount / (totalDetections || 1)) * 100).toFixed(0)}% of total traffic</span>
        </div>

        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-1 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Unidentified / Guests</span>
          <div className="text-2xl font-bold text-rose-400">{unknownCount}</div>
          <span className="text-[11px] text-rose-400/80">Triggered guest Re-ID IDs</span>
        </div>

        <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-1 font-mono">
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">High Risk Detections</span>
          <div className="text-2xl font-bold text-red-400">{highRiskCount}</div>
          <span className="text-[11px] text-red-400/70">Faces explicitly denied by operator</span>
        </div>
      </div>

      <div className="text-[11px] font-mono text-slate-500 px-1">Average face / Re-ID match similarity for stitch events: <span className="text-amber-300 font-bold">{avgConfidence}%</span> · New guest identities have no match score until a prior identity can be compared.</div>

      {/* ── CHARTS ROW ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Hourly Activity Chart (2 cols) */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-mono text-sm font-bold text-slate-100 uppercase tracking-wider">
                Hourly Temporal Detection Activity
              </h3>
              <p className="text-[11px] font-mono text-slate-500">
                Authorized identity sightings vs unregistered guest sightings over time
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="flex items-center gap-1.5 text-cyan-400">
                <span className="w-2.5 h-2.5 rounded bg-cyan-500" /> Authorized
              </span>
              <span className="flex items-center gap-1.5 text-rose-400">
                <span className="w-2.5 h-2.5 rounded bg-rose-500" /> Unknown
              </span>
            </div>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timelineData}>
                <defs>
                  <linearGradient id="colorKnown" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#06B6D4" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorUnknown" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#EF4444" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#EF4444" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
                <XAxis dataKey="hour" stroke="#64748B" fontStyle="mono" fontSize={11} />
                <YAxis stroke="#64748B" fontStyle="mono" fontSize={11} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="authorized" name="Authorized" stroke="#06B6D4" strokeWidth={2} fillOpacity={1} fill="url(#colorKnown)" />
                <Area type="monotone" dataKey="unknown" name="Unknown" stroke="#EF4444" strokeWidth={2} fillOpacity={1} fill="url(#colorUnknown)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Camera Load Chart (1 col) */}
        <div className="p-5 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl space-y-4">
          <div>
            <h3 className="font-mono text-sm font-bold text-slate-100 uppercase tracking-wider">
              Channel Density Matrix
            </h3>
            <p className="text-[11px] font-mono text-slate-500">
              Total spatial sightings distributed by camera
            </p>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cameraData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
                <XAxis dataKey="camera" stroke="#64748B" fontSize={10} />
                <YAxis stroke="#64748B" fontSize={10} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="detections" name="Sightings" fill="#06B6D4" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ── FILTER TOOLBAR ──────────────────────────────────────────────────── */}
      <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search by person name or sighting ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-[#090d12] border border-slate-700/80 text-xs font-mono text-slate-200 placeholder:text-slate-600 outline-none focus:border-cyan-500"
          />
        </div>

        {/* Type & Camera Dropdowns */}
        <div className="flex items-center gap-3">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-2 rounded-xl bg-[#090d12] border border-slate-700/80 text-xs font-mono text-slate-300 outline-none"
          >
            <option value="ALL">All Profile Types</option>
            <option value="KNOWN">Authorized Only</option>
            <option value="HIGH_RISK">High Risk Only</option>
            <option value="UNKNOWN">Unregistered Guests Only</option>
          </select>

          <select
            value={filterCamera}
            onChange={(e) => setFilterCamera(e.target.value)}
            className="px-3 py-2 rounded-xl bg-[#090d12] border border-slate-700/80 text-xs font-mono text-slate-300 outline-none"
          >
            <option value="ALL">All Cameras</option>
            {cameraData.map(c => (
              <option key={c.camera_id || c.camera} value={c.camera_id || c.camera}>
                {c.camera}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── SIGHTINGS LOG TABLE ──────────────────────────────────────────────── */}
      <div className="rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl overflow-hidden">
        <div className="px-5 py-3.5 bg-[#090d12] border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wider">
              Historical Sighting Telemetry Log
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              ({filteredSightings.length} events matching filter)
            </span>
          </div>
        </div>

        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-[#090d12]/60 text-slate-400 uppercase text-[10px] sticky top-0 backdrop-blur-sm z-10 border-b border-slate-800">
              <tr>
                <th className="px-5 py-3">Event Time</th>
                <th className="px-5 py-3">Camera Channel</th>
                <th className="px-5 py-3">Target Identity</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Confidence</th>
                <th className="px-5 py-3">Bounding Box [X1, Y1, X2, Y2]</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredSightings.length > 0 ? (
                filteredSightings.map(s => {
                  const isHighRisk = s.face_review_status === 'denied';
                  const isAuthorized = s.face_review_status === 'confirmed';
                  const isGuest = !isHighRisk && !isAuthorized;
                  return (
                    <tr key={s.id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-5 py-3 text-slate-400">
                        {new Date(s.timestamp > 1e12 ? s.timestamp : s.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </td>
                      <td className="px-5 py-3">
                        <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300 text-[11px]">
                          {s.camera_name || s.camera}
                        </span>
                      </td>
                      <td className="px-5 py-3 font-bold text-slate-100">
                        {s.name}
                      </td>
                      <td className="px-5 py-3">
                        {isHighRisk ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] bg-red-950/60 border border-red-500/50 text-red-300 font-semibold flex items-center gap-1 w-fit">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                            HIGH RISK
                          </span>
                        ) : isAuthorized ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 font-semibold flex items-center gap-1 w-fit">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                            AUTHORIZED
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] bg-rose-950/60 border border-rose-500/40 text-rose-400 font-semibold flex items-center gap-1 w-fit">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                            UNREGISTERED
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-emerald-400 font-bold">
                        {s.confidence != null ? `${(s.confidence * 100).toFixed(0)}%` : 'N/A'}
                      </td>
                      <td className="px-5 py-3 text-slate-500 text-[11px]">
                        [{s.bbox?.join(', ')}]
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-500">
                    No sightings recorded matching selected criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default TrackingPage;
