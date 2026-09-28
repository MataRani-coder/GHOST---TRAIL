import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';

// Lazy load pages for optimum performance
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const TacticalMapPage = lazy(() => import('./pages/TacticalMapPage'));
const PersonsPage = lazy(() => import('./pages/PersonsPage'));
const TrackingPage = lazy(() => import('./pages/TrackingPage'));
const AlertsPage = lazy(() => import('./pages/AlertsPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

// High-tech cyber loader
const PageLoader = () => (
  <div className="flex flex-col items-center justify-center h-80 gap-3">
    <div className="relative flex items-center justify-center">
      <div className="w-10 h-10 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
      <div className="absolute w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
    </div>
    <span className="font-mono text-xs text-slate-400 tracking-widest uppercase">
      INITIALIZING CHANNEL TELEMETRY...
    </span>
  </div>
);

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/map" element={<TacticalMapPage />} />
            <Route path="/persons" element={<PersonsPage />} />
            <Route path="/tracking" element={<TrackingPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
