import { useEffect, useState } from 'react';
import { billing, startSubscription } from '../billing';
import { useAuth } from '../auth';

/**
 * The upgrade path. Renders nothing at all when billing is not configured on the
 * server, so a dev environment with no Razorpay keys does not show a dead button.
 */
export default function UpgradeButton({ className = 'upgrade', label = 'Upgrade · ₹50/mo' }) {
  const { user, refreshUser } = useAuth();
  const [config, setConfig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    billing.config().then(setConfig).catch(() => setConfig({ enabled: false }));
  }, []);

  if (!config?.enabled || user?.plan === 'paid') return null;

  async function upgrade() {
    setBusy(true);
    setMessage('');
    try {
      const result = await startSubscription();
      if (result?.pending) {
        setMessage('Payment received — activating. Refresh in a moment.');
      } else if (result?.is_paid) {
        setMessage('You are on DevDuel Pro. Ranked is unlimited now.');
      } else {
        setMessage('Payment authorised. Activation can take a few seconds.');
      }
      await refreshUser();
    } catch (err) {
      if (err.message !== 'cancelled') setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className={className} onClick={upgrade} disabled={busy}>
        {busy ? 'Opening…' : label}
      </button>
      {config.test_mode && <span className="test-badge">test mode</span>}
      {message && <p className="billing-message">{message}</p>}
    </>
  );
}
