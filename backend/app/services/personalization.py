"""Country-aware editorial ranking and strict category personalization."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

SUPPORTED_COUNTRIES={"IN":"India","US":"United States","GB":"United Kingdom","CA":"Canada","AU":"Australia","SG":"Singapore","AE":"United Arab Emirates","GLOBAL":"Global"}
SUPPORTED_SERVICE_COUNTRIES=set(SUPPORTED_COUNTRIES)-{"GLOBAL"}

@dataclass(frozen=True)
class CountryResolution:
    requested:str; effective:str; supported:bool; fallback_used:bool

def normalize_country(value):
    value=(value or "").strip().upper(); return value if value in SUPPORTED_COUNTRIES else ""

def resolve_country(value):
    requested=normalize_country(value)
    if requested in SUPPORTED_SERVICE_COUNTRIES: return CountryResolution(requested,requested,True,False)
    return CountryResolution(requested,"GLOBAL",False,bool(requested))

def _country_score(story,effective):
    c=getattr(story,"country_code",None) or "GLOBAL"
    if c==effective:return 40.0
    if c=="GLOBAL":return 18.0
    return 0.0

def _category_score(story,preferred): return 24.0 if preferred and story.category_slug in preferred else 0.0

def _quality_score(story):
    confidence=max(0.0,min(1.0,float(getattr(story,"confidence_score",0.0) or 0.0)))
    return confidence*20.0+(8.0 if getattr(story,"is_pinned",False) else 0.0)

def rank_stories(stories:Iterable,country_code,preferred_categories=None):
    resolution=resolve_country(country_code); preferred_categories=preferred_categories or set()
    return sorted(stories,key=lambda s:_country_score(s,resolution.effective)+_category_score(s,preferred_categories)+_quality_score(s),reverse=True)

def select_personalized_stories(stories:list,country_code,preferred_categories,limit=None,outside_category_min=0,min_confidence=0.40):
    """Return all matching stories by default; selected categories are strict.

    An empty preference set means the user wants the default/all-news view.
    When categories are selected, stories outside those categories are never
    inserted just to fill a quota.
    """
    resolution=resolve_country(country_code); preferred_categories=preferred_categories or set()
    quality=[s for s in stories if float(getattr(s,"confidence_score",0) or 0)>=min_confidence]
    if not quality: quality=list(stories)
    if resolution.supported:
        relevant=[s for s in quality if (getattr(s,"country_code",None) or "GLOBAL") in {resolution.effective,"GLOBAL"}]
        if relevant: quality=relevant
    ranked=rank_stories(quality,resolution.effective,preferred_categories)
    if preferred_categories:
        ranked=[s for s in ranked if s.category_slug in preferred_categories]
    if limit is None or int(limit)<=0:return ranked,resolution
    return ranked[:int(limit)],resolution
