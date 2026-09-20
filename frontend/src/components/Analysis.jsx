import { useEffect, useState } from 'react';
import { api } from '../api';
import { PremiumLock } from './Badges';

const VERDICT_LABEL = {
  accepted: 'Accepted',
  wrong_answer: 'Wrong answer',
  tle: 'Too slow',
  mle: 'Out of memory',
  runtime_error: 'Crashed',
  compile_error: 'Did not compile',
  system_error: 'Judge error',
};

/**
 * Shown after every duel — win, loss or draw.
 *
 * Gating this behind winning (or behind a "Keep solving" click, as it was) had it
 * backwards: the player who just lost is the one who needs to know why.
 */
export default function Analysis({ duelId, locked }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [review, setReview] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const [lang, setLang] = useState('python');

  useEffect(() => {
    api(`/api/duels/${duelId}/analysis`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [duelId]);

  async function runReview() {
    setReviewing(true);
    setReviewError('');
    try {
      const { review: r } = await api(`/api/ai/duels/${duelId}/review`, { method: 'POST' });
      setReview(r);
    } catch (e) {
      setReviewError(
        e.status === 503
          ? 'AI review is not configured on this server.'
          : e.message || 'Review could not be generated.',
      );
    } finally {
      setReviewing(false);
    }
  }

  if (error) return <p className="empty">{error}</p>;
  if (!data) return <p className="empty">Loading analysis…</p>;

  const solutions = data.reference?.solution || {};
  const languages = Object.keys(solutions);
  const shown = solutions[lang] || solutions[languages[0]];

  return (
    <div className="analysis">
      {/* --- what happened ------------------------------------------------ */}
      <h4>Your attempts</h4>
      {data.attempts.length === 0 ? (
        <p className="empty">
          You didn't submit anything. The reference solution is below — worth reading
          even so.
        </p>
      ) : (
        <ul className="attempt-list">
          {data.attempts.map((a, i) => (
            <li key={i} className={`attempt verdict-${a.verdict}`}>
              <span className="attempt-index">#{i + 1}</span>
              <span className="attempt-verdict">{VERDICT_LABEL[a.verdict] || a.verdict}</span>
              <span className="attempt-tests">
                {a.tests_passed}/{a.tests_total}
              </span>
              <span className="attempt-time">{a.runtime_ms ?? '—'}ms</span>
              <span className="attempt-why">{a.explanation}</span>
              {a.stderr && <pre className="stderr">{a.stderr}</pre>}
            </li>
          ))}
        </ul>
      )}

      {/* --- free heuristics ---------------------------------------------- */}
      {data.hints.length > 0 && (
        <>
          <h4>Things worth looking at</h4>
          <ul className="review-list bad">
            {data.hints.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
          <p className="topic-help">
            These are quick pattern checks, not a reading of your logic. The AI review
            below actually analyses the code.
          </p>
        </>
      )}

      {/* --- the answer key ------------------------------------------------ */}
      <h4>Reference solution</h4>
      {languages.length > 1 && (
        <div className="topic-chips" style={{ marginBottom: 10 }}>
          {languages.map((l) => (
            <button
              key={l}
              className={`topic-chip ${lang === l ? 'active' : ''}`}
              onClick={() => setLang(l)}
            >
              {l}
            </button>
          ))}
        </div>
      )}
      {shown ? (
        <pre className="code-reveal">{shown}</pre>
      ) : (
        <p className="empty">No reference solution recorded for this problem.</p>
      )}
      {data.reference?.editorial && <p className="muted">{data.reference.editorial}</p>}

      {/* --- paid: the real review ----------------------------------------- */}
      <h4>AI code review</h4>
      <PremiumLock
        locked={locked}
        title="Unlock AI code review"
        blurb="A reading of your actual solution — complexity, correctness, and what to do instead."
      >
        {review ? (
          <div className="review-body">
            <p className="review-verdict">{review.verdict}</p>
            {review.time_complexity && (
              <p className="muted">
                Yours: <strong>{review.time_complexity}</strong> · Optimal:{' '}
                <strong>{review.optimal_complexity}</strong>
              </p>
            )}
            {review.strengths?.length > 0 && (
              <>
                <h5>What you did well</h5>
                <ul className="review-list good">
                  {review.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </>
            )}
            {review.issues?.length > 0 && (
              <>
                <h5>What to improve</h5>
                <ul className="review-list bad">
                  {review.issues.map((i) => (
                    <li key={i.title}>
                      <strong>{i.title}</strong>
                      <span>{i.detail}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {review.alternative && (
              <>
                <h5>A better approach</h5>
                <pre className="code-reveal">{review.alternative}</pre>
                <p className="muted">{review.alternative_note}</p>
              </>
            )}
          </div>
        ) : (
          <div>
            <button onClick={runReview} disabled={reviewing || data.attempt_count === 0}>
              {reviewing ? 'Reading your solution…' : 'Review my code'}
            </button>
            {data.attempt_count === 0 && (
              <p className="topic-help">Nothing to review — you made no submissions.</p>
            )}
            {reviewError && <p className="error">{reviewError}</p>}
          </div>
        )}
      </PremiumLock>
    </div>
  );
}
