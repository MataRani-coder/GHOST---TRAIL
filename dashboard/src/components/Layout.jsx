import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Camera, Database, Activity, AlertTriangle, Settings as SettingsIcon,
  Volume2, VolumeX, Search, Bell, UserPlus, X, Menu, ArrowUpRight
} from 'lucide-react';
import wsService from '../services/websocket';
import apiService from '../services/api';
import soundManager from '../services/audioAlert';
import CommandPalette from './CommandPalette';
import WebcamEnrollModal from './WebcamEnrollModal';

const LiveClock = () => {
  const [time, setTime] = useState('');
  useEffect(() => {
    const update = () => {
      const d = new Date();
      const pad = n => String(n).padStart(2, '0');
      setTime(`${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`);
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="top-clock"><span className="top-clock-dot" /> {time}</span>;
};

export const Layout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting');
  const [liveCount, setLiveCount] = useState(3);
  const [fps, setFps] = useState(29.4);
  const [isMuted, setIsMuted] = useState(soundManager.isMuted());
  const [emergencyBanner, setEmergencyBanner] = useState(null);
  const [isCommandOpen, setIsCommandOpen] = useState(false);
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);
  const [enrollInitialBlob, setEnrollInitialBlob] = useState(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const notifRef = useRef(null);

  useEffect(() => {
    const handleOutside = e => {
      if (notifRef.current && !notifRef.current.contains(e.target)) setShowNotifications(false);
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  useEffect(() => {
    apiService.getAlerts().then(data => setActiveAlerts((data || []).filter(a => a.status === 'active')));
    apiService.getCameras().then(data => setLiveCount((data || []).filter(c => c.enabled).length));

    const handleAlert = newAlert => {
      setActiveAlerts(prev => {
        const id = newAlert.id || `${newAlert.timestamp}-${newAlert.camera_id}`;
        if (prev.some(a => a.id === id)) return prev;
        return [newAlert, ...prev];
      });
      setEmergencyBanner(newAlert);
      setTimeout(() => setEmergencyBanner(null), 5000);
    };
    const handleConn = e => setWsStatus(e.status);
    const handleTelemetry = t => {
      if (t.fps) setFps(t.fps);
      if (t.active_cameras !== undefined) setLiveCount(t.active_cameras);
    };
    wsService.on('alert', handleAlert);
    wsService.on('connection_change', handleConn);
    wsService.on('telemetry', handleTelemetry);
    wsService.connect();
    return () => {
      wsService.off('alert', handleAlert);
      wsService.off('connection_change', handleConn);
      wsService.off('telemetry', handleTelemetry);
    };
  }, []);

  const toggleSound = () => {
    const nextMuted = soundManager.toggleMute();
    setIsMuted(nextMuted);
    if (!nextMuted) soundManager.playPing();
  };

  const dismissAlert = async id => {
    await apiService.dismissAlert(id);
    setActiveAlerts(prev => prev.filter(a => a.id !== id));
  };

  const navItems = [
    { label: 'Product', path: '/dashboard', icon: Camera },
    { label: 'Tracking', path: '/tracking', icon: Activity },
    { label: 'Alerts', path: '/alerts', icon: AlertTriangle, badge: activeAlerts.length || null },
    { label: 'People', path: '/persons', icon: Database },
    { label: 'Environment', path: '/map', icon: Camera },
    { label: 'Settings', path: '/settings', icon: SettingsIcon },
  ];

  return (
    <div className="sentinel-shell min-h-screen w-full select-none">
      <header className="sentinel-topnav">
        <Link to="/dashboard" className="sentinel-logo">Ghost <span>Trail</span></Link>

        <nav className={`sentinel-nav ${mobileMenu ? 'open' : ''}`}>
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || (item.path === '/dashboard' && location.pathname === '/');
            return (
              <Link key={item.path} to={item.path} onClick={() => setMobileMenu(false)} className={`sentinel-toplink ${isActive ? 'active' : ''}`}>
                <Icon size={14} />
                <span>{item.label}</span>
                {item.badge ? <b>{item.badge}</b> : null}
              </Link>
            );
          })}
        </nav>

        <div className="sentinel-top-actions">
          <button className="top-action-search" onClick={() => setIsCommandOpen(true)} title="Search">
            <Search size={16} /><span>Search</span><kbd>⌘K</kbd>
          </button>
          <LiveClock />
          <button className="top-icon-btn" onClick={toggleSound} title={isMuted ? 'Unmute' : 'Mute'}>
            {isMuted ? <VolumeX size={17} /> : <Volume2 size={17} />}
          </button>
          <div className="notification-wrap" ref={notifRef}>
            <button className={`top-icon-btn ${activeAlerts.length ? 'has-alert' : ''}`} onClick={() => setShowNotifications(!showNotifications)} title="Alerts">
              <Bell size={17} />
              {activeAlerts.length > 0 && <span className="notification-count">{activeAlerts.length}</span>}
            </button>
            {showNotifications && (
              <div className="notification-popover">
                <div className="popover-head"><strong>Recent alerts</strong><Link to="/alerts" onClick={() => setShowNotifications(false)}>View all</Link></div>
                <div className="popover-list">
                  {activeAlerts.length ? activeAlerts.slice(0, 5).map(alert => (
                    <div className="popover-item" key={alert.id || alert.timestamp}>
                      <div><span className="alert-dot" /> <strong>{alert.camera_id || 'Camera'}</strong></div>
                      <p>{alert.message}</p>
                      <button onClick={() => dismissAlert(alert.id)}><X size={12} /></button>
                    </div>
                  )) : <div className="popover-empty">No active alerts.</div>}
                </div>
              </div>
            )}
          </div>
          <button className="yellow-button compact" onClick={() => { setEnrollInitialBlob(null); setIsEnrollOpen(true); }}>
            <UserPlus size={15} /> Add person
          </button>
          <button className="mobile-menu-btn" onClick={() => setMobileMenu(v => !v)}><Menu size={21} /></button>
        </div>
      </header>

      {emergencyBanner && (
        <div className="emergency-strip">
          <span><b>LIVE ALERT</b> {emergencyBanner.camera_id?.toUpperCase() || 'CHANNEL'} — {emergencyBanner.message}</span>
          <button onClick={() => navigate('/alerts')}>Inspect <ArrowUpRight size={14} /></button>
          <button className="close-strip" onClick={() => setEmergencyBanner(null)}><X size={14} /></button>
        </div>
      )}

      <main className="sentinel-main">{children}</main>

      <CommandPalette isOpen={isCommandOpen} onClose={() => setIsCommandOpen(false)} onOpenEnroll={() => { setEnrollInitialBlob(null); setIsEnrollOpen(true); }} />
      {isEnrollOpen && <WebcamEnrollModal initialImageBlob={enrollInitialBlob} onClose={() => setIsEnrollOpen(false)} onSuccess={() => setIsEnrollOpen(false)} />}
    </div>
  );
};

export default Layout;
