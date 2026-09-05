"""Deterministic source-similarity and editorial safety checks."""
import re
from difflib import SequenceMatcher

STOPWORDS = {"a","an","the","and","or","but","of","in","on","at","to","for","with","is","are","was","were","as","by","from","after","before","over","into","amid","says","say","said","will","it","its","his","her","their","this","that","new","how","why","what"}


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9']+", (text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def _word_jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _bigram_precision(a: list[str], b: list[str]) -> float:
    """Fraction of generated adjacent word pairs also found in the source."""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    source_bigrams = set(zip(b, b[1:]))
    generated_bigrams = set(zip(a, a[1:]))
    return len(generated_bigrams & source_bigrams) / len(generated_bigrams)


def _similarity_score(summary_tokens: list[str], source_tokens: list[str]) -> float:
    """Measure wording similarity without treating subset overlap as 100%.

    The previous metric divided the intersection by the *smaller* token set.
    A normal generated summary is usually shorter than its source, so using the
    smaller set made a summary that merely reused many source terms look 100%
    similar.  This score combines sequence similarity, Jaccard overlap and
    contiguous-bigram reuse. Exact copies can still reach 1.0, while a shorter
    summary that uses common source vocabulary no longer automatically does.
    """
    if not summary_tokens or not source_tokens:
        return 0.0
    sequence = SequenceMatcher(None, summary_tokens, source_tokens, autojunk=False).ratio()
    jaccard = _word_jaccard(set(summary_tokens), set(source_tokens))
    bigram_precision = _bigram_precision(summary_tokens, source_tokens)
    combined = (0.50 * sequence) + (0.20 * jaccard) + (0.30 * bigram_precision)
    return min(1.0, combined)


def compute_max_similarity(summary_text: str, original_snippets: list[str]) -> float:
    summary_tokens = _tokenize(summary_text)
    if not summary_tokens:
        return 0.0
    scores = (_similarity_score(summary_tokens, _tokenize(s)) for s in original_snippets)
    return round(max(scores, default=0.0), 3)


def compute_max_long_phrase_overlap(summary_text: str, original_snippets: list[str], phrase_words: int = 6) -> float:
    """Detect copied long phrases, which word-overlap alone can miss.

    Returns the fraction of generated n-grams that occur verbatim in a source.
    A 6-word contiguous match is a strong editorial copying signal even when
    the overall summary similarity is modest.
    """
    tokens = _tokenize(summary_text)
    if len(tokens) < phrase_words:
        return 0.0
    summary_phrases = {" ".join(tokens[i:i+phrase_words]) for i in range(len(tokens)-phrase_words+1)}
    if not summary_phrases:
        return 0.0
    best = 0.0
    for source in original_snippets:
        src = _tokenize(source)
        src_phrases = {" ".join(src[i:i+phrase_words]) for i in range(len(src)-phrase_words+1)}
        if src_phrases:
            best = max(best, len(summary_phrases & src_phrases) / len(summary_phrases))
    return round(best, 3)


def check_source_risk(cluster_articles: list, blocked_domains: set) -> tuple[bool, bool]:
    is_blocked = is_high_risk = False
    for article in cluster_articles:
        risk_level = getattr(article, "source_legal_risk_level", "standard")
        if risk_level == "blocked": is_blocked = True
        elif risk_level == "high_risk": is_high_risk = True
        domain = _extract_domain(getattr(article, "link", ""))
        if domain and any(domain.endswith(blocked) for blocked in blocked_domains): is_blocked = True
    return is_blocked, is_high_risk


def _extract_domain(url: str) -> str:
    match = re.search(r"://(?:www\.)?([^/]+)", url or "")
    return match.group(1).lower() if match else ""


def build_verification_flags(*, confidence: float, min_confidence: float, max_similarity: float,
                             similarity_threshold: float, is_high_risk_source: bool,
                             has_citations: bool, max_long_phrase_overlap: float = 0.0,
                             long_phrase_threshold: float = 0.20) -> list[str]:
    flags = []
    if confidence < min_confidence: flags.append("low_confidence")
    if max_similarity >= similarity_threshold: flags.append("near_verbatim_risk")
    if max_long_phrase_overlap >= long_phrase_threshold: flags.append("long_phrase_copy_risk")
    if is_high_risk_source: flags.append("high_risk_source")
    if not has_citations: flags.append("no_citations")
    return flags
