import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base


def utcnow():
    return datetime.datetime.utcnow()


class UserCategory(Base):
    __tablename__ = "user_categories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_slug = Column(String, ForeignKey("categories.slug"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "category_slug", name="uq_user_category"),)


class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    price_cents = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String, default="user", nullable=False)
    auth_provider = Column(String, default="password", nullable=False)
    google_sub = Column(String, unique=True, nullable=True)

    # ISO-3166 alpha-2 country selected by the reader. GLOBAL is represented
    # at ranking time, not stored as a user country.
    country_code = Column(String, default="IN", nullable=False, index=True)
    timezone = Column(String, default="Asia/Kolkata", nullable=False)
    send_hour = Column(Integer, default=6, nullable=False)
    send_minute = Column(Integer, default=0, nullable=False)
    onboarded = Column(Boolean, default=False, nullable=False)
    content_language = Column(String, default="en", nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    last_sent_date = Column(String, nullable=True)
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
    country_code = Column(String, default="IN", nullable=False, index=True)
    trust_tier = Column(Integer, default=2, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_fetched_at = Column(DateTime, nullable=True)
    last_fetch_error = Column(Text, nullable=True)
    legal_risk_level = Column(String, default="standard", nullable=False)


class Story(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True)
    edition_date = Column(String, index=True, nullable=False)
    headline = Column(String, nullable=False)
    hook = Column(String, nullable=True)
    summary = Column(Text, nullable=False)
    headline_hi = Column(String, nullable=True)
    hook_hi = Column(String, nullable=True)
    summary_hi = Column(Text, nullable=True)
    category_slug = Column(String, ForeignKey("categories.slug"), nullable=False, default="general")
    country_code = Column(String, default="GLOBAL", nullable=False, index=True)
    confidence_score = Column(Float, default=0.5, nullable=False)
    needs_review = Column(Boolean, default=False, nullable=False)
    is_published = Column(Boolean, default=True, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_test_content = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    publication_status = Column(String, default="pending", nullable=False)
    pipeline_stage = Column(String, default="draft_generated", nullable=False)
    verification_flags = Column(Text, nullable=True)
    max_source_similarity = Column(Float, default=0.0, nullable=False)
    max_long_phrase_overlap = Column(Float, default=0.0, nullable=False)
    originality_rewrite_applied = Column(Boolean, default=False, nullable=False)
    generator_model = Column(String, nullable=True)
    verifier_model = Column(String, nullable=True)
    verifier_report = Column(Text, nullable=True)
    contradiction_flag = Column(Boolean, default=False, nullable=False)
    citation_complete = Column(Boolean, default=True, nullable=False)
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
    status = Column(String, default="sent")
    error = Column(Text, nullable=True)


class VerificationLayer(Base):
    __tablename__ = "verification_layers"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_blocking = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    config = Column(Text, nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)
    key_hash = Column(String, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    last_used_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
