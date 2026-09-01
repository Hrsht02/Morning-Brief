# Morning Brief testing and sandbox

## Safe pre-production test sequence

1. Start backend and frontend with a non-production database/environment.
2. Log in as an admin.
3. Open `/admin/sandbox`.
4. Run **Run full sandbox suite**. Fix every failed readiness check before deployment.
5. Review the automatic-email simulation for every active onboarded reader. Confirm timezone, configured send time, current local date, approved story count, selected story count, country fallback and duplicate-delivery decision.
6. Run **Send safe test email** only after `BREVO_API_KEY`, sender settings and the developer/test recipient are configured. This is the only sandbox action that sends mail.
7. Separately test **Send latest approved news** only with a dedicated test user/database before using real subscribers.

## What the automatic simulation proves

The simulation is read-only and checks the important scheduled-delivery gates:

- active and onboarded reader
- reader timezone
- configured send hour/minute and one-hour scheduler window
- current local date
- approved, published, non-test stories for that local date
- successful email-log duplicate protection
- country/category personalization
- configured edition story limit
- effective country/fallback resolution

It reports `WOULD SEND` or an explicit reason such as `outside_send_window`, `already_delivered`, `no_approved_stories`, or `no_personalized_stories`. It does not change `last_sent_date`, create an `EmailLog`, or call the email provider.

## API endpoints

All require an authenticated admin:

- `GET /admin/sandbox/health` — deployment/configuration readiness
- `GET /admin/sandbox/features` — core feature/data readiness
- `GET /admin/sandbox/automatic-email` — read-only scheduler simulation
- `GET /admin/sandbox/suite` — one-click read-only suite combining health, features and automatic-email simulation
- `POST /admin/actions/send-test-email` — real provider delivery to the configured test address

## Backend tests

From `backend/`:

```bash
pip install -r requirements.txt
pytest -q
```

CI runs compilation, application import, and the full pytest suite on every PR to `main`.

## Frontend checks

From `frontend/`:

```bash
npm ci
npm run build
```

## Production rule

Never use the real-user manual send as the first email test. First use the sandbox suite, then the safe test email, then a dedicated test subscriber/database, and only then enable scheduled delivery for real subscribers.
