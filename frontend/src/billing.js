import { api } from './api';

const CHECKOUT_SRC = 'https://checkout.razorpay.com/v1/checkout.js';
let scriptPromise = null;

function loadCheckoutScript() {
  if (window.Razorpay) return Promise.resolve();
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = CHECKOUT_SRC;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error('Could not reach the payment provider.'));
    };
    document.body.appendChild(script);
  });
  return scriptPromise;
}

/**
 * Open Razorpay Checkout for a monthly subscription.
 *
 * The handler callback is NOT proof of payment — it only tells us *which* subscription
 * to re-check. `/api/billing/sync` then asks Razorpay server-to-server what actually
 * happened, and the webhook confirms it again independently. A user who edits the
 * callback in devtools changes nothing.
 */
export async function startSubscription() {
  await loadCheckoutScript();

  const session = await api('/api/billing/subscribe', { method: 'POST' });

  return new Promise((resolve, reject) => {
    const checkout = new window.Razorpay({
      key: session.key_id,
      subscription_id: session.subscription_id,
      name: 'DevDuel',
      description: 'Unlimited ranked duels, AI practice, private rooms',
      theme: { color: '#2ee6c5' },
      prefill: { name: session.name, email: session.email },
      handler: async (response) => {
        try {
          resolve(
            await api('/api/billing/sync', {
              method: 'POST',
              body: { subscription_id: response.razorpay_subscription_id },
            }),
          );
        } catch (err) {
          // Payment may well have succeeded — the webhook is the backstop, so never
          // tell the user it failed. Ask them to refresh instead.
          resolve({ pending: true, error: err.message });
        }
      },
      modal: {
        ondismiss: () => reject(new Error('cancelled')),
      },
    });

    checkout.on('payment.failed', (response) => {
      reject(new Error(response?.error?.description || 'Payment failed.'));
    });

    checkout.open();
  });
}

export const billing = {
  config: () => api('/api/billing/config'),
  status: () => api('/api/billing/status'),
  cancel: () => api('/api/billing/cancel', { method: 'POST' }),
};
