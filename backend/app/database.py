from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Additive, dependency-free migrations for existing deployments. New installs
# receive these fields from Base.metadata.create_all(); existing installs get
# them on the next startup without losing data.
_ADDITIVE_COLUMN_MIGRATIONS = [
    ("sources", "legal_risk_level", "VARCHAR DEFAULT 'standard' NOT NULL"),
    ("sources", "country_code", "VARCHAR DEFAULT 'IN' NOT NULL"),
    ("stories", "publication_status", "VARCHAR DEFAULT 'pending' NOT NULL"),
    ("stories", "verification_flags", "TEXT"),
    ("stories", "max_source_similarity", "FLOAT DEFAULT 0.0 NOT NULL"),
    ("stories", "country_code", "VARCHAR DEFAULT 'GLOBAL' NOT NULL"),
    ("stories", "max_long_phrase_overlap", "FLOAT DEFAULT 0.0 NOT NULL"),
    ("stories", "originality_rewrite_applied", "BOOLEAN DEFAULT FALSE NOT NULL"),
    ("users", "role", "VARCHAR DEFAULT 'user' NOT NULL"),
    ("users", "auth_provider", "VARCHAR DEFAULT 'password' NOT NULL"),
    ("users", "google_sub", "VARCHAR"),
    ("users", "country_code", "VARCHAR DEFAULT 'IN' NOT NULL"),
    ("users", "content_language", "VARCHAR DEFAULT 'en' NOT NULL"),
    ("users", "plan_id", "INTEGER"),
    ("stories", "headline_hi", "VARCHAR"),
    ("stories", "hook_hi", "VARCHAR"),
    ("stories", "summary_hi", "TEXT"),
    ("stories", "is_test_content", "BOOLEAN DEFAULT FALSE NOT NULL"),
    ("stories", "pipeline_stage", "VARCHAR DEFAULT 'draft_generated' NOT NULL"),
    ("stories", "generator_model", "VARCHAR"),
    ("stories", "verifier_model", "VARCHAR"),
    ("stories", "verifier_report", "TEXT"),
    ("stories", "contradiction_flag", "BOOLEAN DEFAULT FALSE NOT NULL"),
    ("stories", "citation_complete", "BOOLEAN DEFAULT TRUE NOT NULL"),
    ("stories", "reviewed_by_user_id", "INTEGER"),
    ("stories", "reviewed_at", "TIMESTAMP"),
    ("stories", "review_notes", "TEXT"),
]


def run_additive_migrations():
    with engine.connect() as conn:
        for table, column, ddl in _ADDITIVE_COLUMN_MIGRATIONS:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                conn.commit()
            except Exception:
                conn.rollback()
