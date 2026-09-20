import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth';
import { RankBadge } from './components/Badges';
import Login from './pages/Login';
import Register from './pages/Register';
import Home from './pages/Home';
import Queue from './pages/Queue';
import Duel from './pages/Duel';
import AiDuel from './pages/AiDuel';
import Analytics from './pages/Analytics';
import Profile from './pages/Profile';
import Leaderboard from './pages/Leaderboard';
import Upgrade from './pages/Upgrade';

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="center">Loading…</div>;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function Header() {
  const { user, logout } = useAuth();
  const isPaid = user?.plan === 'paid';

  return (
    <header className="header">
      <Link to="/" className="brand">
        Dev<span>Duel</span>
      </Link>

      <nav>
        {user && (
          <>
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/analytics">Analytics</NavLink>
            <NavLink to="/profile">Profile</NavLink>
          </>
        )}
        <NavLink to="/leaderboard">Leaderboard</NavLink>

        {user ? (
          <>
            <RankBadge rating={user.rating} />
            {!isPaid && (
              <Link to="/upgrade" className="nav-upgrade">
                Go Pro
              </Link>
            )}
            <button className="link-button" onClick={logout}>
              Sign out
            </button>
          </>
        ) : (
          <Link to="/login" className="nav-upgrade">
            Sign in
          </Link>
        )}
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <div className="app">
      <Header />
      <main>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/upgrade" element={<Upgrade />} />

          <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
          <Route path="/duel/queue" element={<RequireAuth><Queue /></RequireAuth>} />
          <Route path="/duel/ai" element={<RequireAuth><AiDuel /></RequireAuth>} />
          <Route path="/duel/:duelId" element={<RequireAuth><Duel /></RequireAuth>} />
          <Route path="/analytics" element={<RequireAuth><Analytics /></RequireAuth>} />
          <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
