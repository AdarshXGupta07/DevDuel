import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import { connectSocket } from '../socket';
import { RankBadge } from '../components/Badges';

const ACTIVE_DUEL_KEY = 'devduel.activeDuel';

export default function Queue() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [mode, setMode] = useState(params.get('mode') || 'casual');
  const [language, setLanguage] = useState('python');
  const [languages, setLanguages] = useState([{ id: 'python', label: 'Python' }]);
  const [topics, setTopics] = useState([]);
  const [chosenTopics, setChosenTopics] = useState([]);
  const [blocked, setBlocked] = useState(null);

  // Tick the cooldown down so the player can watch it expire rather than guessing when
  // to retry. Clears itself at zero.
  useEffect(() => {
    if (!blocked?.seconds_remaining) return undefined;
    const id = setInterval(() => {
      setBlocked((b) => {
        if (!b) return null;
        const left = b.seconds_remaining - 1;
        return left <= 0 ? null : { ...b, seconds_remaining: left };
      });
    }, 1000);
    return () => clearInterval(id);
  }, [blocked?.blocked_until]);
  const [quota, setQuota] = useState(null);
  const [searching, setSearching] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [found, setFound] = useState(null);
  const [notice, setNotice] = useState('');
  const socketRef = useRef(null);

  useEffect(() => {
    api('/api/duels/me/quota')
      .then((q) => {
        setQuota(q);
        if (q.conduct?.blocked) setBlocked(q.conduct);
      })
      .catch(() => {});
    // The language list comes from the judge, not a hardcoded array — the selector can
    // then never offer something the sandbox has no image for.
    api('/api/languages')
      .then((d) => setLanguages(d.languages))
      .catch(() => {});
    // Topics come from the problem bank, so the picker can never offer one that would
    // always fall back to something else.
    api('/api/topics')
      .then((d) => setTopics(d.topics))
      .catch(() => {});
  }, []);

  // Elapsed counter. Restarted whenever a search begins so it always reads true.
  useEffect(() => {
    if (!searching) return undefined;
    setElapsed(0);
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500);
    return () => clearInterval(id);
  }, [searching]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const socket = await connectSocket();
      if (cancelled) return;
      socketRef.current = socket;

      const handlers = {
        'matchmaking:queued': () => setSearching(true),
        'matchmaking:cancelled': () => setSearching(false),
        'matchmaking:limit_reached': (data) => {
          setSearching(false);
          setNotice(data.message);
        },
        'matchmaking:blocked': (data) => {
          setSearching(false);
          setBlocked(data);
        },
        'matchmaking:error': (data) => {
          setSearching(false);
          if (data.reason === 'no_problems') setNotice('No problems are configured yet.');
          if (data.reason === 'already_queued') setNotice('You are already in a queue.');
        },
        'matchmaking:found': (data) => {
          localStorage.setItem(ACTIVE_DUEL_KEY, data.duel_id);
          const opponent = data.players?.find((p) => p.user_id !== user?.id);
          // A beat on "Opponent found" before the duel — going straight in gives the
          // player no chance to register who they are about to face.
          setFound({ duelId: data.duel_id, rating: opponent?.rating ?? 1200 });
          setTimeout(() => navigate(`/duel/${data.duel_id}`), 1800);
        },
      };

      Object.entries(handlers).forEach(([event, fn]) => socket.on(event, fn));
    })();

    return () => {
      cancelled = true;
      const socket = socketRef.current;
      if (!socket) return;
      [
        'matchmaking:queued',
        'matchmaking:cancelled',
        'matchmaking:limit_reached',
        'matchmaking:blocked',
        'matchmaking:error',
        'matchmaking:found',
      ].forEach((e) => socket.off(e));
    };
  }, [navigate, user?.id]);

  const start = useCallback(async () => {
    setNotice('');
    (await connectSocket()).emit('matchmaking:find', {
      mode,
      language,
      topics: chosenTopics,
    });
  }, [mode, language, chosenTopics]);

  const toggleTopic = (topic) =>
    setChosenTopics((current) =>
      current.includes(topic) ? current.filter((t) => t !== topic) : [...current, topic],
    );

  const cancel = useCallback(async () => {
    (await connectSocket()).emit('matchmaking:cancel');
    setSearching(false);
  }, []);

  // Leaving the page must leave the queue, or the player is matched into a duel they
  // are no longer looking at — and then forfeits it.
  useEffect(() => {
    return () => {
      socketRef.current?.emit('matchmaking:cancel');
    };
  }, []);

  const unlimited = quota?.unlimited;
  const remaining = quota?.ranked_remaining ?? 0;
  const rankedBlocked = mode === 'ranked' && !unlimited && remaining === 0;

  if (found) {
    return (
      <div className="card center-card found-card">
        <span className="micro">Opponent found</span>
        <div className="found-versus">
          <div className="found-side you">
            <span className="micro">You</span>
            <strong>{user?.name}</strong>
            <RankBadge rating={user?.rating ?? 1200} />
          </div>
          <span className="versus-vs">VS</span>
          <div className="found-side foe">
            <span className="micro">Opponent</span>
            <strong>Anonymous</strong>
            <RankBadge rating={found.rating} />
          </div>
        </div>
        <p className="muted">Entering duel…</p>
      </div>
    );
  }

  return (
    <div className="card center-card queue-card">
      <span className="micro">Matchmaking</span>

      {searching ? (
        <>
          <div className="searching">
            <span className="radar" />
            <h1>Searching for an opponent</h1>
            <span className="elapsed">
              {String(Math.floor(elapsed / 60)).padStart(2, '0')}:
              {String(elapsed % 60).padStart(2, '0')}
            </span>
            <p className="muted">
              {mode === 'ranked'
                ? 'Matching by rating — the search widens the longer you wait.'
                : 'Casual match — anyone available.'}
            </p>
          </div>
          <button className="secondary" onClick={cancel}>
            Cancel
          </button>
        </>
      ) : blocked ? (
        <div className="cooldown">
          <span className="cooldown-icon">⏳</span>
          <h1>Matchmaking paused</h1>
          <span className="cooldown-clock">
            {String(Math.floor(blocked.seconds_remaining / 60)).padStart(2, '0')}:
            {String(blocked.seconds_remaining % 60).padStart(2, '0')}
          </span>
          <p className="muted">
            You left {blocked.abandons_today} duels today. Finishing your matches — even
            losing them — keeps this from happening.
          </p>
          <p className="topic-help">
            Your opponents waited for those duels. The pause gets longer each time.
          </p>
        </div>
      ) : (
        <>
          <h1>Find a duel</h1>

          {quota?.conduct?.abandons_today > 0 && (
            <p className="conduct-warning">
              You've left {quota.conduct.abandons_today} duel
              {quota.conduct.abandons_today === 1 ? '' : 's'} today.{' '}
              {quota.conduct.remaining_before_block === 1
                ? 'One more pauses matchmaking for 15 minutes.'
                : `${quota.conduct.remaining_before_block} more pauses matchmaking.`}
            </p>
          )}

          <div className="mode-toggle">
            <button
              className={`toggle ${mode === 'casual' ? 'active' : ''}`}
              onClick={() => setMode('casual')}
            >
              Casual
              <span className="toggle-sub">Unlimited · no rating</span>
            </button>
            <button
              className={`toggle ranked ${mode === 'ranked' ? 'active' : ''}`}
              onClick={() => setMode('ranked')}
            >
              Ranked
              <span className="toggle-sub">
                {unlimited ? 'Unlimited' : `${remaining} of 2 left today`}
              </span>
            </button>
          </div>

          <label className="inline">
            Language
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              {languages.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>

          {topics.length > 0 && (
            <div className="topic-picker">
              <span className="micro">Topics (optional)</span>
              <div className="topic-chips">
                {topics.map((t) => (
                  <button
                    key={t}
                    className={`topic-chip ${chosenTopics.includes(t) ? 'active' : ''}`}
                    onClick={() => toggleTopic(t)}
                  >
                    {t.replace(/-/g, ' ')}
                  </button>
                ))}
              </div>
              <p className="topic-help">
                {chosenTopics.length === 0
                  ? 'No preference — any problem.'
                  : 'If your opponent picked any of the same, the problem comes from there. ' +
                    'If not, it comes from what you both asked for between you.'}
              </p>
            </div>
          )}

          {rankedBlocked ? (
            <div className="notice">
              <p style={{ margin: '0 0 12px' }}>
                You've used today's free ranked matches. Casual stays unlimited.
              </p>
              <a className="button-link" href="/upgrade">
                Unlock unlimited ranked — ₹50/mo
              </a>
            </div>
          ) : (
            <button onClick={start}>Enter queue</button>
          )}

          {notice && <div className="notice">{notice}</div>}
        </>
      )}
    </div>
  );
}
