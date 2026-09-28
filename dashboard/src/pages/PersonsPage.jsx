import React, { useState, useEffect, useMemo } from 'react';
import { 
  Plus, Trash2, Clock, Upload, Check, AlertTriangle, 
  Search, Shield, ShieldCheck, UserCheck, Eye, LayoutGrid, 
  List, Filter, ArrowUpRight, Camera
} from 'lucide-react';
import apiService from '../services/api';
import WebcamEnrollModal from '../components/WebcamEnrollModal';
import PersonDossierModal from '../components/PersonDossierModal';

const EditPersonModal = ({ person, onClose, onSave }) => {
  const [form, setForm] = useState({
    name: person.name || '',
    badge_id: person.badge_id || '',
    role: person.role || '',
    clearance: person.clearance || 'Level 2 (Personnel)',
    profile_note: person.profile_note || '',
  });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg rounded-2xl bg-[#0e141c] border border-slate-700 shadow-2xl p-5 font-mono">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-100 uppercase">Edit Security Profile</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white text-lg">×</button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[["name","Name"],["badge_id","Badge ID"],["role","Role"]].map(([key,label]) => (
            <label key={key} className="text-[10px] text-slate-400 space-y-1">{label}
              <input value={form[key]} onChange={e => setForm({...form,[key]:e.target.value})} className="w-full px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-xs text-slate-200 outline-none focus:border-cyan-500" />
            </label>
          ))}
          <label className="text-[10px] text-slate-400 space-y-1">Clearance
            <select value={form.clearance} onChange={e => setForm({...form,clearance:e.target.value})} className="w-full px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-xs text-slate-200 outline-none">
              <option>Level 1 (Contractor)</option><option>Level 2 (Personnel)</option><option>Level 3 (Security Officer)</option><option>Level 4 (Director / VIP)</option>
            </select>
          </label>
          <label className="col-span-2 text-[10px] text-slate-400 space-y-1">Notes
            <textarea value={form.profile_note} onChange={e => setForm({...form,profile_note:e.target.value})} rows={3} className="w-full px-3 py-2 rounded-lg bg-[#090d12] border border-slate-700 text-xs text-slate-200 outline-none focus:border-cyan-500" />
          </label>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-xs text-slate-300">Cancel</button>
          <button onClick={() => onSave(form)} className="px-3 py-2 rounded-lg bg-cyan-400 text-black font-bold text-xs">Save Changes</button>
        </div>
      </div>
    </div>
  );
};

