import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth';
import { PremiumLock } from '../components/Badges';
import { mockRatingHistory, mockTopicStrength, mockWinRateTrend } from '../mock';

/** Inline SVG rather than a charting library: three small charts do not justify 200KB. */
function LineChart({ points, format = (v) => v, color = 'var(--you)' }) {
  const { path, area, min, max, last } = useMemo(() => {
    const values = points.map((p) => p.value);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const span = hi - lo || 1;
    const x = (i) => (i / Math.max(points.length - 1, 1)) * 100;
    const y = (v) => 100 - ((v - lo) / span) * 82 - 9; // 9% padding top and bottom
    const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(p.value)}`).join(' ');
    return {
      path: d,
      area: `${d} L 100 100 L 0 100 Z`,
      min: lo,
      max: hi,
      last: values[values.length - 1],
    };
  }, [points]);

  return (
    <div className="chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img">
        <path d={area} fill={color} opacity="0.08" />
        <path d={path} fill="none" stroke={color} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="chart-axis">
        <span>{format(min)}</span>
        <strong style={{ color }}>{format(last)}</strong>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}

function TopicBars({ topics }) {
  return (
    <ul className="topic-list">
      {topics.map((t) => {
        // Strong / weak is a judgement about accuracy, so the colour is too. Green above
        // 70%, amber 45–70%, red below — and the label says the number, because a colour
        // alone is unreadable to anyone with a colour-vision deficiency.
        const pct = Math.round(t.accuracy * 100);
        const band = pct >= 70 ? 'strong' : pct >= 45 ? 'mid' : 'weak';
        return (
          <li key={t.topic} className={`topic ${band}`}>
            <span className="topic-name">{t.topic}</span>
            <span className="topic-bar">
              <span className="topic-fill" style={{ width: `${pct}%` }} />
            </span>
            <span className="topic-pct">{pct}%</span>
            <span className="topic-count">
              {t.solved}/{t.attempted}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default function Analytics() {
  const { user } = useAuth();
  const locked = user?.plan !== 'paid';

  const weakest = [...mockTopicStrength].sort((a, b) => a.accuracy - b.accuracy).slice(0, 3);

  return (
    <div className="analytics">
      <header className="page-head">
        <div>
          <h1>Analytics</h1>
          <p className="muted">
            Where you're strong, where you're losing duels, and what to practise next.
          </p>
        </div>
        <span className="mock-note">Sample data — not yet wired to real matches</span>
      </header>

      <PremiumLock
        locked={locked}
        title="Analytics is a Pro feature"
        blurb="See your topic strengths, rating trend and what to practise next."
      >
        <div className="analytics-grid">
          <section className="card span-2">
            <h4 style={{ marginTop: 0 }}>Topic strength</h4>
            <TopicBars topics={mockTopicStrength} />
          </section>

          <section className="card">
            <h4 style={{ marginTop: 0 }}>Rating history</h4>
            <LineChart
              points={mockRatingHistory.map((r) => ({ value: r.rating }))}
              format={(v) => Math.round(v)}
            />
          </section>

          <section className="card">
            <h4 style={{ marginTop: 0 }}>Win rate</h4>
            <LineChart
              points={mockWinRateTrend.map((w) => ({ value: w.winRate * 100 }))}
              format={(v) => `${Math.round(v)}%`}
            />
          </section>

          <section className="card">
            <h4 style={{ marginTop: 0 }}>Average solve time</h4>
            <LineChart
              points={mockWinRateTrend.map((w) => ({ value: w.avgSolveSeconds }))}
              format={(v) => `${Math.round(v / 60)}m`}
              color="var(--foe)"
            />
            <p className="muted" style={{ fontSize: 12 }}>
              Down 26% over six weeks — you're solving the same difficulty faster.
            </p>
          </section>

          <section className="card span-2">
            <h4 style={{ marginTop: 0 }}>Recommended practice</h4>
            <p className="muted" style={{ fontSize: 13 }}>
              Your three weakest topics. Practising these moves your rating more than
              drilling what you're already good at.
            </p>
            <div className="recommend-row">
              {weakest.map((t) => (
                <Link
                  key={t.topic}
                  to={`/duel/ai?topic=${encodeURIComponent(t.topic)}`}
                  className="recommend"
                >
                  <span className="recommend-topic">{t.topic}</span>
                  <span className="recommend-pct">{Math.round(t.accuracy * 100)}% accuracy</span>
                  <span className="recommend-cta">Practise vs AI →</span>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </PremiumLock>
    </div>
  );
}
