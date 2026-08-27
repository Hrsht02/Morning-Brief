"""
Populates sensible defaults on first startup so the app is usable immediately
after `docker run` / `uvicorn` with no manual setup. Every value here is a
STARTING POINT the admin can edit later from the admin panel - nothing here
is hardcoded into the app's logic, it's just initial data.
"""
import logging
from sqlalchemy.orm import Session
from . import models
from .security import hash_password
from .config import settings

logger = logging.getLogger("morning_brief.seed")

DEFAULT_CATEGORIES = [
    ("general", "Mixed / For You", None, 0),
    ("national", "National", None, 1),
    ("international", "International", None, 2),
    ("business", "Business", None, 3),
    ("technology", "Technology", None, 4),
    ("sports", "Sports", None, 5),
    ("entertainment", "Entertainment", None, 6),
    ("science-health", "Science & Health", None, 7),
    ("politics", "Politics", None, 8),
    # a couple of illustrative subcategories
    ("cricket", "Cricket", "sports", 0),
    ("football", "Football", "sports", 1),
]

# India-focused default source list. PTI/ANI are deliberately NOT included -
# see blocked_source_domains below and the earlier legal discussion about why.
DEFAULT_SOURCES = [
    ("The Hindu - National", "https://www.thehindu.com/news/national/feeder/default.rss", "national", 2),
    ("The Hindu - International", "https://www.thehindu.com/news/international/feeder/default.rss", "international", 2),
    ("NDTV Top Stories", "https://feeds.feedburner.com/ndtvnews-top-stories", "general", 2),
    ("Indian Express - India", "https://indianexpress.com/section/india/feed/", "national", 2),
    ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml", "international", 1),
    ("BBC Top Stories", "http://feeds.bbci.co.uk/news/rss.xml", "general", 1),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "international", 1),
    ("NPR News", "https://feeds.npr.org/1001/rss.xml", "international", 2),
    ("TechCrunch", "https://techcrunch.com/feed/", "technology", 2),
    ("ESPN Top Headlines", "https://www.espn.com/espn/rss/news", "sports", 2),
]

DEFAULT_SETTINGS = [
    ("stories_per_edition", "8", "How many stories appear in a daily edition by default"),
    ("min_confidence_score", "0.55", "Below this LLM confidence, a story is auto-flagged for review (used by the confidence_threshold verification layer)"),
    ("cluster_similarity_threshold", "0.25", "Word-overlap threshold (0-1) for grouping articles into one story"),
    ("summary_max_sentences", "3", "Max sentences the LLM should use per story summary"),
    ("outside_bubble_min_stories", "1", "Minimum stories from outside the user's chosen categories, to avoid a filter bubble"),

    ("require_human_approval_all", "true", "If true, EVERY story requires manual admin approval before publishing, even if it passes all verification layers cleanly. Recommended while monetized."),
    ("skip_all_verification", "false", "DANGER: if true, ALL verification layers are bypassed entirely and every story auto-publishes immediately. Overrides require_human_approval_all. Only for trusted testing."),
    ("near_verbatim_similarity_threshold", "0.55", "Word-overlap ratio (0-1) above which a story is flagged as too close to verbatim copying"),
    ("blocked_source_domains", "ani.in,aninews.in,ptinews.com,ptinews.in", "Comma-separated domains that are NEVER fetched even if a source pointing to them is accidentally added and marked active"),

    ("bilingual_generation", "true", "If true, every story is generated in English AND Hindi in a single LLM call. If false, only English is generated."),

    ("scheduling_mode", "auto", "'auto' = the scheduled GitHub Actions cron jobs run normally. 'manual' = scheduled jobs are disabled; only the admin panel's manual buttons trigger ingestion/sending."),
    ("admin_timezone", "Asia/Kolkata", "Timezone used to interpret scheduling-related settings like the final daily ingestion pass"),
    ("final_ingestion_hour", "23", "Local hour (admin_timezone, 24h) for the LAST ingestion pass of the day, capturing news up to midnight - like a newspaper's print deadline"),
    ("email_send_window_start", "06:00", "Informational: the intended start of the daily email send window (individual users can still pick their own send time)"),
    ("email_send_window_end", "07:00", "Informational: the intended end of the daily email send window"),

    ("testing_mode", "false", "If true, a visible banner appears in the admin panel as a reminder that the system is in testing mode. Does not by itself change behavior - use scheduling_mode=manual and the sandbox API for actual test isolation."),
    ("developer_test_email", "", "Email address that developer-triggered test sends go to, instead of any real subscriber. Leave blank to use the developer's own account email."),
]

# Default multi-layer verification pipeline, in execution order. Every layer
# can be toggled, reordered, or marked advisory-only from the admin panel -
# this is just the sensible starting configuration.
DEFAULT_VERIFICATION_LAYERS = [
    ("source_policy", "Source Policy Check", True, True, 0),
    ("citation_completeness", "Citation Completeness", True, True, 1),
    ("near_verbatim_similarity", "Near-Verbatim Similarity Check", True, True, 2),
    ("confidence_threshold", "AI Confidence Threshold", True, True, 3),
    ("independent_ai_verifier", "Independent AI Verifier (Gemini)", True, True, 4),
]

DEFAULT_PLANS = [
    ("free", "Free", 0),
]


def run_seed(db: Session):
    # Categories
    if db.query(models.Category).count() == 0:
        for slug, name, parent, order in DEFAULT_CATEGORIES:
            db.add(models.Category(slug=slug, name=name, parent_slug=parent, sort_order=order))
        logger.info("Seeded default categories")

    # Sources
    if db.query(models.Source).count() == 0:
        for name, url, cat, tier in DEFAULT_SOURCES:
            db.add(models.Source(name=name, rss_url=url, default_category=cat, trust_tier=tier))
        logger.info("Seeded default sources")

    # Settings
    existing_keys = {s.key for s in db.query(models.Setting).all()}
    for key, value, desc in DEFAULT_SETTINGS:
        if key not in existing_keys:
            db.add(models.Setting(key=key, value=value, description=desc))

    # Verification layers
    if db.query(models.VerificationLayer).count() == 0:
        for key, name, enabled, blocking, order in DEFAULT_VERIFICATION_LAYERS:
            db.add(models.VerificationLayer(
                key=key, name=name, is_enabled=enabled, is_blocking=blocking, sort_order=order
            ))
        logger.info("Seeded default verification layers")

    # Plans (stub for future billing)
    if db.query(models.Plan).count() == 0:
        for slug, name, price in DEFAULT_PLANS:
            db.add(models.Plan(slug=slug, name=name, price_cents=price))
        logger.info("Seeded default plans")

    db.commit()

    # First admin account
    admin = db.query(models.User).filter(models.User.email == settings.ADMIN_EMAIL).first()
    if admin is None:
        free_plan = db.query(models.Plan).filter(models.Plan.slug == "free").first()
        admin = models.User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            is_admin=True,
            role="admin",
            onboarded=True,
            plan_id=free_plan.id if free_plan else None,
        )
        db.add(admin)
        db.commit()
        logger.info(f"Created initial admin account: {settings.ADMIN_EMAIL}")


def get_setting(db: Session, key: str, default: str = "") -> str:
    """Central helper - ALWAYS read tunable behavior through this, never hardcode it inline."""
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    return row.value if row else default


def set_setting(db: Session, key: str, value: str, description: str = ""):
    """Central helper for WRITING settings - used both by the admin API and by
    background jobs that need to report their own status (e.g. ingestion progress)."""
    row = db.query(models.Setting).filter(models.Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(models.Setting(key=key, value=value, description=description))
