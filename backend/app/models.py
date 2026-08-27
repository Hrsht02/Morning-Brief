import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


def utcnow():
    return datetime.datetime.utcnow()


# Many-to-many: which categories a user is subscribed to
class UserCategory(Base):
    __tablename__ = "user_categories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_slug = Column(String, ForeignKey("categories.slug"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "category_slug", name="uq_user_category"),)


class Plan(Base):
    """
    Deliberately minimal stub so a future subscription/payment feature never
    requires a schema rewrite - just add real gating logic that reads
    user.plan.slug. Nothing in the app enforces plan limits today; this exists
    purely so the extension point is already there.
    """
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)  # e.g. "free", "pro"
    name = Column(String, nullable=False)
    price_cents = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)  # Google-only accounts get a random unusable hash - see auth.py
    is_admin = Column(Boolean, default=False, nullable=False)  # kept for backward compatibility; role is authoritative
    is_active = Column(Boolean, default=True, nullable=False)

    # "user" | "developer" | "admin". Kept separate from is_admin (above) so
    # existing code checking is_admin keeps working, while new role-based
    # checks (developer sandbox access, etc.) use this richer field.
    role = Column(String, default="user", nullable=False)

    # "password" | "google" - how this account authenticates.
    auth_provider = Column(String, default="password", nullable=False)
    google_sub = Column(String, unique=True, nullable=True)  # Google's stable user ID, if signed up via Google

    timezone = Column(String, default="Asia/Kolkata", nullable=False)
    send_hour = Column(Integer, default=6, nullable=False)   # 0-23, local time - default sits in the 6-7AM window
    send_minute = Column(Integer, default=0, nullable=False)  # 0-59
    onboarded = Column(Boolean, default=False, nullable=False)

    # "en" | "hi" - which language this user reads content in. Falls back to
    # English automatically if a Hindi variant wasn't generated for a story.
    content_language = Column(String, default="en", nullable=False)

    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)  # stub for future billing, unused today

    created_at = Column(DateTime, default=utcnow)
    last_sent_date = Column(String, nullable=True)  # "YYYY-MM-DD" - prevents duplicate sends

    categories = relationship("UserCategory", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    slug = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    parent_slug = Column(String, ForeignKey("categories.slug"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    rss_url = Column(String, nullable=False, unique=True)
    default_category = Column(String, ForeignKey("categories.slug"), nullable=True)
    trust_tier = Column(Integer, default=2, nullable=False)  # 1=wire service, 2=major outlet, 3=niche
    is_active = Column(Boolean, default=True, nullable=False)
    last_fetched_at = Column(DateTime, nullable=True)
    last_fetch_error = Column(Text, nullable=True)

    # "standard" = normal ingestion. "high_risk" = always requires human approval
    # regardless of confidence (e.g. wire services known to be litigious about
    # commercial reuse). "blocked" = never fetched at all, even if is_active=True -
    # a hard safety net so a mistaken re-activation can't slip content through.
    legal_risk_level = Column(String, default="standard", nullable=False)


class Story(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True)
    edition_date = Column(String, index=True, nullable=False)  # "YYYY-MM-DD"
    headline = Column(String, nullable=False)          # English (base language, always populated)
    hook = Column(String, nullable=True)                # English one-line teaser for the email
    summary = Column(Text, nullable=False)              # English

    # Hindi variants - populated only when bilingual generation is enabled.
    # Nullable by design: a Hindi-preferring user just sees the English
    # version if these are empty, rather than the story disappearing.
    headline_hi = Column(String, nullable=True)
    hook_hi = Column(String, nullable=True)
    summary_hi = Column(Text, nullable=True)

    category_slug = Column(String, ForeignKey("categories.slug"), nullable=False, default="general")
    confidence_score = Column(Float, default=0.5, nullable=False)
    needs_review = Column(Boolean, default=False, nullable=False)
    is_published = Column(Boolean, default=True, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)  # admin can pin breaking news to top
    is_test_content = Column(Boolean, default=False, nullable=False)  # generated via a developer test run - never shown to real users
    created_at = Column(DateTime, default=utcnow)

    # Final publication gate. Values: "pending" | "approved" | "rejected".
    # A story is only ever shown to users / emailed when publication_status="approved"
    # AND is_published=True - the two are kept in sync by the pipeline/admin actions.
    publication_status = Column(String, default="pending", nullable=False)

    # Informational, more granular pipeline state for the admin's benefit -
    # does NOT gate publication by itself (publication_status does that).
    # e.g. "draft_generated" -> "ai_verified" -> "rules_checked" -> "pending_human_review"
    pipeline_stage = Column(String, default="draft_generated", nullable=False)

    # JSON-encoded list of human-readable flags explaining WHY a story needs
    # review, e.g. ["near_verbatim_risk", "high_risk_source", "verifier_unavailable"].
    verification_flags = Column(Text, nullable=True)

    # Highest word-overlap ratio (0-1) between the AI summary and any single
    # original source snippet - the near-verbatim / copying risk proxy.
    max_source_similarity = Column(Float, default=0.0, nullable=False)

    # Independent second-opinion verifier (separate model/provider from the
    # generator) output, stored as raw JSON for full auditability.
    generator_model = Column(String, nullable=True)
    verifier_model = Column(String, nullable=True)
    verifier_report = Column(Text, nullable=True)       # raw JSON string of the verifier's structured verdict
    contradiction_flag = Column(Boolean, default=False, nullable=False)
    citation_complete = Column(Boolean, default=True, nullable=False)

    # Human decision audit trail directly on the story, for quick reference
    # (the full history also lives in AuditLog).
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)

    citations = relationship("Citation", cascade="all, delete-orphan", backref="story")


class Citation(Base):
    __tablename__ = "citations"
    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    source_name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    url = Column(String, nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String, nullable=True)


class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    edition_date = Column(String, nullable=False)
    sent_at = Column(DateTime, default=utcnow)
    status = Column(String, default="sent")  # sent | failed
    error = Column(Text, nullable=True)


class VerificationLayer(Base):
    """
    Every row here is one step in the publication pipeline. Admin can enable,
    disable, reorder, and mark any layer as blocking or advisory-only - the
    pipeline reads this table fresh on every run rather than having any
    verification logic hardcoded into a fixed sequence.
    """
    __tablename__ = "verification_layers"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)   # matches a registered Python function - see verification_layers.py
    name = Column(String, nullable=False)                # human-readable, shown in the admin UI
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_blocking = Column(Boolean, default=True, nullable=False)  # if True, a failure here forces "pending" and can never auto-approve
    sort_order = Column(Integer, default=0, nullable=False)
    config = Column(Text, nullable=True)  # optional JSON string for layer-specific settings (e.g. custom thresholds)


class ApiKey(Base):
    """Issued to developers for programmatic access to the sandboxed /api/v1/test/*
    endpoints. Never grants access to real user data or the ability to email
    real subscribers - see routers/api_v1.py for exactly what a key can do."""
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)                 # admin-chosen label, e.g. "Dev laptop key"
    key_prefix = Column(String, nullable=False)            # first 8 chars, shown in the UI so admin can identify a key without re-exposing it
    key_hash = Column(String, nullable=False)              # bcrypt hash of the full key - the raw key is shown ONCE at creation and never stored
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    last_used_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    """Generic audit trail for anything worth being able to reconstruct later:
    source risk changes, story approve/reject decisions, API key issuance,
    developer account creation, verification layer toggles, etc."""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)   # "story" | "source" | "user" | "api_key" | "verification_layer" | "setting"
    entity_id = Column(String, nullable=True)
    action = Column(String, nullable=False)        # "approved" | "rejected" | "created" | "updated" | "deleted" | ...
    actor = Column(String, nullable=False)          # "user:<id>" | "system" | "api_key:<id>"
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
