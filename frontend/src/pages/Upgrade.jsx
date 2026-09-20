import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth';
import { billing, startSubscription } from '../billing';

const ROWS = [
  ['Casual duels', 'Unlimited', 'Unlimited'],
  ['Ranked duels', '2 per day', 'Unlimited'],
  ['ELO rating & leaderboard', 'Yes', 'Yes'],
  ['AI opponent practice', false, true],
  ['Post-duel AI code review', false, true],
  ['Analytics dashboard', false, true],
  ['Private rooms', false, true],
  ['Problem set', 'Rotating set', 'Full set + interview tags'],
];

function Cell({ value, pro }) {
  if (value === true) return <span className="tick">✓</span>;
  if (value === false) return <span className="cross">—</span>;
  return <span className={pro ? 'pro-value' : ''}>{value}</span>;
}

export default function Upgrade() {
  const { user, refreshUser } = useAuth();
  const [config, setConfig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const isPaid = user?.plan === 'paid';

  useEffect(() => {
    billing.config().then(setConfig).catch(() => setConfig({ enabled: false }));
  }, []);

  async function upgrade() {
    setBusy(true);
    setMessage('');
    try {
      const result = await startSubscription();
      setMessage(
        result?.pending
          ? 'Payment received — activating. Refresh in a moment.'
          : 'You are on DevDuel Pro. Ranked is unlimited now.',
      );
      await refreshUser();
    } catch (err) {
      if (err.message !== 'cancelled') setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upgrade">
      <section className="card upgrade-head">
        <span className="micro">DevDuel Pro</span>
        <h1>Everything unlimited, for less than a coffee.</h1>
        <p className="muted">
          One plan. Cancel any time — access runs to the end of the period you paid for.
        </p>
        <div className="price">
          <span className="price-amount">₹50</span>
          <span className="price-period">/month</span>
        </div>

        {isPaid ? (
          <p className="pro-active">✓ You're on Pro. Thanks for backing this.</p>
        ) : !user ? (
          <Link to="/login" className="button-link">
            Sign in to upgrade
          </Link>
        ) : config?.enabled ? (
          <button onClick={upgrade} disabled={busy}>
            {busy ? 'Opening…' : 'Upgrade to Pro'}
          </button>
        ) : (
          <>
            <button disabled title="Billing is not configured on this server">
              Upgrade to Pro
            </button>
            <p className="billing-message">
              Payments aren't switched on for this environment yet.
            </p>
          </>
        )}

        {config?.test_mode && <span className="test-badge">test mode</span>}
        {message && <p className="billing-message">{message}</p>}
      </section>

      <section className="card">
        <table className="compare">
          <thead>
            <tr>
              <th />
              <th>Free</th>
              <th className="pro-col">Pro</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([label, free, pro]) => (
              <tr key={label}>
                <td className="compare-label">{label}</td>
                <td>
                  <Cell value={free} />
                </td>
                <td className="pro-col">
                  <Cell value={pro} pro />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <p className="muted fine-print">
        Free ranked matches reset at midnight IST. A forfeited or abandoned match doesn't
        count against your daily free matches.
      </p>
    </div>
  );
}
