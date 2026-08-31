# Morning Brief

Country-aware, bilingual daily news digest with automatic RSS ingestion, Groq generation, independent Gemini verification, originality checks, human publication gates, personalized editions, and timezone-aware email delivery.

## Production flow

`RSS sources → country-aware clustering → Groq draft → automatic originality rewrite when needed → similarity + long-phrase checks → independent Gemini verification → human approval gate → personalized edition → scheduled email`

Nothing reaches a real reader unless it is `approved`, `is_published=true`, and not test content. The default production policy requires human approval for every story.

## Key capabilities

- **Country-aware personalization:** readers select a country; supported countries receive local-first ranking plus global stories. Unsupported countries safely fall back to the global editorial pool instead of returning an empty edition.
- **India-first defaults:** India is the default market and default country for new users. Indian sources are pre-seeded; source country can be managed from the admin API.
- **Category personalization:** selected categories are prioritized while `outside_bubble_min_stories` keeps the edition from becoming a filter bubble.
- **Bilingual EN/HI:** one Groq call can produce English and Hindi variants; Hindi safely falls back to English when unavailable.
- **Automatic ingestion:** GitHub Actions runs hourly plus a final 23:45 IST pass. `scheduling_mode=manual` disables scheduled triggers while preserving manual admin actions.
- **Automatic processing:** ingestion performs clustering, generation, originality rewrite, verification, storage, and publication gating without a manual processing step.
- **Timezone-aware delivery:** every user has an IANA timezone and local send time. The hourly job checks the user's local time and prevents duplicate sends per local date.
- **Originality protection:** deterministic word similarity is calculated first; a Groq originality rewrite is automatically attempted above `originality_rewrite_trigger_threshold`, then similarity is checked again.
- **Long-phrase detection:** consecutive phrase overlap is checked independently from word-overlap similarity and is configurable.
- **Independent verification:** Gemini is a separate provider/model from Groq and fails closed when unavailable.
- **Human review:** individual Approve/Reject actions with notes and audit history.
- **Approved-news dashboard:** `/admin/approved` lists all approved production stories and shows country, category, confidence, and originality status.
- **Source management:** activate/deactivate sources, edit country/category/tier, and assign standard/high-risk/blocked legal risk.
- **Verification management:** enable/disable, reorder, and make verification layers blocking or advisory.
- **Job monitoring:** ingestion status, start/completion timestamps, last result, scheduling configuration, and detailed health endpoints.
- **Scalability controls:** configurable max RSS entries, fetch timeout, max clusters per run, and LLM pacing.
- **Developer sandbox:** test ingestion is isolated from production content and test email never targets the real subscriber list.
- **Auditability:** source changes, publication decisions, settings, API keys, and other administrative actions are recorded.

## Setup

### Backend

```bash
cd backend
python -m venv venv
# Windows: venv\\Scripts\\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Backend docs: `http://localhost:8000/docs`  
Frontend: `http://localhost:5173`

## Required services

| Service | Purpose |
|---|---|
| Groq | Open-weight LLM generation + originality rewrite |
| Google Gemini | Independent verification |
| Brevo | Transactional email |
| Google OAuth | Optional Google login |
| Postgres/Supabase/Neon | Recommended production database |
| GitHub Actions | Scheduled ingestion and email triggers |

## Environment and security

Copy `backend/.env.example` to `.env`. In production set `ENVIRONMENT=production` and use strong, unique values for `JWT_SECRET_KEY`, `CRON_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`. Production startup rejects the insecure defaults.

Never commit `.env` or API keys. GitHub Actions should contain `BACKEND_URL` and `CRON_SECRET` as repository secrets.

## Important settings

All behavior below is stored in the `settings` table and can be changed from **Admin → Settings**:

- `scheduling_mode`: `auto` or `manual`
- `require_human_approval_all`: default `true`
- `skip_all_verification`: dangerous testing override; keep `false` in production
- `stories_per_edition`
- `outside_bubble_min_stories`
- `near_verbatim_similarity_threshold`
- `long_phrase_overlap_threshold`
- `long_phrase_words`
- `originality_rewrite_trigger_threshold`
- `max_entries_per_source`
- `source_fetch_timeout_seconds`
- `max_clusters_per_run`
- `llm_pause_seconds`
- `admin_timezone`
- `bilingual_generation`

## Verification layers

1. Source policy
2. Citation completeness
3. Near-verbatim similarity
4. Long-phrase copy detection
5. AI confidence threshold
6. Independent Gemini verifier

Layers are configurable from the admin panel. A failed or unavailable **blocking** layer holds the story for human review.

## Scheduling

The included workflows are:

- `.github/workflows/ingest-news.yml` — hourly ingestion + final 23:45 IST pass
- `.github/workflows/send-emails.yml` — hourly local-time email check
- `.github/workflows/ci.yml` — backend compile/import checks and frontend production build on pushes/PRs

The workflow triggers are deliberately frequent because the backend owns the actual user-local schedule. This avoids hardcoding one UTC send time for users in different countries.

## Admin routes

- `/admin` — main management dashboard
- `/admin/approved` — all approved production news
- `/admin/stories/pending` — human review queue
- `/admin/sources` — source management
- `/admin/verification-layers` — verification configuration
- `/admin/settings` — runtime configuration
- `/admin/jobs` — operational status
- `/admin/countries` — country/service statistics
- `/admin/health/details` — configuration/health diagnostics

## Testing

CI runs automatically after repository changes. It validates Python compilation/application import and runs `npm ci` + the Vite production build. The GitHub Actions run must be green before treating a commit as production-ready.

For manual functional testing:

1. Run backend and frontend.
2. Create/login as admin.
3. Set `scheduling_mode=manual` while testing.
4. Run ingestion from Admin.
5. Review individual stories in Pending Approval.
6. Approve selected stories.
7. Open **Approved News**.
8. Use the safe TEST email action rather than the real-user send action.

## Deployment

For a small production deployment, use a persistent Postgres database, a hosted FastAPI service, a static React host, and GitHub Actions for scheduled triggers. Keep the backend awake if your host sleeps so background ingestion can finish.

Before monetization or large-scale redistribution, review each source's RSS terms/licensing and obtain appropriate legal advice. Technical similarity and verification checks reduce risk but do not replace publisher licensing requirements.

## Repository structure

```text
Morning-Brief/
├── backend/
│   └── app/
│       ├── ingestion/       # RSS, clustering, verification, full pipeline
│       ├── llm/             # Groq generator, originality rewrite, Gemini verifier
│       ├── services/        # country-aware personalization/fallback
│       └── routers/         # auth, users, editions, admin, scheduler, operations
├── frontend/
│   └── src/
│       ├── pages/           # reader, preferences, admin, approved-news
│       └── components/
└── .github/workflows/       # ingestion, email delivery, CI
```
