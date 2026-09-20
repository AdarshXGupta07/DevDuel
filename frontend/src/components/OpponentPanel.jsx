const LABELS = {
  typing: 'typing',
  idle: 'thinking',
  running: 'running code',
  ran_tests: 'ran tests',
  submitting: 'submitting',
  reconnected: 'back online',
};

/**
 * Everything the opponent is allowed to know — and nothing else exists here to leak.
 * The server never transmits opponent code during a live duel (ADR-0028), so this panel
 * has no access to it even by mistake.
 *
 * Amber throughout: in this interface the opponent is always amber, you are always teal.
 */
export default function OpponentPanel({ status, disconnect }) {
  const state = status?.state || 'waiting';
  const pct = status?.total ? (status.passed / status.total) * 100 : 0;

  return (
    <aside className="opponent-panel">
      <h4>Opponent</h4>

      <div className={`opponent-state state-${state}`}>
        <span className="dot" />
        {LABELS[state] || 'waiting'}
      </div>

      {status?.total ? (
        <div className="opponent-tests">
          <div className="bar">
            <div className="bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="tests-count">
            {status.passed}/{status.total}
          </span>
          <span className="tests-label">tests passing</span>
        </div>
      ) : null}

      {disconnect && (
        <div className="opponent-disconnected">
          <strong>Connection lost</strong>
          <span className="grace-count">{disconnect.secondsLeft}s</span>
          <span className="tests-label">until they forfeit</span>
        </div>
      )}
    </aside>
  );
}
