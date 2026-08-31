"""Fetch and normalize active RSS sources with per-source isolation."""
import datetime
import logging
import re
import feedparser
import httpx
from sqlalchemy.orm import Session
from .. import models

logger = logging.getLogger("morning_brief.ingestion")
MAX_ENTRIES_PER_SOURCE = 15
FETCH_TIMEOUT_SECONDS = 15


class RawArticle:
    __slots__ = ("title", "link", "summary", "source_name", "default_category", "country_code", "trust_tier", "source_legal_risk_level")

    def __init__(self, title, link, summary, source_name, default_category, trust_tier, country_code="IN", source_legal_risk_level="standard"):
        self.title = (title or "").strip()
        self.link = (link or "").strip()
        self.summary = (summary or "").strip()
        self.source_name = source_name
        self.default_category = default_category
        self.country_code = (country_code or "GLOBAL").upper()
        self.trust_tier = trust_tier
        self.source_legal_risk_level = source_legal_risk_level


def _extract_domain(url: str) -> str:
    match = re.search(r"://(?:www\.)?([^/]+)", url or "")
    return match.group(1).lower() if match else ""


def fetch_all_active_sources(db: Session, blocked_domains: set = None) -> list[RawArticle]:
    blocked_domains = blocked_domains or set()
    sources = db.query(models.Source).filter(models.Source.is_active.is_(True)).all()
    articles = []
    for source in sources:
        source_domain = _extract_domain(source.rss_url)
        if source.legal_risk_level == "blocked" or any(source_domain.endswith(d) for d in blocked_domains):
            logger.warning("Skipping blocked source '%s'", source.name)
            continue
        try:
            resp = httpx.get(source.rss_url, timeout=FETCH_TIMEOUT_SECONDS,
                             headers={"User-Agent": "MorningBrief/1.0 (+RSS reader)"}, follow_redirects=True)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            if parsed.bozo and not parsed.entries:
                raise ValueError(f"Feed could not be parsed: {parsed.bozo_exception}")
            count = 0
            for entry in parsed.entries[:MAX_ENTRIES_PER_SOURCE]:
                title = getattr(entry, "title", None)
                link = getattr(entry, "link", None)
                summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                if not title or not link:
                    continue
                articles.append(RawArticle(title, link, summary, source.name,
                    source.default_category, source.trust_tier, source.country_code,
                    source.legal_risk_level))
                count += 1
            source.last_fetched_at = datetime.datetime.utcnow()
            source.last_fetch_error = None
            logger.info("Fetched %s entries from %s", count, source.name)
        except Exception as e:
            source.last_fetch_error = str(e)[:500]
            logger.warning("Failed to fetch source '%s': %s", source.name, e)
    db.commit()
    return articles