export const PersonsPage = () => {
  const [persons, setPersons] = useState([]);
  const [sightings, setSightings] = useState([]);
  const [flagged, setFlagged] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterClearance, setFilterClearance] = useState('ALL');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'table'
  
  // Modals
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [selectedPersonForDossier, setSelectedPersonForDossier] = useState(null);
  const [editingPerson, setEditingPerson] = useState(null);

  const fetchData = async () => {
    try {
      const [registered, logs, flags] = await Promise.all([
        apiService.getRegisteredPersons(),
        apiService.getSightings(),
        apiService.getFlaggedPersons()
      ]);
      setPersons(registered || []);
      setSightings(logs || []);
      setFlagged(flags || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 8000);
    return () => clearInterval(id);
  }, []);

  const handleDelete = async (id, name) => {
    if (window.confirm(`Delete ${name} from the security database and erase face embeddings?`)) {
      await apiService.deletePerson(id);
      fetchData();
    }
  };

  // A flagged capture is a photo pending human review.
  const handleConfirmFlag = async (id) => {
    const result = await apiService.confirmFlaggedPerson(id);
    if (!result?.success) {
      window.alert(result?.error || 'Face acceptance failed.');
      return;
    }
    window.alert('face has been accepted, person has been added to the database');
    fetchData();
  };

  const handleDenyFlag = async (flag) => {
    const confirmed = window.confirm(
      `Deny the face for ${flag.guest_label}? This will categorize this person as High Risk and create a Security Incident.`
    );
    if (!confirmed) return;
    const result = await apiService.denyFlaggedPerson(flag.id);
    if (!result?.success) {
      window.alert(result?.error || 'Face denial failed.');
      return;
    }
    fetchData();
  };

  const handleUnenroll = async (person) => {
    const confirmed = window.confirm(
      `Remove ${person.name} from the enrolled face database? The active face template and profile will be removed.`
    );
    if (!confirmed) return;
    try {
      const result = await apiService.unenrollPerson(person.id);
      if (!result?.success) {
        window.alert(result?.error || 'Could not remove the enrolled face.');
        return;
      }
      await fetchData();
    } catch (err) {
      console.error(err);
      window.alert('Could not remove the enrolled face. Check that the backend is running.');
    }
  };

  const handleSavePerson = async (details) => {
    if (!editingPerson) return;
    try {
      const result = await apiService.updatePersonDetails(editingPerson.id, details);
      if (!result?.success) {
        window.alert(result?.error || 'Could not update profile.');
        return;
      }
      setEditingPerson(null);
      await fetchData();
    } catch (err) {
      console.error(err);
      window.alert('Could not update profile. Check that the backend is running.');
    }
  };

  const handleFaceReview = async (person, decision) => {
    const isDenied = decision === 'denied';
    const confirmed = window.confirm(
      isDenied
        ? `Deny the face for ${person.name}? This will mark the profile High Risk and create a security incident.`
        : `Confirm the face for ${person.name} as verified?`
    );
    if (!confirmed) return;

    try {
      const result = await apiService.reviewPersonFace(person.id, decision);
      if (!result?.success) {
        window.alert(result?.error || 'Face review failed.');
        return;
      }
      fetchData();
    } catch (err) {
      console.error(err);
      window.alert('Face review failed. Check that the backend is running.');
    }
  };

  // Filter persons
  const pendingFlags = useMemo(() => (flagged || []).filter(f => String(f.status || 'pending_review') === 'pending_review'), [flagged]);

  const filteredPersons = useMemo(() => {
    return persons.filter(p => {
      const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.clearance && p.clearance.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesClearance = filterClearance === 'ALL' || (p.clearance && p.clearance.includes(filterClearance));
      return matchesSearch && matchesClearance;
    });
  }, [persons, searchQuery, filterClearance]);

  const reviewBadge = (status) => {
    if (status === 'confirmed') {
      return { label: 'FACE VERIFIED', className: 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40' };
    }
    if (status === 'denied') {
      return { label: 'FACE DENIED • HIGH RISK', className: 'bg-red-950/80 text-red-300 border-red-500/50' };
    }
    return { label: 'FACE REVIEW PENDING', className: 'bg-amber-950/80 text-amber-300 border-amber-500/40' };
  };

  return (
    <div className="space-y-6">
      
      {/* ── HEADER ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono tracking-widest bg-cyan-950 text-cyan-400 border border-cyan-500/40 uppercase">
              BIOMETRIC IDENTITY REPOSITORY
            </span>
            <span className="text-xs font-mono text-slate-500">
              {persons.length} Enrolled Profiles
            </span>
          </div>
          <h2 className="text-2xl font-mono font-bold tracking-tight text-slate-100 uppercase">
            Enrolled Security Profiles
          </h2>
          <p className="text-xs font-mono text-slate-400">
            Facial recognition templates and DeepReID feature gallery for automated access control
          </p>
        </div>

        {/* Enroll Button */}
        <button
          onClick={() => setShowEnrollModal(true)}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cyan-400 hover:bg-cyan-300 text-black font-mono text-xs font-bold transition-all shadow-[0_0_20px_rgba(6,182,212,0.25)] hover:shadow-[0_0_30px_rgba(6,182,212,0.4)]"
        >
          <Plus size={16} />
          <span>Enroll New Profile</span>
        </button>
      </div>

      {/* ── FILTER & SEARCH TOOLBAR ─────────────────────────────────────────── */}
      <div className="p-4 rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search enrolled profile by name, badge, clearance..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 rounded-xl bg-[#090d12] border border-slate-700/80 focus:border-cyan-500 text-xs font-mono text-slate-200 placeholder:text-slate-600 outline-none transition-colors"
          />
        </div>

        {/* Filters & View Toggle */}
        <div className="flex items-center gap-3">
          <select
            value={filterClearance}
            onChange={(e) => setFilterClearance(e.target.value)}
            className="px-3 py-2 rounded-xl bg-[#090d12] border border-slate-700/80 text-xs font-mono text-slate-300 outline-none cursor-pointer"
          >
            <option value="ALL">All Clearance Levels</option>
            <option value="Level 4">Level 4 (Director / VIP)</option>
            <option value="Level 3">Level 3 (Security Officer)</option>
            <option value="Level 2">Level 2 (Personnel)</option>
            <option value="Level 1">Level 1 (Contractor)</option>
          </select>

          {/* View toggle */}
          <div className="flex bg-[#090d12] border border-slate-800 rounded-xl p-1">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-1.5 rounded-lg text-xs transition-colors ${
                viewMode === 'grid' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              <LayoutGrid size={15} />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 rounded-lg text-xs transition-colors ${
                viewMode === 'table' ? 'bg-cyan-500 text-black font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              <List size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* ── FLAGGED FOR REVIEW ────────────────────────────────────────────────
          Photos captured because a track's behavior crossed the Suspicious /
          High-Risk line. These are NOT confirmed identities — a human has to
          look at each photo and either Confirm Face or Deny Face. */}
      {pendingFlags.length > 0 && (
        <div className="p-4 rounded-2xl bg-[#1a1006] border border-amber-500/30 shadow-xl space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-400" />
            <h3 className="text-sm font-mono font-bold tracking-wide text-amber-300 uppercase">
              Flagged for Review
            </h3>
            <span className="text-xs font-mono text-amber-500/70">
              {pendingFlags.length} pending — not yet confirmed
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {pendingFlags.map((f) => (
              <div key={f.id} className="rounded-xl bg-[#0e141c] border border-amber-500/20 overflow-hidden">
                <img
                  src={f.thumbnail}
                  alt={f.guest_label}
                  className="w-full h-28 object-cover"
                  onError={(e) => { e.target.src = '/assets/placeholder.jpg'; }}
                />
                <div className="p-2 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-mono text-slate-200 truncate">{f.guest_label}</span>
                    <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase ${
                      f.risk_tier === 'high_risk' ? 'bg-red-950 text-red-400 border border-red-500/40'
                        : 'bg-amber-950 text-amber-400 border border-amber-500/40'
                    }`}>
                      {f.risk_tier === 'high_risk' ? 'High Risk' : 'Suspicious'}
                    </span>
                  </div>
                  <p className="text-[10px] font-mono text-slate-500 truncate" title={f.reason}>
                    {f.camera_id} — {f.reason}
                  </p>
                  <div className="flex gap-1.5 pt-1">
                    <button
                      onClick={() => handleConfirmFlag(f.id)}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded-lg bg-emerald-500/90 hover:bg-emerald-400 text-black text-[10px] font-mono font-bold"
                    >
                      <ShieldCheck size={11} /> Confirm Face
                    </button>
                    <button
                      onClick={() => handleDenyFlag(f)}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded-lg bg-red-500/90 hover:bg-red-400 text-black text-[10px] font-mono font-bold"
                    >
                      <AlertTriangle size={11} /> Deny Face
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── PROFILE LISTINGS ─────────────────────────────────────────────────── */}
      {viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
          {filteredPersons.map(person => (
            <div
              key={person.id}
              className="group relative rounded-2xl bg-[#0e141c] border border-slate-800 hover:border-cyan-500/50 shadow-xl overflow-hidden flex flex-col justify-between transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_0_30px_rgba(6,182,212,0.15)]"
            >
              {/* Photo Area */}
              <div 
                onClick={() => setSelectedPersonForDossier(person)}
                className="relative aspect-square w-full bg-slate-950 overflow-hidden cursor-pointer"
              >
                <img
                  src={person.thumbnail}
                  alt={person.name}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  onError={(e) => {
                    e.target.src = 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200&auto=format&fit=crop&q=80';
                  }}
                />

                {/* Status chip */}
                <div className="absolute top-2.5 left-2.5">
                  {(() => {
                    const badge = reviewBadge(person.face_review_status);
                    return (
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-black/70 backdrop-blur-md border ${badge.className} flex items-center gap-1`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${person.face_review_status === 'denied' ? 'bg-red-400' : person.face_review_status === 'confirmed' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                        {badge.label}
                      </span>
                    );
                  })()}
                </div>

                {/* ID badge */}
                <div className="absolute top-2.5 right-2.5">
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-mono bg-black/70 backdrop-blur-md text-cyan-300 border border-cyan-500/30">
                    #{person.id}
                  </span>
                </div>

                {/* Quick Inspect Hover Overlay */}
                <div className="absolute inset-0 bg-cyan-950/60 backdrop-blur-[2px] opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <span className="px-3 py-1.5 rounded-xl bg-cyan-400 text-black font-mono text-xs font-bold flex items-center gap-1.5 shadow-lg">
                    <Eye size={13} /> View Dossier
                  </span>
                </div>
              </div>

              {/* Card Body */}
              <div className="p-4 space-y-2 font-mono flex-1 flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide truncate">
                    {person.name}
                  </h3>
                  <p className="text-[11px] text-cyan-400 truncate">
                    {person.clearance || 'Level 2 (Personnel)'}
                  </p>
                </div>

                <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500">
                  <span>Last Seen:</span>
                  <span className="text-slate-300 font-semibold">
                    {person.last_seen ? new Date(person.last_seen).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Today'}
                  </span>
                </div>

                {/* Face verification + profile actions */}
                <div className="pt-2 border-t border-slate-800/80 space-y-2">
                  {person.face_review_status === 'pending' ? (
                    <div className="grid grid-cols-2 gap-2">
                      <button onClick={() => handleFaceReview(person, 'confirmed')} className="flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[10px] font-mono font-bold border bg-emerald-950/50 border-emerald-500/40 text-emerald-200 hover:bg-emerald-900/60">
                        <ShieldCheck size={12} /> Confirm Face
                      </button>
                      <button onClick={() => handleFaceReview(person, 'denied')} className="flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[10px] font-mono font-bold border bg-red-950/50 border-red-500/40 text-red-200 hover:bg-red-900/60">
                        <AlertTriangle size={12} /> Deny Face
                      </button>
                    </div>
                  ) : (
                    <div className="text-[10px] font-mono font-bold">
                      <span className={person.face_review_status === 'confirmed' ? 'text-emerald-300' : 'text-red-300'}>
                        {person.face_review_status === 'confirmed' ? 'FACE VERIFIED — AUTHORIZED' : 'FACE DENIED — HIGH RISK'}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <button onClick={() => setEditingPerson(person)} className="text-[10px] text-cyan-300 hover:text-cyan-200 hover:underline">Edit Details</button>
                    {person.face_review_status === 'confirmed' ? (
                      <button onClick={() => handleUnenroll(person)} className="text-[10px] text-rose-400 hover:text-rose-300 hover:underline flex items-center gap-1" title="Remove from enrolled face database">
                        <Trash2 size={11} /> Remove Enrolled
                      </button>
                    ) : <span />}
                    <button onClick={() => setSelectedPersonForDossier(person)} className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1">
                      <span>Timeline</span>
                      <ArrowUpRight size={12} />
                    </button>
                    <button onClick={() => handleDelete(person.id, person.name)} title="Delete Identity" className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Table View */
        <div className="rounded-2xl bg-[#0e141c] border border-slate-800 shadow-xl overflow-hidden">
          <table className="w-full text-left font-mono text-xs">
            <thead className="bg-[#090d12] border-b border-slate-800 text-slate-400 uppercase text-[10px]">
              <tr>
                <th className="px-5 py-3">Profile</th>
                <th className="px-5 py-3">ID Code</th>
                <th className="px-5 py-3">Clearance Role</th>
                <th className="px-5 py-3">Match Confidence</th>
                <th className="px-5 py-3">Last Active</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredPersons.map(person => (
                <tr key={person.id} className="hover:bg-slate-900/50 transition-colors">
                  <td className="px-5 py-3 flex items-center gap-3">
                    <img
                      src={person.thumbnail}
                      alt={person.name}
                      className="w-9 h-9 rounded-lg object-cover border border-slate-700"
                    />
                    <div>
                      <span className="font-bold text-slate-100 block">{person.name}</span>
                      <span className={`text-[10px] ${person.face_review_status === 'denied' ? 'text-red-400' : person.face_review_status === 'confirmed' ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {person.face_review_status === 'denied' ? 'Face Denied • High Risk' : person.face_review_status === 'confirmed' ? 'Face Verified' : 'Face Review Pending'}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-cyan-400">#{person.id}</td>
                  <td className="px-5 py-3 text-slate-300">{person.clearance || 'Level 2 (Personnel)'}</td>
                  <td className="px-5 py-3 text-emerald-400 font-bold">
                    {((person.confidence || 0.92) * 100).toFixed(1)}%
                  </td>
                  <td className="px-5 py-3 text-slate-400">
                    {person.last_seen ? new Date(person.last_seen).toLocaleTimeString() : 'Recent'}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {person.face_review_status === 'pending' ? (
                        <>
                          <button onClick={() => handleFaceReview(person, 'confirmed')} className="px-2.5 py-1 rounded-lg bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-900 text-[10px]">Confirm Face</button>
                          <button onClick={() => handleFaceReview(person, 'denied')} className="px-2.5 py-1 rounded-lg bg-red-950/60 border border-red-500/40 text-red-300 hover:bg-red-900 text-[10px]">Deny Face</button>
                        </>
                      ) : (
                        <span className={`px-2.5 py-1 rounded-lg text-[10px] font-bold ${person.face_review_status === 'confirmed' ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/40' : 'bg-red-950/60 text-red-300 border border-red-500/40'}`}>
                          {person.face_review_status === 'confirmed' ? 'VERIFIED' : 'HIGH RISK'}
                        </span>
                      )}
                      <button onClick={() => setEditingPerson(person)} className="px-2.5 py-1 rounded-lg bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-900 text-[10px]">Edit</button>
                      {person.face_review_status === 'confirmed' && (
                        <button onClick={() => handleUnenroll(person)} className="px-2.5 py-1 rounded-lg bg-rose-950/60 border border-rose-500/40 text-rose-300 hover:bg-rose-900 text-[10px]">Remove Enrolled</button>
                      )}
                      <button
                        onClick={() => setSelectedPersonForDossier(person)}
                        className="px-3 py-1 rounded-lg bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-900 text-[11px]"
                      >
                        Inspect
                      </button>
                      <button
                        onClick={() => handleDelete(person.id, person.name)}
                        className="p-1 rounded-lg text-rose-400 hover:bg-rose-950/40"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty State */}
      {filteredPersons.length === 0 && (
        <div className="py-16 text-center rounded-2xl bg-[#0e141c] border border-slate-800 font-mono space-y-3">
          <Shield size={36} className="mx-auto text-slate-600" />
          <h3 className="text-base text-slate-300 font-bold uppercase">
            No Security Profiles Matched
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Try adjusting search terms or enroll a new identity using the button above.
          </p>
        </div>
      )}

      {/* Modal: Enroll Face */}
      {showEnrollModal && (
        <WebcamEnrollModal
          onClose={() => setShowEnrollModal(false)}
          onSuccess={() => {
            setShowEnrollModal(false);
            fetchData();
          }}
        />
      )}

      {editingPerson && (
        <EditPersonModal person={editingPerson} onClose={() => setEditingPerson(null)} onSave={handleSavePerson} />
      )}

      {/* Modal: Person Dossier */}
      {selectedPersonForDossier && (
        <PersonDossierModal
          person={selectedPersonForDossier}
          sightings={sightings}
          onClose={() => setSelectedPersonForDossier(null)}
          onDelete={(id, name) => {
            handleDelete(id, name);
            setSelectedPersonForDossier(null);
          }}
        />
      )}
    </div>
  );
};

export default PersonsPage;
