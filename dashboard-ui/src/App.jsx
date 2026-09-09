import { useEffect, useState } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import api from './api';

// Pages
import Landing from './pages/Landing';
import AuthCallback from './pages/AuthCallback';
import ServerSelector from './pages/ServerSelector';
import DashboardLayout from './pages/DashboardLayout';
import StreamAlerts from './pages/features/StreamAlerts';
import Tickets from './pages/features/Tickets';
import Welcome from './pages/features/Welcome';
import Music from './pages/features/Music';
import Security from './pages/features/Security';
import Moderation from './pages/features/Moderation';
import StickyMessages from './pages/features/StickyMessages';
import AutoReactions from './pages/features/AutoReactions';
import ServerSync from './pages/features/ServerSync';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUser = async () => {
      const token = localStorage.getItem('bot_dashboard_token');
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const res = await api.get('/users/@me');
        setUser(res.data.user);
      } catch (err) {
        console.error('Session invalid', err);
        localStorage.removeItem('bot_dashboard_token');
      }
      setLoading(false);
    };
    fetchUser();
  }, []);

  if (loading) {
    return <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}>Loading...</div>;
  }

  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to="/dashboard" /> : <Landing />} />
      <Route path="/auth/callback" element={<AuthCallback setUser={setUser} />} />
      
      {/* Protected Routes */}
      <Route path="/dashboard" element={user ? <ServerSelector /> : <Navigate to="/" />} />
      
      <Route path="/dashboard/:guildId" element={user ? <DashboardLayout user={user} /> : <Navigate to="/" />}>
        {/* Default route inside a guild dashboard defaults to Welcome */}
        <Route index element={<Navigate to="welcome" replace />} />
        <Route path="welcome" element={<Welcome />} />
        <Route path="stream-alerts" element={<StreamAlerts />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="security" element={<Security />} />
        <Route path="moderation" element={<Moderation />} />
        <Route path="sticky" element={<StickyMessages />} />
        <Route path="auto-reactions" element={<AutoReactions />} />
        <Route path="music" element={<Music />} />
        <Route path="sync" element={<ServerSync />} />
      </Route>

      {/* Fallback route for unknown paths like /undefined */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
