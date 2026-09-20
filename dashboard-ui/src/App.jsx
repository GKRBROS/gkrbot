import { useEffect, useState } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import api from './api';

// Pages
import Landing from './pages/Landing';
import AuthCallback from './pages/AuthCallback';
import ServerSelector from './pages/ServerSelector';
import DashboardLayout from './pages/DashboardLayout';
import Overview from './pages/features/Overview';
import StreamAlerts from './pages/features/StreamAlerts';
import Tickets from './pages/features/Tickets';
import Welcome from './pages/features/Welcome';
import Music from './pages/features/Music';
import Radio from './pages/features/Radio';
import Security from './pages/features/Security';
import Moderation from './pages/features/Moderation';
import StickyMessages from './pages/features/StickyMessages';
import AutoReactions from './pages/features/AutoReactions';
import ServerSync from './pages/features/ServerSync';
import CustomCommands from './pages/features/CustomCommands';
import Economy from './pages/features/Economy';
import TempVC from './pages/features/TempVC';
import Registration from './pages/features/Registration';
import RoleSync from './pages/features/RoleSync';
import AISystem from './pages/features/AISystem';
import VoiceAnnounce from './pages/features/VoiceAnnounce';
import Giveaways from './pages/features/Giveaways';
import Polls from './pages/features/Polls';
import SelfRoles from './pages/features/SelfRoles';
import ServerLogs from './pages/features/ServerLogs';
import Birthdays from './pages/features/Birthdays';
import Leaderboard from './pages/features/Leaderboard';
import Community from './pages/features/Community';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // StrictMode runs this effect twice. Ignore results of the stale run so a
    // failed duplicate request cannot delete the token of a successful one.
    let cancelled = false;

    const fetchUser = async () => {
      const token = localStorage.getItem('bot_dashboard_token');
      if (!token) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const res = await api.get('/users/@me');
        if (!cancelled) setUser(res.data.user);
      } catch (err) {
        if (cancelled) return;
        console.error('Session check failed', err.response?.status, err.response?.data || err.message);
        // Drop the token only when the server rejects it. Network errors and
        // 5xx must not log the user out.
        const status = err.response?.status;
        if (status === 400 || status === 401 || status === 403) {
          localStorage.removeItem('bot_dashboard_token');
        }
      }
      if (!cancelled) setLoading(false);
    };
    fetchUser();

    return () => { cancelled = true; };
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
        {/* Default route inside a guild dashboard defaults to Overview */}
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<Overview />} />
        <Route path="welcome" element={<Welcome />} />
        <Route path="stream-alerts" element={<StreamAlerts />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="registration" element={<Registration />} />
        <Route path="security" element={<Security />} />
        <Route path="moderation" element={<Moderation />} />
        <Route path="sticky" element={<StickyMessages />} />
        <Route path="auto-reactions" element={<AutoReactions />} />
        <Route path="custom-commands" element={<CustomCommands />} />
        <Route path="temp-vc" element={<TempVC />} />
        <Route path="music" element={<Music />} />
        <Route path="radio" element={<Radio />} />
        <Route path="economy" element={<Economy />} />
        <Route path="giveaways" element={<Giveaways />} />
        <Route path="polls" element={<Polls />} />
        <Route path="self-roles" element={<SelfRoles />} />
        <Route path="server-logs" element={<ServerLogs />} />
        <Route path="birthdays" element={<Birthdays />} />
        <Route path="leaderboard" element={<Leaderboard />} />
        <Route path="community" element={<Community />} />
        <Route path="ai" element={<AISystem />} />
        <Route path="voice-announce" element={<VoiceAnnounce />} />
        <Route path="role-sync" element={<RoleSync />} />
        <Route path="sync" element={<ServerSync />} />
      </Route>

      {/* Fallback route for unknown paths */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;