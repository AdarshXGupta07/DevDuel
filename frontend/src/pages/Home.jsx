import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import { RankBadge } from '../components/Badges';
import { mockGlobalPosition, mockStreak } from '../mock';

const ACTIVE_DUEL_KEY = 'devduel.activeDuel';

export default function Home() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [quota, setQuota] = useState(null);
  const [history, setHistory] = useState([]);
  const [resuming, setResuming] = useState(null);

  useEffect(() => {
    api('/api/duels/me/quota').then(setQuota).catch(() => {});
    api('/api/duels/me/history?limit=50').then(setHistory).catch(() => {});
  }, []);

  // A duel that was live when the tab closed is the most important thing on this
  // screen — offer it before anything else rather than letting it quietly time out.
  useEffect(() => {
    const stored = localStorage.getItem(ACTIVE_DUEL_KEY);
    if (!stored) return;
    api(`/api/duels/${stored}`)
      .then((duel) => {
        if (['pending', 'ready', 'active'].includes(duel.status)) setResuming(duel);
        else localStorage.removeItem(ACTIVE_DUEL_KEY);
      })
      .catch(() => localStorage.removeItem(ACTIVE_DUEL_KEY));
  }, []);

  const isPaid = user?.plan === 'paid';
  const wins = history.filter((d) => d.result === 'win').length;
  const decided = history.filter((d) => d.result !== 'draw').length;
  const winRate = decided ? Math.round((wins / decided) * 100) : null;

  return (
    <div className="home">
      {resuming && (
        <div className="resume-bar">
          <span>
            You have a duel in progress — <strong>{resuming.mode}</strong>
          </span>
          <button onClick={() => navigate(`/duel/${resuming.id}`)}>Rejoin duel</button>
        </div>
      )}

      <section className="hero">
        <h1 className="hero-title">
          Race another developer<br />to solve it first.
        </h1>
        <p className="hero-pitch">
          Same problem. Same clock. One winner. You watch your opponent's progress live —
          never their code.
        </p>

        <div className="hero-actions">
          <button className="cta cta-primary" onClick={() => navigate('/duel/queue')}>
            <span className="cta-title">Duel a Real Player</span>
            <span className="cta-sub">Matched by rating, usually under a minute</span>
          </button>

          <button
            className="cta cta-secondary"
            onClick={() => navigate('/duel/ai')}
          >
            <span className="cta-title">
              Duel with AI
              {!isPaid && <span className="cta-lock">🔒 Pro</span>}
            </span>
            <span className="cta-sub">Practice at your rank. No queue, no rating risk.</span>
          </button>
        </div>
      </section>

      {user ? (
        <section className="stats-strip">
          <div className="stat">
            <span className="micro">Rank</span>
            <RankBadge rating={user.rating} size="md" />
          </div>
          <div className="stat">
            <span className="micro">Win rate</span>
            <span className="stat-value">{winRate === null ? '—' : `${winRate}%`}</span>
            <span className="stat-note">{decided} decided</span>
          </div>
          <div className="stat">
            <span className="micro">Streak</span>
            <span className="stat-value">{mockStreak.current}</span>
            <span className="stat-note">best {mockStreak.best}</span>
          </div>
          <div className="stat">
            <span className="micro">Ranked today</span>
            {quota?.unlimited ? (
              <span className="stat-value accent">∞</span>
            ) : (
              <span className="stat-value">
                {quota ? `${quota.ranked_remaining} of 2` : '—'}
              </span>
            )}
            <span className="stat-note">
              {quota?.unlimited ? 'unlimited' : 'resets at midnight IST'}
            </span>
          </div>
          {!isPaid && (
            <Link to="/upgrade" className="stat-upgrade">
              Unlimited ranked, AI practice and analytics → <strong>₹50/mo</strong>
            </Link>
          )}
        </section>
      ) : (
        <section className="stats-strip signed-out">
          <p>Create a free account to start dueling — two ranked matches a day, forever.</p>
          <Link to="/register" className="button-link">
            Create account
          </Link>
        </section>
      )}
    </div>
  );
}
