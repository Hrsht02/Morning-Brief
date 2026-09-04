import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from .database import Base


class SourceCompliance(Base):
    __tablename__ = "source_compliance"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), unique=True, nullable=False)
    tos_url = Column(String, nullable=True)
    licence_status = Column(String, default="unreviewed", nullable=False)
    terms_reviewed_at = Column(DateTime, nullable=True)
    usage_notes = Column(Text, nullable=True)
    reviewer = Column(String, nullable=True)
    active_for_commercial_use = Column(Boolean, default=False, nullable=False)


class ContentReport(Base):
    __tablename__ = "content_reports"
    id = Column(Integer, primary_key=True)
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="SET NULL"), nullable=True)
    reporter_email = Column(String, nullable=True)
    reason = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    status = Column(String, default="open", nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class UserConsent(Base):
    __tablename__ = "user_consents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    email_news_opt_in = Column(Boolean, default=False, nullable=False)
    consent_version = Column(String, nullable=True)
    consented_at = Column(DateTime, nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
