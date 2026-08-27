"""
Compliance / legal-risk verification layer, run on every story BEFORE it is
ever shown to the admin for approval - let alone published to users.

This is deliberately kept as its own module, separate from summarization
(llm/groq_client.py) and clustering (clustering.py), so the checks here can
be audited, tested, and extended independently of how stories are generated.

Nothing in this module makes a final publish decision by itself - it produces
a list of human-readable flags and a similarity score, which the pipeline
then uses (together with the require_human_approval_all setting) to decide
whether a story can be auto-published or must wait for manual approval.
"""
import re

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "is", "are", "was", "were", "as", "by", "from", "after", "before",
    "over", "into", "amid", "says", "say", "said", "will", "it", "its", "his",
    "her", "their", "this", "that", "new", "how", "why", "what",
}


def _tokenize(text: str) -> set:
    words = re.findall(r"[a-zA-Z0-9']+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _word_overlap_ratio(a: set, b: set) -> float:
    """What fraction of the SMALLER set's words also appear in the larger set.
    Deliberately not Jaccard here: a short summary that is 90% identical to a
    30-word slice of a much longer article is a real near-verbatim risk even
    though the Jaccard score would look low due to the size mismatch."""
    if not a or not b:
        return 0.0
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    return len(smaller & larger) / len(smaller)


def compute_max_similarity(summary_text: str, original_snippets: list[str]) -> float:
    """Returns the highest overlap ratio between the generated summary and
    ANY single original source snippet it was built from. This is the actual
    proxy for 'is this a paraphrase or basically a copy' - the real legal
    risk factor, independent of how short the summary is."""
    summary_tokens = _tokenize(summary_text)
    if not summary_tokens:
        return 0.0

    best = 0.0
    for snippet in original_snippets:
        snippet_tokens = _tokenize(snippet)
        ratio = _word_overlap_ratio(summary_tokens, snippet_tokens)
        best = max(best, ratio)
    return round(best, 3)


def check_source_risk(cluster_articles: list, blocked_domains: set) -> tuple[bool, bool]:
    """Returns (is_blocked, is_high_risk) for a cluster, based on the
    legal_risk_level of each article's originating source and the
    blocked-domains safety net."""
    is_blocked = False
    is_high_risk = False
    for article in cluster_articles:
        risk_level = getattr(article, "source_legal_risk_level", "standard")
        if risk_level == "blocked":
            is_blocked = True
        elif risk_level == "high_risk":
            is_high_risk = True

        domain = _extract_domain(getattr(article, "link", ""))
        if domain and any(domain.endswith(blocked) for blocked in blocked_domains):
            is_blocked = True

    return is_blocked, is_high_risk


def _extract_domain(url: str) -> str:
    match = re.search(r"://(?:www\.)?([^/]+)", url or "")
    return match.group(1).lower() if match else ""


def build_verification_flags(
    *,
    confidence: float,
    min_confidence: float,
    max_similarity: float,
    similarity_threshold: float,
    is_high_risk_source: bool,
    has_citations: bool,
) -> list[str]:
    """Central place that turns raw check results into the flag list shown
    directly to the admin. Add new checks here as the product's compliance
    needs grow - never scatter ad-hoc flag strings elsewhere in the codebase."""
    flags = []
    if confidence < min_confidence:
        flags.append("low_confidence")
    if max_similarity >= similarity_threshold:
        flags.append("near_verbatim_risk")
    if is_high_risk_source:
        flags.append("high_risk_source")
    if not has_citations:
        flags.append("no_citations")
    return flags
