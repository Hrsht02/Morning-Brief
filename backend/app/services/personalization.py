"""Country-aware editorial ranking and service-country fallback.

This module intentionally runs after ingestion, so it never changes what is
fetched or what facts are generated. It only decides which already-approved
stories should be shown first to a particular reader.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SUPPORTED_COUNTRIES = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "SG": "Singapore",
    "AE": "United Arab Emirates",
    "GLOBAL": "Global",
}

# A country is considered locally supported when we have a country-aware
# editorial profile. Unsupported countries safely fall back to GLOBAL rather
# than returning an empty edition.
SUPPORTED_SERVICE_COUNTRIES = set(SUPPORTED_COUNTRIES) - {"GLOBAL"}
DEFAULT_COUNTRY = "IN"


@dataclass(frozen=True)
class CountryResolution:
    requested: str
    effective: str
    supported: bool
    fallback_used: bool


def normalize_country(value: str | None) -> str:
    value = (value or "").strip().upper()
    return value if value in SUPPORTED_COUNTRIES else ""


def resolve_country(value: str | None) -> CountryResolution:
    requested = normalize_country(value) or ""
    if requested in SUPPORTED_SERVICE_COUNTRIES:
        return CountryResolution(requested, requested, True, False)
    # Global is always available. India is the product's default editorial
    # market, but unsupported users should not be misrepresented as Indian.
    return CountryResolution(requested, "GLOBAL", False, bool(requested))


def _country_score(story, effective_country: str) -> float:
    story_country = getattr(story, "country_code", None) or "GLOBAL"
    if story_country == effective_country:
        return 40.0
    if story_country == "GLOBAL":
        return 18.0
    return 0.0


def _category_score(story, preferred_categories: set[str]) -> float:
    return 24.0 if preferred_categories and story.category_slug in preferred_categories else 0.0


def _quality_score(story) -> float:
    confidence = max(0.0, min(1.0, float(getattr(story, "confidence_score", 0.0) or 0.0)))
    # Editorial quality remains meaningful, but country relevance is stronger.
    return confidence * 20.0 + (8.0 if getattr(story, "is_pinned", False) else 0.0)


def rank_stories(stories: Iterable, country_code: str | None, preferred_categories: set[str] | None = None) -> list:
    """Rank approved stories without mutating them.

    Ordering: local-country relevance -> preferred categories -> global/high
    quality -> confidence. India therefore naturally gets India-first results,
    while every supported country receives its own local-first ordering.
    """
    resolution = resolve_country(country_code)
    preferred_categories = preferred_categories or set()

    def score(story):
        return (
            _country_score(story, resolution.effective)
            + _category_score(story, preferred_categories)
            + _quality_score(story)
        )

    return sorted(stories, key=score, reverse=True)


def select_personalized_stories(
    stories: list,
    country_code: str | None,
    preferred_categories: set[str] | None,
    limit: int,
    outside_category_min: int = 1,
) -> tuple[list, CountryResolution]:
    """Select a balanced edition while preventing category filter bubbles."""
    resolution = resolve_country(country_code)
    preferred_categories = preferred_categories or set()
    ranked = rank_stories(stories, resolution.effective, preferred_categories)

    if not preferred_categories:
        return ranked[:limit], resolution

    preferred = [s for s in ranked if s.category_slug in preferred_categories]
    outside = [s for s in ranked if s.category_slug not in preferred_categories]

    selected = preferred[:limit]
    if outside and outside_category_min > 0:
        outside_take = min(outside_category_min, limit)
        selected = selected[: max(0, limit - outside_take)] + outside[:outside_take]
        selected = sorted(selected, key=lambda s: ranked.index(s))

    return selected[:limit], resolution
