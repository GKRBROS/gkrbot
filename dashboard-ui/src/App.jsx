import { useEffect, useState } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import api from './api';
import { Loader } from './components/Loader';

// Pages
import Home from './pages/Home';
import AuthCallback from './pages/AuthCallback';
import ServerSelector from './pages/ServerSelector';
import Commands from './pages/Commands';
import DevNews from './pages/DevNews';
import Support from './pages/Support';
import Docs from './pages/Docs';
import Status from './pages/Status';
import Admin from './pages/Admin';
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
import Pinger from './pages/features/Pinger';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // The deck loader fires exactly twice by design:
  //  1) HERE, once, on the very first load/refresh of the site -- any route.
  //     `loading` only starts true and is only ever set back to false; it
  //     never resets on navigation, so this can't re-appear later.
  //  2) Inside ServerSelector (Dashboard) and Admin, which mount fresh (and
  //     so start their own `loading`/`checking` state) every time you
  //     navigate to /dashboard or /admin -- covering Home -> Dashboard and
  //     Dashboard -> Admin without this component needing to know about
  //     routes at all. Every other page has no such mount-time fetch gate,
  //     so navigating between them is always instant.

  useEffect(() => {
    // StrictMode runs this effect twice. Ignore results of the stale run so a
    // failed duplicate request cannot delete the token of a successful one.
    let cancelled = false;

    // The loader's card animation needs real time to actually play — without
    // this, a fast/no-token check (the common case on the Home page) hides it
    // almost instantly and the deck never finishes its first cycle.
    const MIN_LOADER_MS = 3400;
    const started = Date.now();
    const finishLoading = () => {
      const elapsed = Date.now() - started;
      const wait = Math.max(0, MIN_LOADER_MS - elapsed);
      setTimeout(() => { if (!cancelled) setLoading(false); }, wait);
    };

    const fetchUser = async () => {
      const token = localStorage.getItem('bot_dashboard_token');
      if (!token) {
        finishLoading();
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
      finishLoading();
    };
    fetchUser();

    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return <Loader label="Loading..." />;
  }

  return (
    <Routes>
      {/* Public marketing site — always visible, signed in or not */}
      <Route path="/" element={<Home user={user} />} />
      <Route path="/commands" element={<Commands user={user} />} />
      <Route path="/devnews" element={<DevNews user={user} />} />
      <Route path="/support" element={<Support user={user} />} />
      <Route path="/docs" element={<Docs user={user} />} />
      <Route path="/status" element={<Status user={user} />} />
      <Route path="/admin" element={<Admin user={user} />} />
      {/* "admin" typed/linked as if it were a guild id under /dashboard -- send it to the real Admin route */}
      <Route path="/dashboard/admin" element={<Navigate to="/admin" replace />} />
      <Route path="/dashboard/admin/*" element={<Navigate to="/admin" replace />} />

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
        <Route path="pinger" element={<Pinger />} />
      </Route>

      {/* Fallback route for unknown paths */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;