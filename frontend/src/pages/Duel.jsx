import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import { connectSocket } from '../socket';
import CodeEditor from '../components/CodeEditor';
import OpponentPanel from '../components/OpponentPanel';
import Timer, { useCountdown } from '../components/Timer';
import { DifficultyBadge, PremiumLock, ResultBanner } from '../components/Badges';
import QuitDialog, { useQuitGuard } from '../components/QuitGuard';
import {
  FullscreenGate,
  ProctorOverlay,
  isFullscreen,
  requestFullscreen,
  useProctor,
} from '../components/Proctor';
import Analysis from '../components/Analysis';

const ACTIVE_DUEL_KEY = 'devduel.activeDuel';

const END_REASONS = {
  solved: 'Solved first.',
  timeout: 'Time expired.',
  forfeit: 'Forfeited.',
  disconnect: 'Opponent disconnected and did not return.',
  draw: 'Time expired and neither player solved it.',
  abandoned: 'The duel was abandoned before it started.',
};

const SOCKET_ERRORS = {
  rate_limited: 'Slow down — too many submissions.',
  duel_not_active: 'This duel is not active.',
  time_expired: 'Time is up.',
  code_too_large: 'That submission is too large.',
  not_a_participant: 'You are not in this duel.',
  not_found: 'Duel not found.',
};

