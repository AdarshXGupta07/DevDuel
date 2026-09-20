import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import { DifficultyBadge, RankProgress } from '../components/Badges';
import { mockGlobalPosition, mockStreak } from '../mock';

const PAGE = 10;

export default function Profile() {
  const { user } = useAuth();
  const [history, setHistory] = useState([]);
  const [shown, setShown] = useState(PAGE);
  const [top, setTop] = useState([]);

  useEffect(() => {
    api('/api/duels/me/history?limit=100').then(setHistory).catch(() => {});
    api('/api/leaderboard?limit=5').then(setTop).catch(() => {});
  }, []);

  const stats = useMemo(() => {
    const wins = history.filter((d) => d.result === 'win').length;
    const losses = history.filter((d) => d.result === 'loss').length;
    const decided = wins + losses;
    return {
      total: history.length,
      wins,
      losses,
      winRate: decided ? Math.round((wins / decided) * 100) : null,
    };
  }, [history]);

  if (!user) return null;
  const isPaid = user.plan === 'paid';

  return (
    <div className="profile">
      <section className="card profile-head">
        <div className="avatar" aria-hidden="true">
          {user.name.slice(0, 1).toUpperCase()}
        </div>
        <div className="profile-identity">
          <h1>{user.name}</h1>
          <p className="muted">{user.email}</p>
          <span className={`plan-chip plan-${user.plan}`}>
            {isPaid ? 'Pro' : 'Free plan'}
          </span>
          {!isPaid && (
            <Link to="/upgrade" className="button-link small">
              Upgrade — ₹50/mo
            </Link>
          )}
        </div>
        <RankProgress rating={user.rating} />
      </section>

      <section className="stats-row card">
        <div className="stat">
          <span className="micro">Matches</span>
          <span className="stat-value">{stats.total}</span>
        </div>
        <div className="stat">
          <span className="micro">Win rate</span>
          <span className="stat-value">
            {stats.winRate === null ? '—' : `${stats.winRate}%`}
          </span>
          <span className="stat-note">
            {stats.wins}W · {stats.losses}L
          </span>
        </div>
        <div className="stat">
          <span className="micro">Streak</span>
          <span className="stat-value">{mockStreak.current}</span>
          <span className="stat-note">best {mockStreak.best}</span>
        </div>
        <div className="stat">
          <span className="micro">Global</span>
          {/* Mock: computing a true global position needs a ranked-count query the API
              does not expose yet. Shown here so the layout is real. */}
          <span className="stat-value">#{mockGlobalPosition.rank.toLocaleString()}</span>
          <span className="stat-note">
            of {mockGlobalPosition.totalPlayers.toLocaleString()}
          </span>
        </div>
        <div className="stat">
          <span className="micro">Ranked played</span>
          <span className="stat-value">{user.ranked_matches_played}</span>
          <span className="stat-note">
            {user.ranked_matches_played < 20
              ? `${20 - user.ranked_matches_played} to calibrate`
              : 'calibrated'}
          </span>
        </div>
      </section>

      <div className="profile-columns">
        <section className="card">
          <h4 style={{ marginTop: 0 }}>Match history</h4>
          {history.length === 0 ? (
            <p className="empty">No duels yet.</p>
          ) : (
            <>
              <table className="history">
                <tbody>
                  {history.slice(0, shown).map((d) => (
                    <tr key={d.id}>
                      <td className={`result ${d.result}`}>{d.result}</td>
                      <td className="opp">{d.opponent.name}</td>
                      <td className="meta">{d.mode}</td>
                      <td className="meta">{d.end_reason}</td>
                      <td className="meta">
                        {d.finished_at ? new Date(d.finished_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {shown < history.length && (
                <button className="secondary" onClick={() => setShown((s) => s + PAGE)}>
                  Load more
                </button>
              )}
            </>
          )}
        </section>

        <section className="card">
          <h4 style={{ marginTop: 0 }}>Top players</h4>
          <table className="leaderboard compact">
            <tbody>
              {top.map((r) => (
                <tr key={r.id} className={r.id === user.id ? 'is-you' : ''}>
                  <td className="rank">{String(r.rank).padStart(2, '0')}</td>
                  <td className="player">{r.name}</td>
                  <td className="rating">{r.rating}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Link to="/leaderboard" className="button-link small">
            Full leaderboard
          </Link>
        </section>
      </div>
    </div>
  );
}
