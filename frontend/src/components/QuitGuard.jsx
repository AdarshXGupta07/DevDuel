import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Stops a player walking out of a live duel by accident.
 *
 * Three ways out of a duel, and each needs its own interception:
 *   1. The browser Back button  -> popstate, re-pushed so Back has somewhere to land
 *   2. Closing the tab/window   -> beforeunload (the browser shows its own dialog; we
 *                                  cannot style it or add our own text any more)
 *   3. An in-app link or button -> the Quit button calls confirmQuit() directly
 *
 * Deliberately NOT prevented: the duel itself continuing. A player who really wants out
 * gets out — this only makes sure it is a decision rather than a reflex.
 */
export function useQuitGuard({ active, onConfirm }) {
  const [asking, setAsking] = useState(false);
  const pendingRef = useRef(null);

  // Keep a sentinel entry on the history stack so a Back press has something to consume.
  // Without it the first Back leaves the page before popstate can react.
  useEffect(() => {
    if (!active) return undefined;

    window.history.pushState({ duelGuard: true }, '');

    const onPopState = () => {
      // Back was pressed: re-push so we stay put, then ask.
      window.history.pushState({ duelGuard: true }, '');
      pendingRef.current = 'back';
      setAsking(true);
    };

    const onBeforeUnload = (e) => {
      e.preventDefault();
      // Modern browsers ignore custom text and show their own wording; returning a
      // value is still what triggers the dialog at all.
      e.returnValue = '';
      return '';
    };

    window.addEventListener('popstate', onPopState);
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      window.removeEventListener('popstate', onPopState);
      window.removeEventListener('beforeunload', onBeforeUnload);
    };
  }, [active]);

  const requestQuit = useCallback(() => {
    pendingRef.current = 'button';
    setAsking(true);
  }, []);

  const cancel = useCallback(() => {
    pendingRef.current = null;
    setAsking(false);
  }, []);

  const confirm = useCallback(() => {
    setAsking(false);
    pendingRef.current = null;
    onConfirm?.();
  }, [onConfirm]);

  return { asking, requestQuit, cancel, confirm };
}

/**
 * The dialog itself. Says exactly what quitting costs — a vague "are you sure?" makes
 * people click through without reading, which defeats the point of asking.
 */
export default function QuitDialog({ open, mode, conduct, onCancel, onConfirm }) {
  if (!open) return null;

  const isRanked = mode === 'ranked';
  const abandons = conduct?.abandons_today ?? 0;
  const remaining = conduct?.remaining_before_block ?? 2;
  const lastChance = remaining === 1;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <span className="micro">Leave duel</span>
        <h2>Quit this match?</h2>

        <ul className="quit-consequences">
          <li>
            <strong>You lose the match.</strong> Your opponent is awarded the win.
          </li>
          {isRanked && (
            <li>
              <strong>Your rating drops.</strong> A forfeit is scored exactly like a loss.
            </li>
          )}
          <li>
            {lastChance ? (
              <>
                <strong className="danger">This is your second walkout today.</strong>{' '}
                Matchmaking will be paused for 15 minutes.
              </>
            ) : remaining === 0 ? (
              <>
                <strong className="danger">Matchmaking will be paused</strong> — you have
                already left {abandons} duels today, and the pause gets longer each time.
              </>
            ) : (
              <>Leaving twice in one day pauses matchmaking for 15 minutes.</>
            )}
          </li>
        </ul>

        <div className="modal-actions">
          <button onClick={onCancel}>Keep playing</button>
          <button className="danger-button" onClick={onConfirm}>
            Quit and forfeit
          </button>
        </div>
      </div>
    </div>
  );
}
