# Billing — Razorpay subscriptions

₹50/month recurring, via Razorpay Subscriptions. Built and testable entirely on **test
keys**; nothing here needs live keys or completed KYC to develop against.

---

## 1. One-time setup in the Razorpay dashboard

Switch the dashboard to **Test Mode** (toggle, top of the page) before doing any of this.

1. **Settings → API Keys → Generate Test Key.** You get `rzp_test_…` and a secret. The
   secret is shown once — copy it now.
2. **Subscriptions → Plans → Create Plan.**
   - Billing frequency: Monthly, every 1 month
   - Amount: `50` INR
   - Note the plan id: `plan_…`
3. **Settings → Webhooks → Add New Webhook.**
   - URL: your public URL + `/api/billing/webhook`
   - Secret: invent a strong string; this is `RAZORPAY_WEBHOOK_SECRET`
   - Events: `subscription.authenticated`, `subscription.activated`,
     `subscription.charged`, `subscription.updated`, `subscription.pending`,
     `subscription.halted`, `subscription.cancelled`, `subscription.completed`

For local development Razorpay cannot reach `localhost`, so tunnel it:

```bash
npx localtunnel --port 8000
```

Use the tunnel URL in the webhook config while testing.

## 2. Environment

```
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=whsec_something_long
RAZORPAY_PLAN_ID=plan_xxxxxxxxxxxx
```

Leave them blank and billing disables itself cleanly — `/api/billing/config` reports
`enabled: false` and the frontend renders no upgrade button at all.

## 3. Testing a subscription

Razorpay test mode accepts these without moving real money:

| Method | Value |
|---|---|
| Card | `4111 1111 1111 1111`, any future expiry, any CVV |
| UPI (success) | `success@razorpay` |
| UPI (failure) | `failure@razorpay` |
| Netbanking | pick any bank, then "Success" on their simulator |

Flow to walk through:

1. Register a free user, play 2 ranked duels → the third click shows the wall.
2. Click Upgrade → Razorpay Checkout opens → pay with a test method.
3. `/api/billing/sync` runs immediately (server-to-server re-check), and the webhook
   arrives independently seconds later.
4. `GET /auth/me` shows `plan: "paid"`; ranked becomes unlimited.

**Also test the unhappy paths** — they are the ones that cost money when wrong:

- Dismiss the Checkout modal → nothing changes, no subscription left half-created
- Pay with `failure@razorpay` → user stays free, a clear message appears
- Replay a webhook from the dashboard ("Resend") → second delivery is a no-op
  (`{"status": "duplicate"}`), the plan does not extend twice
- Tamper with a webhook body in a manual `curl` → `400 Invalid signature`
- Cancel → access continues to the period end, then lapses

## 4. How access is actually granted

```
browser ──► /api/billing/subscribe ──► Razorpay: create subscription
                                             │  (user is still FREE here)
browser ──► Razorpay Checkout ───────────────┘
   │
   ├─ handler fires ──► /api/billing/sync ──► Razorpay API: "what is this really?"
   │                                              └──► users.plan = paid
   └─ meanwhile ────── Razorpay ──► /api/billing/webhook (signed)
                                          └──► users.plan = paid  (idempotent)
```

The browser never asserts payment; it only says *which* subscription to re-check. Both
paths converge on `_apply_entity()`, the single function that writes `users.plan`.

## 5. Things that will bite

- **The webhook signature covers the raw request body.** Never re-serialise the JSON
  before verifying; a reordered key or added space breaks the digest.
- **Webhooks are at-least-once.** Idempotency comes from the UNIQUE constraint on
  `payments.provider_event_id`, not from a prior SELECT — which would race a simultaneous
  redelivery.
- **The webhook route returns 200 even on an internal error** (after the signature
  verifies). A non-2xx makes Razorpay retry, and a retry will not fix a bug in our code;
  failures are logged with the event id for deliberate replay.
- **Going live is a separate act**: real keys, a real plan id, a real webhook secret, and
  completed KYC. The app refuses to boot with `rzp_test_` keys when `APP_ENV=production`.

## 6. Still to build before charging real money

- Pricing page and a proper paid-features comparison
- Payment-failure and renewal-reminder emails (no email system exists yet at all)
- **Terms, Privacy Policy, Refund/Cancellation Policy** — Razorpay requires these pages
  before approving a live account, and the privacy policy must disclose keystroke logging
- An admin view of subscriptions for support questions
