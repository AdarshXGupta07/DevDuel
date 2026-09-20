import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Keeps the player inside the duel window during a ranked match.
 *
 * What this genuinely is: a deterrent and a behavioural record. The browser cannot force
 * fullscreen (entering needs a user gesture, exiting cannot be blocked) and a determined
 * cheat can patch these listeners out of the page in a minute. What it does is make
 * "alt-tab to an LLM" a deliberate, visibly-recorded act rather than a reflex — which
 * covers most people most of the time.
 *
 * The forfeit decision is the server's. This hook only reports.
 */

export function isFullscreen() {
  return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
}

export async function requestFullscreen(element = document.documentElement) {
  try {
    if (element.requestFullscreen) await element.requestFullscreen({ navigationUI: 'hide' });
    else if (element.webkitRequestFullscreen) await element.webkitRequestFullscreen();
    return true;
  } catch {
    // Denied, or the browser has no fullscreen (iOS Safari on iPhone). Not fatal —
    // tab-switch detection still works without it.
    return false;
  }
}

export function useProctor({ active, graceSeconds = 15, onViolation, onExpired }) {
  const [away, setAway] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(graceSeconds);
  const [fullscreen, setFullscreen] = useState(isFullscreen());
  const timerRef = useRef(null);
  const awayRef = useRef(false);
  const reasonRef = useRef('blur');

  const clearTimer = () => {
    clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const goneAway = useCallback(
    (reason) => {
      if (!active || awayRef.current) return;
      awayRef.current = true;
      reasonRef.current = reason;
      setAway(true);
      setSecondsLeft(graceSeconds);

      if (graceSeconds <= 0) {
        onExpired?.(reason);
        return;
      }

      clearTimer();
      timerRef.current = setInterval(() => {
        setSecondsLeft((s) => {
          if (s <= 1) {
            clearTimer();
            onExpired?.(reasonRef.current);
            return 0;
          }
          return s - 1;
        });
      }, 1000);
    },
    [active, graceSeconds, onExpired],
  );

  const cameBack = useCallback(() => {
    if (!awayRef.current) return;
    awayRef.current = false;
    clearTimer();
    setAway(false);
    // Report only once they are back, so the server counts one violation per trip
    // rather than one per event — leaving fires both visibilitychange and blur.
    onViolation?.(reasonRef.current);
  }, [onViolation]);

  useEffect(() => {
    if (!active) {
      clearTimer();
      awayRef.current = false;
      setAway(false);
      return undefined;
    }

    const onVisibility = () => {
      if (document.hidden) goneAway('tab_hidden');
      else cameBack();
    };
    const onBlur = () => {
      // A blur without the tab being hidden means another window took focus.
      if (!document.hidden) goneAway('window_blur');
    };
    const onFocus = () => {
      if (!document.hidden) cameBack();
    };
    const onFullscreenChange = () => {
      const now = isFullscreen();
      setFullscreen(now);
      if (!now) goneAway('left_fullscreen');
      else cameBack();
    };

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange);

    return () => {
      clearTimer();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', onFullscreenChange);
    };
  }, [active, goneAway, cameBack]);

  return { away, secondsLeft, fullscreen, setFullscreen };
}

/** Full-bleed overlay shown the moment focus leaves, counting down to the forfeit. */
export function ProctorOverlay({ away, secondsLeft, graceSeconds }) {
  if (!away) return null;
  const urgent = secondsLeft <= 5;

  return (
    <div className="proctor-overlay">
      <span className="proctor-icon">⚠</span>
      <h2>Return to the duel</h2>
      <p>Leaving the duel window is not allowed in ranked matches.</p>
      <span className={`proctor-count ${urgent ? 'urgent' : ''}`}>{secondsLeft}</span>
      <p className="muted">
        The match is forfeited if you are still away when this reaches zero.
      </p>
      {graceSeconds > 0 && (
        <p className="topic-help">Click anywhere in this window to come back.</p>
      )}
    </div>
  );
}

/** Shown before the duel starts, because fullscreen needs a real click to enter. */
export function FullscreenGate({ onEnter }) {
  return (
    <div className="proctor-overlay">
      <span className="proctor-icon">⛶</span>
      <h2>Ranked match — fullscreen required</h2>
      <p>
        Ranked duels run fullscreen. Leaving the window, switching tabs, or exiting
        fullscreen forfeits the match.
      </p>
      <button onClick={onEnter}>Enter fullscreen and start</button>
      <p className="topic-help">Copy and paste are disabled for the duration.</p>
    </div>
  );
}
