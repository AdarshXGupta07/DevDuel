import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../auth';
import { RankBadge } from '../components/Badges';
import { TIERS, tierFor } from '../lib/ranks';
import { mockGlobalPosition } from '../mock';

export default function Leaderboard() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [tier, setTier] = useState('all');
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/leaderboard?limit=200')
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);

  const filtered = useMemo(
    () => (tier === 'all' ? rows : rows.filter((r) => tierFor(r.rating).name === tier)),
    [rows, tier],
  );

  const youAreVisible = user && filtered.some((r) => r.id === user.id);

  if (error) return <div className="center error">{error}</div>;

  return (
    <div className="leaderboard-page">
      <header className="page-head">
        <div>
          <h1>Leaderboard</h1>
          <p className="muted">
            One ladder. Free and Pro players compete in the same ranked pool.
          </p>
        </div>
      </header>

      <div className="tier-tabs">
        <button className={`tier-tab ${tier === 'all' ? 'active' : ''}`} onClick={() => setTier('all')}>
          All
        </button>
        {TIERS.map((t) => (
          <button
            key={t.name}
            className={`tier-tab ${tier === t.name ? 'active' : ''}`}
            style={{ '--tier': t.color }}
            onClick={() => setTier(t.name)}
          >
            {t.name}
          </button>
        ))}
      </div>

      <section className="card">
        {filtered.length === 0 ? (
          <p className="empty">No players in this tier yet.</p>
        ) : (
          <table className="leaderboard">
            <thead>
              <tr>
                <th>#</th>
                <th>Player</th>
                <th>Tier</th>
                <th style={{ textAlign: 'right' }}>Rating</th>
                <th style={{ textAlign: 'right' }}>Matches</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className={user && r.id === user.id ? 'is-you' : ''}>
                  <td className="rank">{String(r.rank).padStart(2, '0')}</td>
                  <td className="player">
                    {r.name}
                    {user && r.id === user.id && <span className="you-tag">you</span>}
                  </td>
                  <td>
                    <RankBadge rating={r.rating} showRating={false} />
                  </td>
                  <td className="rating">{r.rating}</td>
                  <td className="played">{r.ranked_matches_played}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Pin the player's own position when they're too far down to see themselves —
          scrolling 1,200 rows to find yourself is not a feature. */}
      {user && !youAreVisible && (
        <div className="your-position">
          <span className="micro">Your position</span>
          <strong>#{mockGlobalPosition.rank.toLocaleString()}</strong>
          <span className="player">{user.name}</span>
          <RankBadge rating={user.rating} />
        </div>
      )}
    </div>
  );
}
