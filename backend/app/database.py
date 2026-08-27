from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# SQLite needs a special connect arg to work with multiple threads (FastAPI uses a threadpool)
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session and always closes it, even on error."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added to existing tables AFTER the app was already deployed and had
# real data. Base.metadata.create_all() only creates missing TABLES, it never
# alters existing ones - so on an already-running deployment, new columns
# referenced by the ORM would otherwise cause "column does not exist" errors
# on every query. This is a lightweight, dependency-free stand-in for a real
# migration tool (Alembic) - sufficient for a project this size, but a real
# migration tool is worth adopting before the schema grows much further.
_ADDITIVE_COLUMN_MIGRATIONS = [
    ("sources", "legal_risk_level", "VARCHAR DEFAULT 'standard' NOT NULL"),
    ("stories", "publication_status", "VARCHAR DEFAULT 'pending' NOT NULL"),
    ("stories", "verification_flags", "TEXT"),
    ("stories", "max_source_similarity", "FLOAT DEFAULT 0.0 NOT NULL"),
    # --- Multi-layer verification, bilingual content, roles/API keys/audit ---
    ("users", "role", "VARCHAR DEFAULT 'user' NOT NULL"),
    ("users", "auth_provider", "VARCHAR DEFAULT 'password' NOT NULL"),
    ("users", "google_sub", "VARCHAR"),
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
    """Adds any missing columns from the list above. Safe to run on every
    startup - each statement is wrapped so an already-existing column is
    silently skipped rather than raising."""
    with engine.connect() as conn:
        for table, column, ddl in _ADDITIVE_COLUMN_MIGRATIONS:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                conn.commit()
            except Exception:
                # Column already exists (or table doesn't exist yet on a brand
                # new install, in which case create_all() will create it fresh
                # with the column already included) - either way, safe to ignore.
                conn.rollback()