export default function Duel() {
  const { duelId } = useParams();
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();

  const [duel, setDuel] = useState(null);
  const [problem, setProblem] = useState(null);
  // Who the two fighters are. Comes from the REST payload only, so socket updates
  // (which carry duel state, not identities) must never clobber it.
  const [people, setPeople] = useState({ you: null, opponent: null });
  const [code, setCode] = useState('');
  const [opponentStatus, setOpponentStatus] = useState(null);
  const [disconnect, setDisconnect] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [skewMs, setSkewMs] = useState(0);
  const [pane, setPane] = useState('problem');
  const [language, setLanguage] = useState('python');
  const [languages, setLanguages] = useState([]);
  const socketRef = useRef(null);
  const codeRef = useRef('');
  const starterRef = useRef('');

  useEffect(() => {
    api('/api/languages')
      .then((d) => setLanguages(d.languages))
      .catch(() => {});
  }, []);

  useEffect(() => {
    codeRef.current = code;
  }, [code]);

  const applyState = useCallback((payload) => {
    setDuel(payload);
    if (payload.server_time) {
      // Trust the server's clock, not the laptop's.
      setSkewMs(new Date(payload.server_time).getTime() - Date.now());
    }
    if (payload.you || payload.opponent) {
      setPeople((p) => ({ you: payload.you || p.you, opponent: payload.opponent || p.opponent }));
    }
    if (payload.language) setLanguage((l) => (l === 'python' ? payload.language : l));
    if (payload.problem) {
      setProblem(payload.problem);
      starterRef.current = payload.problem.starter_code || '';
      setCode((current) => current || payload.problem.starter_code || '');
    }
    if (payload.status === 'finished' || payload.status === 'abandoned') {
      setResult(payload);
      localStorage.removeItem(ACTIVE_DUEL_KEY);
    }
  }, []);

  // Initial load + resync. This one REST call is the whole recovery story: complete
  // current state, rather than replaying whatever events were missed.
  useEffect(() => {
    let cancelled = false;
    api(`/api/duels/${duelId}`)
      .then((data) => {
        if (cancelled) return;
        applyState(data);
        localStorage.setItem(ACTIVE_DUEL_KEY, duelId);
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [duelId, applyState]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const socket = await connectSocket();
      if (cancelled) return;
      socketRef.current = socket;
      socket.emit('duel:join', { duel_id: duelId });

      const handlers = {
        'duel:state': applyState,
        'duel:start': (p) => {
          applyState(p);
          setResult(null);
        },
        'duel:opponent_status': (p) => {
          if (p.user_id !== user?.id) setOpponentStatus(p);
        },
        'duel:opponent_disconnect': (p) => {
          if (p.user_id !== user?.id) {
            setDisconnect({ secondsLeft: p.grace_seconds, at: Date.now() });
          }
        },
        'duel:opponent_reconnect': () => {
          setDisconnect(null);
          setOpponentStatus({ state: 'reconnected' });
        },
        'duel:run_result': (p) => {
          setRunResult(p);
          setBusy(false);
        },
        'duel:submission_result': (p) => {
          setRunResult(p);
          setBusy(false);
        },
        'duel:end': (p) => {
          setResult(p);
          setDisconnect(null);
          localStorage.removeItem(ACTIVE_DUEL_KEY);
          refreshUser();
        },
        'duel:abandoned': (p) => {
          setResult(p);
          localStorage.removeItem(ACTIVE_DUEL_KEY);
        },
        'duel:error': (p) => {
          setBusy(false);
          setError(SOCKET_ERRORS[p.reason] || 'Something went wrong.');
        },
        'duel:violation_warning': (p) => setViolationNote(p.message),
        'duel:violation_forfeit': () => {
          setViolationNote('');
          if (document.exitFullscreen && isFullscreen()) {
            document.exitFullscreen().catch(() => {});
          }
        },
      };

      Object.entries(handlers).forEach(([event, fn]) => socket.on(event, fn));

      // Re-join and resync after any reconnect. The server puts us back in the room on
      // connect, but the client still needs current truth.
      socket.io.on('reconnect', () => socket.emit('duel:join', { duel_id: duelId }));
    })();

    return () => {
      cancelled = true;
      const socket = socketRef.current;
      if (!socket) return;
      [
        'duel:state', 'duel:start', 'duel:opponent_status', 'duel:opponent_disconnect',
        'duel:opponent_reconnect', 'duel:run_result', 'duel:submission_result',
        'duel:end', 'duel:abandoned', 'duel:error',
        'duel:violation_warning', 'duel:violation_forfeit',
      ].forEach((event) => socket.off(event));
    };
  }, [duelId, user?.id, applyState, refreshUser]);

  // Grace-period countdown shown to the surviving player.
  useEffect(() => {
    if (!disconnect) return undefined;
    const id = setInterval(() => {
      setDisconnect((d) => (d && d.secondsLeft > 1 ? { ...d, secondsLeft: d.secondsLeft - 1 } : d));
    }, 1000);
    return () => clearInterval(id);
  }, [disconnect?.at]);

  const countdown = useCountdown(duel?.starts_at, skewMs);
  const isRanked = duel?.mode === 'ranked';
  const live = duel?.status === 'active' && (countdown === null || countdown === 0);

  const sendEvents = useCallback(
    (events) => socketRef.current?.emit('duel:events', { duel_id: duelId, events }),
    [duelId],
  );

  // "Opponent is typing…" — the live signal the whole product is built around.
  // Throttled to one event per 3s while typing, with an idle event 2.5s after the last
  // keystroke. Emitting per keystroke would be ~5 messages/sec/player for a label that
  // changes twice.
  const lastTypingRef = useRef(0);
  const idleTimerRef = useRef(null);

  const handleCodeChange = useCallback(
    (next) => {
      setCode(next);
      const socket = socketRef.current;
      if (!socket || !live) return;

      const now = Date.now();
      if (now - lastTypingRef.current > 3000) {
        lastTypingRef.current = now;
        socket.emit('duel:status', { duel_id: duelId, state: 'typing' });
      }

      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(() => {
        lastTypingRef.current = 0; // next keystroke re-announces immediately
        socket.emit('duel:status', { duel_id: duelId, state: 'idle' });
      }, 2500);
    },
    [duelId, live],
  );

  useEffect(() => () => clearTimeout(idleTimerRef.current), []);

  // --- quitting ----------------------------------------------------------
  const [conduct, setConduct] = useState(null);

  useEffect(() => {
    // Fetched so the dialog can say "this is your second walkout today" rather than a
    // generic warning. A specific consequence is read; a vague one is clicked through.
    api('/api/duels/me/quota')
      .then((q) => setConduct(q.conduct))
      .catch(() => {});
  }, []);

  const quitDuel = useCallback(() => {
    socketRef.current?.emit('duel:forfeit', { duel_id: duelId });
    localStorage.removeItem(ACTIVE_DUEL_KEY);
    navigate('/');
  }, [duelId, navigate]);

  const guard = useQuitGuard({ active: live, onConfirm: quitDuel });

  // --- proctoring --------------------------------------------------------
  // Whether this duel is proctored is the server's call, not the client's.
  const proctorConfig = duel?.proctor ?? { enabled: false, grace_seconds: 15 };
  const [gateCleared, setGateCleared] = useState(false);
  const [violationNote, setViolationNote] = useState('');
  const proctorActive = proctorConfig.enabled && live && gateCleared;

  const reportViolation = useCallback(
    (kind) => {
      socketRef.current?.emit('duel:violation', { duel_id: duelId, kind, returned: true });
    },
    [duelId],
  );

  const reportExpired = useCallback(
    (kind) => {
      // `returned: false` is what tells the server they never came back — that is the
      // forfeit path rather than the warning path.
      socketRef.current?.emit('duel:violation', { duel_id: duelId, kind, returned: false });
    },
    [duelId],
  );

  const proctor = useProctor({
    active: proctorActive,
    graceSeconds: proctorConfig.grace_seconds,
    onViolation: reportViolation,
    onExpired: reportExpired,
  });

  async function enterDuelFullscreen() {
    await requestFullscreen();
    setGateCleared(true);
  }

  // Leaving the duel should not leave the browser stuck in fullscreen.
  useEffect(() => {
    return () => {
      if (isFullscreen() && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    };
  }, []);

  const emit = (event) => () => {
    setError('');
    if (event !== 'duel:ready') {
      setBusy(true);
      // Tell the opponent something is happening before the judge takes a few seconds.
      socketRef.current?.emit('duel:status', {
        duel_id: duelId,
        state: event === 'duel:run' ? 'running' : 'submitting',
      });
    }
    socketRef.current?.emit(event, {
      duel_id: duelId,
      code: codeRef.current,
      language,
    });
  };

  /**
   * Switching language mid-duel.
   *
   * Each player picks their own — the problem is stdin/stdout, so there is no reason to
   * force both into one. Swapping only replaces the editor contents when the player has
   * not meaningfully written anything yet; silently discarding real work to hand someone
   * a fresh template would be much worse than an unhelpful starter.
   */
  async function switchLanguage(next) {
    setLanguage(next);
    const untouched = !code.trim() || code.trim() === (starterRef.current || '').trim();
    if (!untouched) return;
    try {
      const fresh = await api(`/api/problems/${duel.problem_id}?language=${next}`);
      starterRef.current = fresh.starter_code || '';
      setCode(fresh.starter_code || '');
    } catch {
      /* keep what is on screen; a missing starter is not worth an error banner */
    }
  }

  const youAreReady = useMemo(() => {
    if (!duel || !user) return false;
    return duel.player1_id === user.id ? duel.player1_ready : duel.player2_ready;
  }, [duel, user]);

  if (error && !duel) return <div className="center error">{error}</div>;
  if (!duel || !problem) return <div className="center">Loading duel…</div>;

  if (result) {
    return (
      <ResultScreen
        result={result}
        duelId={duelId}
        navigate={navigate}
        user={user}
        problem={problem}
        yourCode={code}
      />
    );
  }

  // --- ready room ---------------------------------------------------------
  if (duel.status === 'ready' || duel.status === 'pending') {
    return (
      <div className="card center-card ready-room">
        <span className="micro">{isRanked ? 'Ranked duel' : 'Casual duel'}</span>
        <div className="versus">
          <span className="versus-name you">{people.you?.name || 'You'}</span>
          <span className="versus-vs">VS</span>
          <span className="versus-name foe">{people.opponent?.name || 'Opponent'}</span>
        </div>
        <h2>{problem.title}</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          <span className={`difficulty ${problem.difficulty}`}>{problem.difficulty}</span>
          {' · '}
          {Math.round(duel.time_limit_seconds / 60)} minute limit
        </p>
        <div style={{ marginTop: 26 }}>
          <button onClick={emit('duel:ready')} disabled={youAreReady}>
            {youAreReady ? 'Waiting for opponent…' : "I'm ready"}
          </button>
        </div>
      </div>
    );
  }

  // --- live duel ----------------------------------------------------------
  return (
    <div className="duel">
      <QuitDialog
        open={guard.asking}
        mode={duel.mode}
        conduct={conduct}
        onCancel={guard.cancel}
        onConfirm={guard.confirm}
      />

      {/* Fullscreen needs a real click — the browser refuses to enter it otherwise. */}
      {proctorConfig.enabled && live && !gateCleared && (
        <FullscreenGate onEnter={enterDuelFullscreen} />
      )}

      <ProctorOverlay
        away={proctor.away}
        secondsLeft={proctor.secondsLeft}
        graceSeconds={proctorConfig.grace_seconds}
      />

      {violationNote && (
        <div className="violation-banner">
          ⚠ {violationNote}
          <button className="link-button" onClick={() => setViolationNote('')}>
            Dismiss
          </button>
        </div>
      )}

      {countdown > 0 && (
        <div className="countdown-overlay">
          <div className="countdown-number">{countdown}</div>
          <span className="micro">Get ready</span>
        </div>
      )}

      <div className="fightcard">
        <div className="fighter you">
          <span className="fighter-label">You</span>
          <span className="fighter-name">{people.you?.name || user?.name}</span>
          <span className="fighter-rating">{people.you?.rating ?? user?.rating}</span>
        </div>

        <div className="fightcard-center">
          <Timer endsAt={duel.ends_at} skewMs={skewMs} />
          <div className="problem-chip">
            <DifficultyBadge difficulty={problem.difficulty} />
            <span>{problem.title}</span>
            <span className="ranked-pill">{isRanked ? 'Ranked' : 'Casual'}</span>
          </div>
        </div>

        <div className="fighter foe">
          <span className="fighter-label">Opponent</span>
          <span className="fighter-name">{people.opponent?.name || 'Opponent'}</span>
          <span className="fighter-rating">{people.opponent?.rating ?? '—'}</span>
          {live && (
            <button className="quit-button" onClick={guard.requestQuit}>
              Quit match
            </button>
          )}
        </div>
      </div>

      {/* Mobile only (CSS-hidden on desktop): side-by-side panes do not fit a phone,
          so they become tabs rather than a long scroll with the editor below the fold. */}
      <div className="pane-tabs">
        <button
          className={pane === 'problem' ? 'active' : ''}
          onClick={() => setPane('problem')}
        >
          Problem
        </button>
        <button className={pane === 'editor' ? 'active' : ''} onClick={() => setPane('editor')}>
          Code
        </button>
      </div>

      <div className={`duel-body pane-${pane}`}>
        {/* The statement is the real leak path — copying it into an LLM is faster than
            any paste-based cheat. Selection is disabled outright in ranked. */}
        <section
          className={`problem-pane ${isRanked ? 'no-copy' : ''}`}
          onCopy={isRanked ? (e) => e.preventDefault() : undefined}
          onCut={isRanked ? (e) => e.preventDefault() : undefined}
          onContextMenu={isRanked ? (e) => e.preventDefault() : undefined}
        >
          <h4 style={{ marginTop: 0 }}>Problem</h4>
          <p className="statement">{problem.question}</p>

          {problem.constraints && (
            <>
              <h4>Constraints</h4>
              <p className="statement">{problem.constraints}</p>
            </>
          )}

          <h4>Samples</h4>
          {problem.samples.map((s, i) => (
            <div key={i} className="sample">
              <div className="sample-row">
                <span>In</span>
                <pre>{s.input}</pre>
              </div>
              <div className="sample-row">
                <span>Out</span>
                <pre>{s.expected_output}</pre>
              </div>
            </div>
          ))}
        </section>

        <section className="editor-pane">
          <CodeEditor
            value={code}
            onChange={handleCodeChange}
            language={language}
            ranked={isRanked}
            onEvent={sendEvents}
            readOnly={!live}
          />

          <div className="editor-actions">
            <button className="secondary" onClick={emit('duel:run')} disabled={busy || !live}>
              Run samples
            </button>
            <button onClick={emit('duel:submit')} disabled={busy || !live}>
              {busy ? 'Judging…' : 'Submit'}
            </button>
            {error && <span className="error inline-error">{error}</span>}
            {isRanked && (
              <span
                className="paste-lock"
                title="Copy and paste are disabled in ranked matches. Typed code has a rhythm; pasted code doesn't."
              >
                🔒 Copy / paste disabled
              </span>
            )}
            <select
              className="lang-select"
              value={language}
              onChange={(e) => switchLanguage(e.target.value)}
              disabled={!live}
              title="Your language — your opponent picks their own"
            >
              {languages.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          {runResult && (
            <div className={`run-result verdict-${runResult.verdict}`}>
              <span className="verdict">{runResult.verdict.replace(/_/g, ' ')}</span>
              <span className="counts">
                {runResult.tests_passed}/{runResult.tests_total} passing
              </span>
              <span className="counts">{runResult.runtime_ms}ms</span>
              {runResult.stderr && <pre className="stderr">{runResult.stderr}</pre>}
            </div>
          )}
        </section>

        <OpponentPanel status={opponentStatus} disconnect={disconnect} />
      </div>
    </div>
  );
}


function ResultScreen({ result, duelId, navigate, user, problem, yourCode }) {
  const [submissions, setSubmissions] = useState([]);
  // Untimed practice after the duel is decided. The match result and rating are already
  // settled — this is for the player, not the ladder.
  const [practising, setPractising] = useState(false);
  const [practiceCode, setPracticeCode] = useState(yourCode || '');

  useEffect(() => {
    api(`/api/duels/${duelId}/submissions`).then(setSubmissions).catch(() => {});
  }, [duelId]);

  const draw = !result.winner_id;
  const won = result.winner_id === user?.id;
  const outcome = draw ? 'draw' : won ? 'win' : 'loss';
  const rating = result.ratings?.[user?.id];
  const locked = user?.plan !== 'paid';
  const neitherSolved = result.detail?.neither_solved;

  return (
    <div className="card result-screen">
      <span className="micro">
        {result.mode} duel · {result.end_reason}
      </span>

      <ResultBanner
        outcome={outcome}
        reason={END_REASONS[result.end_reason] || result.end_reason}
        delta={rating?.delta}
        ratingAfter={rating?.after}
      />

      {/* A draw nobody solved must not look like a scoring bug. Say why plainly. */}
      {neitherSolved && (
        <p className="draw-note">
          Neither of you solved it, so there's no winner and <strong>no rating change</strong>.
          A problem that beat you both says nothing about which of you is stronger.
        </p>
      )}

      <div className="result-actions">
        <button onClick={() => navigate('/duel/queue')}>Rematch</button>
        <button className="secondary" onClick={() => navigate('/')}>
          Back to home
        </button>
        {!won && !practising && (
          <button className="secondary" onClick={() => setPractising(true)}>
            Keep solving
          </button>
        )}
      </div>

      {practising && (
        <section className="keep-solving">
          <div className="keep-solving-head">
            <h4 style={{ margin: 0 }}>Keep solving — untimed</h4>
            <span className="muted">
              Practice only. The match result and your rating are already settled.
            </span>
          </div>
          <div className="keep-solving-editor">
            <CodeEditor
              value={practiceCode}
              onChange={setPracticeCode}
              language={result.language || 'python'}
            />
          </div>
          <div className="editor-actions">
            <button className="secondary" onClick={() => setPractising(false)}>
              Close
            </button>
          </div>
        </section>
      )}

      {/* Shown for every outcome. The player who lost needs this most. */}
      <section className="analysis-section">
        <Analysis duelId={duelId} locked={locked} />
      </section>

      <h4>Both solutions</h4>
      {submissions.length === 0 ? (
        <p className="empty">No submissions were made.</p>
      ) : (
        <div className="solutions-grid">
          {submissions.map((s) => {
            const mine = s.user_id === user?.id;
            return (
              <div key={s.id} className={`submission ${mine ? 'is-you' : 'is-foe'}`}>
                <header>
                  <strong>{mine ? 'You' : 'Opponent'}</strong>
                  <span className={`verdict-tag verdict-${s.verdict}`}>
                    {s.verdict?.replace(/_/g, ' ')}
                  </span>
                  <span className="spacer">
                    {s.tests_passed}/{s.tests_total} · {s.runtime_ms ?? '—'}ms
                  </span>
                </header>
                <pre className="code-reveal">{s.code}</pre>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
