"""Fetch and normalize active RSS sources with per-source isolation."""
import calendar, datetime, logging, re
import feedparser, httpx
from sqlalchemy.orm import Session
from .. import models
from ..seed import get_setting

logger = logging.getLogger("morning_brief.ingestion")
FETCH_TIMEOUT_SECONDS = 15

class RawArticle:
    __slots__ = ("title", "link", "summary", "source_name", "default_category", "country_code", "trust_tier", "source_legal_risk_level", "published_at")
    def __init__(self, title, link, summary, source_name, default_category, trust_tier, country_code="IN", source_legal_risk_level="standard", published_at=None):
        self.title=(title or "").strip(); self.link=(link or "").strip(); self.summary=(summary or "").strip()
        self.source_name=source_name; self.default_category=default_category; self.country_code=(country_code or "GLOBAL").upper()
        self.trust_tier=trust_tier; self.source_legal_risk_level=source_legal_risk_level; self.published_at=published_at

def _extract_domain(url):
    match=re.search(r"://(?:www\.)?([^/]+)", url or "")
    return match.group(1).lower() if match else ""

def _entry_time(entry):
    for field in ("published_parsed", "updated_parsed"):
        parsed=getattr(entry, field, None)
        if parsed:
            try: return datetime.datetime.fromtimestamp(calendar.timegm(parsed), tz=datetime.timezone.utc)
            except (TypeError, ValueError, OverflowError): pass
    return None

def fetch_all_active_sources(db: Session, blocked_domains=None, published_after: datetime.datetime | None = None):
    blocked_domains=blocked_domains or set(); max_entries=max(1, min(int(get_setting(db,"max_entries_per_source","15")),100))
    timeout=max(5, min(int(get_setting(db,"source_fetch_timeout_seconds","15")),60))
    if published_after and published_after.tzinfo is None: published_after=published_after.replace(tzinfo=datetime.timezone.utc)
    articles=[]
    for source in db.query(models.Source).filter(models.Source.is_active.is_(True)).all():
        source_domain=_extract_domain(source.rss_url)
        if source.legal_risk_level=="blocked" or any(source_domain.endswith(d) for d in blocked_domains):
            logger.warning("Skipping blocked source '%s'",source.name); continue
        try:
            resp=httpx.get(source.rss_url,timeout=timeout,headers={"User-Agent":"MorningBrief/2.0 (+RSS reader)"},follow_redirects=True)
            resp.raise_for_status(); parsed=feedparser.parse(resp.content)
            if parsed.bozo and not parsed.entries: raise ValueError(f"Feed could not be parsed: {parsed.bozo_exception}")
            count=0
            for entry in parsed.entries[:max_entries]:
                title=getattr(entry,"title",None); link=getattr(entry,"link",None); summary=getattr(entry,"summary","") or getattr(entry,"description","")
                if not title or not link: continue
                published_at=_entry_time(entry)
                # Some valid RSS feeds omit published/updated timestamps. When a
                # freshness checkpoint is configured, do not discard those entries
                # merely because their feed has no timestamp; they still came from
                # the source's current feed and can be deduplicated downstream.
                if published_after is not None and published_at is not None and published_at <= published_after:
                    continue
                articles.append(RawArticle(title,link,summary,source.name,source.default_category,source.trust_tier,source.country_code,source.legal_risk_level,published_at)); count+=1
            source.last_fetched_at=datetime.datetime.utcnow(); source.last_fetch_error=None
            logger.info("Fetched %s entries from %s",count,source.name)
        except Exception as exc:
            source.last_fetch_error=str(exc)[:500]; logger.warning("Failed to fetch source '%s': %s",source.name,exc)
    db.commit(); return articles
