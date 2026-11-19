import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { api } from '../lib/api';
import { bus } from '../lib/mqtt';
import { startOutbox } from '../lib/outbox';
import { loadProfile, ProfileContext, saveProfile, useProfile, type Profile } from '../lib/profile';
import { ingest, loadCachedEvents } from '../lib/store';
import { StatusBar } from './StatusBar';
import { RolePage } from '../features/role/RolePage';
import { OverviewPage } from '../features/overview/OverviewPage';
import { MechanicPage } from '../features/mechanic/MechanicPage';
import { OfficerPage } from '../features/officer/OfficerPage';
import { HandoverPage } from '../features/handover/HandoverPage';

/** Wire the transports into the store: cache → server catch-up → live MQTT. */
function useBootstrap(profile: Profile | null) {
  useEffect(() => {
    void loadCachedEvents();
    void startOutbox();
  }, []);

  useEffect(() => {
    const catchUp = () =>
      api
        .loadEvents()
        .then((e) => ingest(e))
        .catch(() => {});
    const offEvent = bus.onEvent((e) => ingest(e));
    const offState = bus.onState((s) => s === 'connected' && void catchUp());
    bus.start(profile);
    return () => {
      offEvent();
      offState();
      bus.stop();
    };
  }, [profile]);
}

function Shell() {
  const { pathname } = useLocation();
  return (
    <div className="min-h-dvh bg-navy text-cream">
      {pathname !== '/role' && <StatusBar />}
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/role" element={<RolePage />} />
        <Route
          path="/mechanic"
          element={
            <Guard>
              <MechanicPage />
            </Guard>
          }
        />
        <Route
          path="/officer"
          element={
            <Guard>
              <OfficerPage />
            </Guard>
          }
        />
        <Route path="/handover" element={<HandoverPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

function Guard({ children }: { children: React.ReactNode }) {
  const { profile } = useProfile();
  const { pathname } = useLocation();
  return profile ? <>{children}</> : <Navigate to={`/role?next=${encodeURIComponent(pathname)}`} replace />;
}

export default function App() {
  const [profile, setProfileState] = useState<Profile | null>(loadProfile);
  const setProfile = useCallback((p: Profile | null) => {
    saveProfile(p);
    setProfileState(p);
  }, []);
  useBootstrap(profile);

  return (
    <ProfileContext.Provider value={{ profile, setProfile }}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </ProfileContext.Provider>
  );
}
