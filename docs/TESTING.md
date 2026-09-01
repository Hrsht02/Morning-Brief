# Morning Brief testing and sandbox

## Safe pre-production test sequence

1. Start backend and frontend with a non-production database/environment.
2. Log in as an admin.
3. Open `/admin/sandbox`.
4. Run **System health**. Fix every red check before deployment.
5. Run **Check all features**. Confirm sources, categories and approved stories exist.
6. Run **Simulate automatic email**. This is read-only: it evaluates every active onboarded reader against their timezone, configured send time, duplicate-delivery state and approved local edition. It does not send mail.
7. Run **Send safe test email** only after `BREVO_API_KEY`, sender settings and the developer/test recipient are configured. This is the only sandbox action that sends mail.
8. Separately test **Send latest approved news** only with a dedicated test user/database before using real subscribers.

## What the automatic simulation proves

The simulation checks the same important eligibility inputs used by scheduled delivery:

- active and onboarded reader
- reader timezone
- configured send hour/minute
- current local date
- approved, published, non-test stories for that local date
- already-sent protection
- country/category personalization and the configured edition story limit

It reports `WOULD SEND` without changing `last_sent_date` or writing an email delivery record.

## API endpoints

All require an authenticated admin:

- `GET /admin/sandbox/health` — deployment/configuration readiness
- `GET /admin/sandbox/features` — core feature/data readiness
- `GET /admin/sandbox/automatic-email` — read-only scheduler simulation
- `POST /admin/actions/send-test-email` — real provider delivery to the configured test address

## Backend tests

From `backend/`:

```bash
pip install -r requirements.txt
pytest -q
```

## Frontend checks

From `frontend/`:

```bash
npm ci
npm run build
```

## Production rule

Never use the real-user manual send as the first email test. First use the sandbox simulation, then the safe test email, then a dedicated test subscriber/database, and only then enable scheduled delivery for real subscribers.
