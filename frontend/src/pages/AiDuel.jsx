import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../auth';
import CodeEditor from '../components/CodeEditor';
import Timer, { useCountdown } from '../components/Timer';
import { DifficultyBadge, RankBadge, StatusPill } from '../components/Badges';

const DIFFICULTIES = [
  { value: 'rank', label: 'My rank' },
  { value: 'easy', label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard', label: 'Hard' },
];

export default function AiDuel() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const topic = params.get('topic');

  const [difficulty, setDifficulty] = useState('rank');
  const [language, setLanguage] = useState('python');
  const [languages, setLanguages] = useState([{ id: 'python', label: 'Python' }]);
  const [starting, setStarting] = useState(false);
  const [session, setSession] = useState(null);   // { problem, plan, scripted, endsAt }
  const [code, setCode] = useState('');
  const [aiState, setAiState] = useState({ state: 'idle' });
  const [runResult, setRunResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState('');
  const timersRef = useRef([]);
  const startedAtRef = useRef(null);

  const locked = user?.plan !== 'paid';

  useEffect(() => {
    api('/api/languages').then((d) => setLanguages(d.languages)).catch(() => {});
  }, []);

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  };
  useEffect(() => clearTimers, []);

  const finish = useCallback((result) => {
    clearTimers();
    setOutcome(result);
  }, []);

  async function start() {
    setError('');
    setStarting(true);
    try {
      const query = new URLSearchParams({ difficulty, language });
      if (topic) query.set('topic', topic);
      const data = await api(`/api/ai/opponent/plan?${query}`, { method: 'POST' });

      const endsAt = new Date(Date.now() + data.time_limit_seconds * 1000).toISOString();
      setSession({ ...data, endsAt });
      setCode(data.problem.starter_code || '');
      startedAtRef.current = Date.now();

      // Replay the opponent's timeline locally. The plan was generated once, up front,
      // so nothing here depends on the network — a blip cannot stall the opponent.
      clearTimers();
      timersRef.current = data.plan.steps.map((step) =>
        setTimeout(() => {
          setAiState(step);
          if (step.state === 'solved') {
            finish({ won: false, reason: 'The AI solved it first.' });
          }
        }, step.at_seconds * 1000),
      );

      // And the clock itself.
      timersRef.current.push(
        setTimeout(
          () => finish({ won: false, reason: 'Time expired.' }),
          data.time_limit_seconds * 1000,
        ),
      );
    } catch (e) {
      setError(e.status === 402 ? 'AI practice requires a Pro subscription.' : e.message);
    } finally {
      setStarting(false);
    }
  }

  async function judge(final) {
    if (!session) return;
    setBusy(true);
    setError('');
    setAiState((s) => s);
    try {
      const outcomeData = await api('/api/ai/practice/run', {
        method: 'POST',
        body: {
          problem_id: session.problem.id,
          code,
          language,
          final,
        },
      });
      setRunResult(outcomeData);

      if (final && outcomeData.verdict === 'accepted') {
        const seconds = Math.round((Date.now() - startedAtRef.current) / 1000);
        const aiSolves = session.plan.solve_seconds || Infinity;
        finish({
          won: true,
          reason:
            seconds < aiSolves
              ? `Solved in ${Math.floor(seconds / 60)}m ${seconds % 60}s — ahead of the AI.`
              : 'Solved it.',
          seconds,
        });
      }
    } catch (e) {
      setError(
        e.status === 429 ? 'Slow down — too many runs.' : e.message || 'Could not run.',
      );
    } finally {
      setBusy(false);
    }
  }

  // ---------------------------------------------------------------- paywall
  if (locked) {
    return (
      <div className="card center-card paywall">
        <span className="lock-icon">🔒</span>
        <h1>AI practice is a Pro feature</h1>
        <p className="muted">
          Practise against an opponent calibrated to your rank — no queue, no waiting, and
          no risk to your rating. Plus post-duel AI review of your solution.
        </p>
        <div className="paywall-rank">
          <span className="micro">Your rank</span>
          <RankBadge rating={user?.rating ?? 1200} size="md" />
        </div>
        <Link className="button-link" to="/upgrade">
          Unlock AI practice — ₹50/mo
        </Link>
        <Link className="muted small-link" to="/duel/queue">
          Or duel a real player →
        </Link>
      </div>
    );
  }

  // ------------------------------------------------------------------ result
  if (outcome) {
    return (
      <div className="card center-card">
        <span className="micro">Practice complete</span>
        <h1 className={`result-headline ${outcome.won ? 'win' : 'loss'}`}>
          {outcome.won ? 'Solved' : 'Not this time'}
        </h1>
        <p className="result-reason">{outcome.reason}</p>
        <p className="muted" style={{ fontSize: 13 }}>
          Practice mode — your rating is unchanged.
        </p>
        <div className="result-actions" style={{ justifyContent: 'center' }}>
          <button
            onClick={() => {
              setOutcome(null);
              setSession(null);
              setRunResult(null);
              setAiState({ state: 'idle' });
            }}
          >
            Practise again
          </button>
          <Link className="button-link" to="/">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------- setup
  if (!session) {
    return (
      <div className="card center-card">
        <span className="micro">AI practice</span>
        <h1>Practice at your rank</h1>

        <div className="paywall-rank">
          <RankBadge rating={user?.rating ?? 1200} size="md" />
          <p className="muted" style={{ fontSize: 13, marginTop: 10 }}>
            Your opponent will be paced like a player around {user?.rating ?? 1200} —
            realistic solve time, and the occasional wrong submission.
          </p>
        </div>

        {topic && (
          <p className="muted">
            Focused on: <strong>{topic}</strong>
          </p>
        )}

        <label className="inline">
          Difficulty
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            {DIFFICULTIES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>

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

        <div className="practice-banner">
          Practice Mode — does not affect your ranked rating.
        </div>

        {error && <p className="error">{error}</p>}
        <button onClick={start} disabled={starting}>
          {starting ? 'Setting up…' : 'Start practice duel'}
        </button>
      </div>
    );
  }

  // -------------------------------------------------------------- live duel
  const { problem } = session;

  return (
    <div className="duel">
      <div className="practice-banner wide">
        Practice Mode — does not affect your ranked rating.
        {session.scripted && ' · Opponent is on a fixed script (AI not configured).'}
      </div>

      <div className="fightcard">
        <div className="fighter you">
          <span className="fighter-label">You</span>
          <span className="fighter-name">{user?.name}</span>
          <span className="fighter-rating">{user?.rating}</span>
        </div>

        <div className="fightcard-center">
          <Timer endsAt={session.endsAt} />
          <div className="problem-chip">
            <DifficultyBadge difficulty={problem.difficulty} />
            <span>{problem.title}</span>
            <span className="ranked-pill">AI Practice</span>
          </div>
        </div>

        <div className="fighter foe">
          <span className="fighter-label">AI opponent</span>
          <span className="fighter-name">DevDuel AI</span>
          <span className="fighter-rating">~{user?.rating}</span>
        </div>
      </div>

      <div className="duel-body">
        <section className="problem-pane">
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
          <CodeEditor value={code} onChange={setCode} language={language} />
          <div className="editor-actions">
            <button className="secondary" onClick={() => judge(false)} disabled={busy}>
              Run samples
            </button>
            <button onClick={() => judge(true)} disabled={busy}>
              {busy ? 'Judging…' : 'Submit'}
            </button>
            {error && <span className="error inline-error">{error}</span>}
            <span className="lang">{language}</span>
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

        <aside className="opponent-panel">
          <h4>AI opponent</h4>
          <StatusPill state={aiState.state} passed={aiState.passed} total={aiState.total} />
          {aiState.total ? (
            <div className="opponent-tests">
              <div className="bar">
                <div
                  className="bar-fill"
                  style={{ width: `${(aiState.passed / aiState.total) * 100}%` }}
                />
              </div>
              <span className="tests-count">
                {aiState.passed}/{aiState.total}
              </span>
              <span className="tests-label">tests passing</span>
            </div>
          ) : null}
          <p className="tests-label" style={{ marginTop: 18 }}>
            Simulated pacing — the AI does not read or run your code.
          </p>
        </aside>
      </div>
    </div>
  );
}
