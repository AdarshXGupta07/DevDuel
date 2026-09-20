import { useEffect, useState } from 'react';

/**
 * Counts down to a server-supplied timestamp.
 *
 * The server never sends ticks — it sends `starts_at` / `ends_at` once, and every client
 * counts locally. That is what makes a refresh mid-countdown work: the client recomputes
 * from the timestamp instead of restarting a number it was handed.
 *
 * `skewMs` corrects for the client's clock being wrong, measured from the `server_time`
 * the server includes in every state payload.
 */
export function useCountdown(target, skewMs = 0) {
  const [remaining, setRemaining] = useState(() => compute(target, skewMs));

  useEffect(() => {
    setRemaining(compute(target, skewMs));
    if (!target) return undefined;
    const id = setInterval(() => setRemaining(compute(target, skewMs)), 250);
    return () => clearInterval(id);
  }, [target, skewMs]);

  return remaining;
}

function compute(target, skewMs) {
  if (!target) return null;
  const ms = new Date(target).getTime() - (Date.now() + skewMs);
  return Math.max(0, Math.floor(ms / 1000));
}

export function formatSeconds(total) {
  if (total === null || total === undefined) return '--:--';
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function Timer({ endsAt, skewMs }) {
  const remaining = useCountdown(endsAt, skewMs);
  const urgent = remaining !== null && remaining <= 60;
  return (
    <div className={`timer ${urgent ? 'urgent' : ''}`}>
      <span className="timer-label">Time left</span>
      <span className="timer-value">{formatSeconds(remaining)}</span>
    </div>
  );
}
