# Morning Brief

An LLM-powered daily news digest with a strict, multi-layer verification pipeline
before anything publishes. Users get one email each morning (or read on the web),
every story cites its real sources, and nothing goes live without either passing
every enabled verification layer or an admin's explicit approval - your choice,
fully configurable. Built for an Indian audience, entirely on free tools.

## What's inside

- `backend/` — FastAPI app: auth (email + Google), RSS ingestion, clustering,
  bilingual (EN/HI) LLM generation, independent AI verification, admin panel,
  developer sandbox API, email sending
- `frontend/` — React app: Google/email login, onboarding, daily edition reader,
  full admin dashboard
- `.github/workflows/` — cron jobs for automatic daily ingestion + email sending

## 1. Get your free credentials (15-20 minutes)

| Service | What it's for | Where to get it |
|---|---|---|
| **Groq** | Content generator (LLM #1) | https://console.groq.com/keys |
| **Google Gemini** | Independent verifier (LLM #2 - deliberately a different provider) | https://aistudio.google.com/apikey |
| **Brevo** | Email sending (free tier: 300/day) | https://app.brevo.com/settings/keys/api |
| **Google OAuth Client ID** | Google Sign-In (optional - skip and email/password still works) | https://console.cloud.google.com/apis/credentials |

For the Google OAuth Client ID: create a "Web application" type credential, and
add your frontend URL (e.g. `http://localhost:5173` and your deployed URL) under
**Authorized JavaScript origins**. Leave `GOOGLE_CLIENT_ID` blank in `.env` if you
want to skip this for now - the Google Sign-In button simply won't appear, and
email/password login is unaffected.

The database defaults to a local SQLite file (zero setup), and default Indian +
international RSS sources are pre-configured.

## 2. Run the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in: GROQ_API_KEY, GEMINI_API_KEY, BREVO_API_KEY, EMAIL_FROM_ADDRESS,
# JWT_SECRET_KEY (any long random string), CRON_SECRET (any long random string).
# GOOGLE_CLIENT_ID is optional - see above.

uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for the full interactive API reference.

On first startup, the app automatically creates all tables, runs any needed
migrations (safe on an existing database with real data - see below), and seeds:
categories, India-focused default RSS sources, the 5-layer default verification
pipeline, a free plan stub, and your first admin account (`ADMIN_EMAIL`/`ADMIN_PASSWORD`
from `.env`).

## 3. Run the frontend

```bash
cd frontend
npm install
cp .env.example .env       # VITE_API_URL=http://localhost:8000 is already correct
npm run dev
```

Visit http://localhost:5173.

## 4. Generate and approve your first edition

1. Log in as admin, go to **Admin → Overview**, click **"Run ingestion now"**
   (runs in the background - watch the button change to "Ingesting...").
2. Once done, go to **Admin → Pending Approval** - by default, EVERY story waits
   here for a human decision, regardless of how clean it is (`require_human_approval_all`
   is `true` by default). Review the flags, approve or reject each one.
3. Go to the **Today** page to see your approved edition.
4. Click **"Send TEST email"** in Admin → Overview to safely test email delivery
   without touching any real subscriber - it sends to `developer_test_email`
   (set in Settings) or your own account.

## The verification pipeline

Every story passes through whatever layers are enabled in **Admin → Verification**,
in order:

1. **Source Policy Check** - blocks/flags based on each source's legal risk tier
2. **Citation Completeness** - every story must trace back to real source articles
3. **Near-Verbatim Similarity** - flags AI summaries that are too close to copying
4. **AI Confidence Threshold** - flags low-confidence generations
5. **Independent AI Verifier** - a SEPARATE model/provider (Gemini, not Groq) checks
   the draft against the original sources for unsupported claims or contradictions

**Every layer is admin-controllable**: enable/disable, reorder, or mark advisory-only
(flags but doesn't block) - right from the Verification tab, no code changes needed.
**Fail-closed by design**: if a blocking layer can't run (network down, API key
missing, etc.), the story is held for review, never silently approved.

Two master switches in **Settings** override everything:
- `require_human_approval_all` (default `true`) - even a perfectly clean story still
  waits for a human click.
- `skip_all_verification` (default `false`) - **danger**: bypasses every layer and
  auto-publishes immediately. Only for trusted testing, never recommended in production.

## Bilingual content (English / Hindi)

Controlled by the `bilingual_generation` setting (default `true`). When on, every
story is generated in English **and** Hindi in a single LLM call (not two - this
protects your free-tier rate limits). Each user picks their reading language in
Preferences; if a Hindi variant wasn't generated for a given story, that user
automatically sees the English version instead - a story never disappears due to
a translation gap.

## Auto vs. manual scheduling

The `scheduling_mode` setting (**Settings** tab) is the master switch:
- `auto` (default): the GitHub Actions cron jobs run ingestion hourly (plus an
  explicit final pass at 23:45 IST, capturing news up to midnight - like a
  newspaper's print deadline) and check every hour whether any user's chosen
  send-time has arrived (most Indian users default to 6 AM, sitting in the
  intended 6-7AM window).
- `manual`: scheduled runs become no-ops. **The admin panel's manual buttons
  always work regardless of this setting** - "Run ingestion now" and "Send
  today's emails now" are your explicit on-demand triggers.

## Developer access (without giving out admin credentials)

**Admin → Developers & API Keys**:
- **Create a developer account**: read-only access to stats/sources/settings/
  verification layers/pending stories. Cannot edit sources, manage users, or
  approve/reject real stories.
- **Issue an API key**: for a developer's own scripts to call the sandboxed
  `/api/v1/*` endpoints directly with an `X-Api-Key` header. Sandbox guarantees:
  - `POST /api/v1/test/run-ingestion` - runs the real pipeline but capped to 3
    clusters, and every resulting story is tagged so it can **never** appear in
    a real user's edition or email, regardless of its approval status.
  - `POST /api/v1/test/send-email` - sends ONE email built from real approved
    content to a fixed test address only, never the real subscriber list.
  - `GET /api/v1/editions/today` - read-only, real published content, no PII.

## Google Sign-In

Works for both regular users and admins - it just authenticates the person;
existing roles are unaffected. Signing in with Google using an email that
already has a password account links the two rather than creating a duplicate.
If `GOOGLE_CLIENT_ID` isn't set, the button simply doesn't render - no broken UI.

## Deploying for free

| Piece | Free host |
|---|---|
| Backend (FastAPI) | [Render](https://render.com) — free web service |
| Frontend (React) | [Vercel](https://vercel.com) or [Cloudflare Pages](https://pages.cloudflare.com) |
| Database | [Supabase](https://supabase.com) or [Neon](https://neon.tech) Postgres — **not** Render's free Postgres, which auto-deletes after 30 days |
| Keep backend awake | [UptimeRobot](https://uptimerobot.com) free monitor pinging `/health` every 5 min |
| Scheduled jobs | The included GitHub Actions workflows — add `BACKEND_URL` and `CRON_SECRET` as repo secrets |

**A note on hosting that never sleeps**: this space is heavily marketed with "no-sleep
free tier" claims from smaller, less-established hosts that I can't independently vouch
for. Render + UptimeRobot (above) is a combination that's actually been tested and
confirmed working. If you want to explore alternatives, Google Cloud Run's free tier
(2 million requests/month) is a well-established, reputable option with much faster
cold starts than Render's default - worth investigating if Render's sleep behavior
becomes a real problem at your scale, but it requires containerizing the app
(a Dockerfile) rather than Render's simpler git-push deploy.

## Upgrading an existing deployment

If you already have this running in production with real users, the new tables and
columns are added automatically and safely on startup - existing data is never
touched or lost (this was specifically tested against a simulated production database
before release). You will need to add the new environment variables (`GEMINI_API_KEY`
at minimum, `GOOGLE_CLIENT_ID` optionally) for the new features to activate.

## Configuration philosophy — nothing is hardcoded

Sources, categories, every verification layer, every threshold, scheduling mode,
bilingual generation, the human-approval requirement, blocked domains - all live in
the database, editable from the Admin panel. Secrets (API keys, database URL) stay
in `.env` - that's a security boundary, not a flexibility one.

## Known limitations to know about

- **Email free tier caps at 300/day (Brevo).** Combine with a second, different
  provider (e.g. Resend) for more free volume, or budget ~$9/month once you
  outgrow it - see earlier project discussion for the full reasoning.
- **Clustering is lightweight by design** (word-overlap + synonym normalization,
  not embeddings) to stay fast and dependency-free on a low-CPU free hosting tier.
- **The independent verifier fails closed**: if Gemini is unreachable, the story
  is held for review rather than silently passing - by design, per the multi-layer
  verification plan.
- **Legal/licensing review is still on you before monetizing** - the verification
  pipeline reduces risk (source risk tiers, blocked domains, near-verbatim
  detection) but is not a substitute for reviewing actual publisher terms and,
  where appropriate, qualified legal advice - see the earlier project discussion
  on Indian copyright law (Section 52, PTI/ANI litigiousness) for the specifics.

## Project structure

```
morning-brief/
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, database.py, models.py, schemas.py
│   │   ├── auth.py                    # JWT + Google Sign-In + API key auth + role checks
│   │   ├── seed.py                    # defaults + get_setting()/set_setting() helpers
│   │   ├── ingestion/
│   │   │   ├── rss_fetcher.py, clustering.py, pipeline.py
│   │   │   ├── verification.py        # pure helper functions (similarity, source risk)
│   │   │   └── verification_layers.py # the configurable layer registry
│   │   ├── llm/
│   │   │   ├── groq_client.py         # generator (LLM #1), bilingual-aware
│   │   │   └── gemini_client.py       # independent verifier (LLM #2)
│   │   ├── email_service/             # brevo_client.py, sender.py
│   │   └── routers/                   # auth, users, editions, categories, admin, scheduler, api_v1
│   ├── requirements.txt, .env.example
├── frontend/
│   └── src/
│       ├── pages/                     # Login, Signup, Onboarding, DailyEdition, Preferences, Admin
│       ├── components/                # incl. GoogleSignInButton.jsx
│       └── context/AuthContext.jsx
└── .github/workflows/                 # ingest-news.yml, send-emails.yml
```
