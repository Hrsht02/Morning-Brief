"""Conservative editorial safety gates for automatic publication.

This module is an engineering control layer, not legal advice. It keeps
similarity as a necessary-but-not-sufficient condition and routes only
exceptional/high-risk reporting to human review.
"""
import re

SENSITIVE_RULES = {
    "crime_corruption_wrongdoing": re.compile(r"\b(arrested|arrest|accused|alleged|allegedly|corruption|bribery|fraud|scam|scandal|murder|rape|sexual assault|terror|terrorist|money laundering|embezzlement|graft|criminal case|crime)\b", re.I),
    "sub_judice": re.compile(r"\b(court|supreme court|high court|tribunal|hearing|petition|lawsuit|litigation|bail|convicted|conviction|sentenced|judgment|judgement|sub judice)\b", re.I),
    "sensitive_election": re.compile(r"\b(election fraud|vote rigging|voter fraud|poll rigging|poll violence|election violence|voter intimidation|booth capturing|model code violation|election code violation|campaign finance violation|electoral misconduct|fake voting|ballot tampering|ballot fraud|hacked voting machine|election manipulation|election dispute|election petition|election-related violence)\b", re.I),
    "communal_religious_caste": re.compile(r"\b(communal violence|religious violence|caste violence|caste conflict|hate speech|religious hatred|communal tension|caste discrimination|religious conflict)\b", re.I),
    "health_medical": re.compile(r"\b(cancer|covid|disease|virus|vaccine|drug|medicine|treatment|therapy|medical|hospital|doctor|health|clinical|symptom|death rate)\b", re.I),
    "financial_market": re.compile(r"\b(stock|stocks|share price|shares|market|markets|nifty|sensex|sebi|investment|investor|trading|trader|ipo|mutual fund|bond|crypto|cryptocurrency|financial advice)\b", re.I),
    "minors": re.compile(r"\b(child|children|minor|juvenile|teenager|teen|schoolgirl|schoolboy)\b", re.I),
    "self_harm": re.compile(r"\b(suicide|self[- ]harm|self harm|attempted suicide)\b", re.I),
}


def sensitive_flags(text: str) -> list[str]:
    return [f"sensitive_{name}" for name, pattern in SENSITIVE_RULES.items() if pattern.search(text or "")]


def contains_named_entity_risk(text: str) -> bool:
    return bool(re.search(r"\b(?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+\b", text or ""))


def mandatory_human_review(text: str, source_count: int, verifier_report: dict | None,
                           max_similarity: float, auto_threshold: float) -> tuple[bool, list[str]]:
    """Return hard review triggers plus advisory flags.

    Single-source reporting is recorded for editorial awareness but is not
    itself a mandatory-review trigger. Routine politics/election reporting is
    also not a hard trigger; only materially sensitive political/election
    patterns are. Similarity remains a copy/novelty signal, never a legal safe
    harbor.
    """
    flags = sensitive_flags(text)
    if contains_named_entity_risk(text) and flags:
        flags.append("named_entity_sensitive_context")
    if source_count < 2:
        flags.append("single_source_story")
    if verifier_report:
        if verifier_report.get("available") is False:
            flags.append("verifier_unavailable")
        if verifier_report.get("overall_verdict") in {"LOW_CONFIDENCE", "UNSUPPORTED_CLAIMS"}:
            flags.append("verifier_low_confidence")
        if verifier_report.get("contradiction_found"):
            flags.append("contradiction_found")
    hard_flags = [f for f in flags if f != "single_source_story"]
    return bool(hard_flags), flags
