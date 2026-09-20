import { nextTier, ratingToNextTier, tierFor, tierProgress } from '../lib/ranks';

export function DifficultyBadge({ difficulty }) {
  return <span className={`difficulty ${difficulty}`}>{difficulty}</span>;
}

export function RankBadge({ rating, size = 'sm', showRating = true }) {
  const tier = tierFor(rating);
  return (
    <span
      className={`rank-badge rank-${size}`}
      style={{ '--tier': tier.color, '--tier-dim': tier.dim }}
    >
      <span className="rank-tier">{tier.name}</span>
      {showRating && <span className="rank-rating">{rating}</span>}
    </span>
  );
}

/** Tier badge plus progress to the next tier — the Profile header version. */
export function RankProgress({ rating }) {
  const tier = tierFor(rating);
  const next = nextTier(rating);
  const pct = tierProgress(rating) * 100;

  return (
    <div className="rank-progress" style={{ '--tier': tier.color, '--tier-dim': tier.dim }}>
      <div className="rank-progress-head">
        <RankBadge rating={rating} size="lg" showRating={false} />
        <span className="rank-progress-rating">{rating}</span>
      </div>
      <div className="rank-bar">
        <div className="rank-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="rank-progress-note">
        {next
          ? `${ratingToNextTier(rating)} rating to ${next.name}`
          : 'Top tier — nothing above this'}
      </span>
    </div>
  );
}

/**
 * Opponent live status. Carries a state and, at most, integer test counts — never code.
 * That restriction is enforced on the server too; this component simply has nothing
 * else to render.
 */
export function StatusPill({ state, passed, total }) {
  const LABELS = {
    typing: 'Typing…',
    idle: 'Thinking',
    running: 'Running tests',
    ran_tests: 'Ran tests',
    submitting: 'Submitting…',
    submitted: 'Submitted',
    solved: 'Solved ✓',
    reconnected: 'Back online',
    disconnected: 'Disconnected',
  };

  const label =
    state === 'ran_tests' && total
      ? `Running tests (${passed}/${total} passing)`
      : LABELS[state] || 'Waiting';

  return (
    <span className={`status-pill state-${state || 'waiting'}`}>
      <span className="dot" />
      {label}
    </span>
  );
}

/**
 * Wraps gated content in a blur with an upgrade prompt.
 *
 * Worth being honest about what this is: a *presentation* gate. It hides content the
 * browser has already received, so it is not a security boundary — anything genuinely
 * sensitive must not be sent to a free user at all. Here it wraps mock analytics and an
 * AI review that the server will simply refuse to generate without a subscription.
 */
export function PremiumLock({ locked, title, blurb, children, cta = 'Upgrade — ₹50/mo' }) {
  if (!locked) return children;

  return (
    <div className="premium-lock">
      <div className="premium-lock-content" aria-hidden="true">
        {children}
      </div>
      <div className="premium-lock-overlay">
        <span className="lock-icon">🔒</span>
        <h3>{title}</h3>
        {blurb && <p className="muted">{blurb}</p>}
        <a className="button-link" href="/upgrade">
          {cta}
        </a>
      </div>
    </div>
  );
}

export function ResultBanner({ outcome, reason, delta, ratingAfter }) {
  const HEADLINE = { win: 'You win', loss: 'You lose', draw: 'Draw' };
  return (
    <div className={`result-banner ${outcome}`}>
      <h1 className="result-headline">{HEADLINE[outcome]}</h1>
      {reason && <p className="result-reason">{reason}</p>}
      {delta !== undefined && delta !== null && (
        <div className={`rating-delta ${delta >= 0 ? 'up' : 'down'}`}>
          {delta >= 0 ? '+' : ''}
          {delta}
          {ratingAfter !== undefined && <span className="to">→ {ratingAfter}</span>}
        </div>
      )}
    </div>
  );
}
