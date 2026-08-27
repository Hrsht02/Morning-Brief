"""
The configurable verification pipeline itself. Each function here is a
"layer" that can be independently enabled/disabled/reordered/marked
blocking-or-advisory from the admin panel (see the VerificationLayer table
and routers/admin.py). Nothing about WHICH checks run, or in what order, or
whether a failure blocks publication, is hardcoded - it's all driven by
whatever rows exist in the verification_layers table.

Every layer function has the same signature and return shape, so adding a
new layer later is: (1) write a function here, (2) register it in
LAYER_REGISTRY, (3) let the admin add a row for it. No pipeline code changes.

FAIL-CLOSED PRINCIPLE: if a layer cannot determine an answer (network down,
API unavailable, bad config), it must return available=False, NEVER
passed=True. An unavailable blocking layer holds the story for human review,
exactly like a failed one - "we couldn't check" is not the same as "it's fine".
"""
import logging
from . import verification as v
from ..llm.gemini_client import verify_draft as gemini_verify_draft

logger = logging.getLogger("morning_brief.verification_layers")


def _result(passed: bool, available: bool = True, flags: list = None, details: dict = None) -> dict:
    return {"passed": passed, "available": available, "flags": flags or [], "details": details or {}}


def layer_source_policy(context: dict) -> dict:
    """Blocked/high-risk source check. Blocked sources should already be
    filtered at fetch time - this is a second, independent check (defense in
    depth) in case a cluster ever mixes sources of different risk levels."""
    is_blocked, is_high_risk = v.check_source_risk(context["cluster_articles"], context["blocked_domains"])
    if is_blocked:
        return _result(passed=False, flags=["blocked_source"], details={"blocked": True})
    if is_high_risk:
        return _result(passed=False, flags=["high_risk_source"], details={"high_risk": True})
    return _result(passed=True)


def layer_citation_completeness(context: dict) -> dict:
    has_citations = len(context["cluster_articles"]) > 0
    if not has_citations:
        return _result(passed=False, flags=["no_citations"])
    return _result(passed=True)


def layer_near_verbatim_similarity(context: dict) -> dict:
    max_similarity = v.compute_max_similarity(context["draft"]["summary"], context["original_snippets"])
    context["max_similarity"] = max_similarity  # stash for the pipeline to persist on the Story row
    threshold = context["thresholds"].get("near_verbatim_similarity_threshold", 0.55)
    if max_similarity >= threshold:
        return _result(passed=False, flags=["near_verbatim_risk"], details={"similarity": max_similarity})
    return _result(passed=True, details={"similarity": max_similarity})


def layer_confidence_threshold(context: dict) -> dict:
    confidence = context["draft"]["confidence"]
    min_confidence = context["thresholds"].get("min_confidence_score", 0.55)
    if confidence < min_confidence:
        return _result(passed=False, flags=["low_confidence"], details={"confidence": confidence})
    return _result(passed=True, details={"confidence": confidence})


def layer_independent_ai_verifier(context: dict) -> dict:
    """LLM #2 - a different provider (Gemini) from the generator (Groq),
    checking the draft against the original source material independently."""
    verdict = gemini_verify_draft(context["draft"]["summary"], context["original_snippets"])
    context["verifier_report"] = verdict  # stash for the pipeline to persist on the Story row

    if not verdict["available"]:
        # Fail closed: an unreachable verifier is NOT the same as a passing one.
        return _result(passed=False, available=False, flags=["verifier_unavailable"], details=verdict)

    flags = []
    if verdict["overall_verdict"] == "UNSUPPORTED_CLAIMS":
        flags.append("unsupported_claims")
    if verdict["contradiction_found"]:
        flags.append("contradiction_found")

    return _result(passed=(len(flags) == 0), details=verdict, flags=flags)


# Registry: DB rows reference layers by this key. Add new layers here as the
# product's compliance needs grow - the pipeline never needs to change.
LAYER_REGISTRY = {
    "source_policy": layer_source_policy,
    "citation_completeness": layer_citation_completeness,
    "near_verbatim_similarity": layer_near_verbatim_similarity,
    "confidence_threshold": layer_confidence_threshold,
    "independent_ai_verifier": layer_independent_ai_verifier,
}


def run_verification_pipeline(enabled_layers: list, context: dict) -> dict:
    """
    enabled_layers: list of VerificationLayer ORM rows (already filtered to
    is_enabled=True and ordered by sort_order) - i.e. exactly what the admin
    has configured right now.

    Returns: {"all_flags": [...], "must_hold": bool, "layer_results": {...}}
    must_hold=True means at least one BLOCKING layer failed or was
    unavailable - the story cannot auto-approve regardless of other settings.
    """
    all_flags = []
    must_hold = False
    layer_results = {}

    for layer_row in enabled_layers:
        fn = LAYER_REGISTRY.get(layer_row.key)
        if fn is None:
            logger.warning(f"Verification layer '{layer_row.key}' is enabled in settings but not implemented - skipping")
            continue

        try:
            result = fn(context)
        except Exception as e:
            # A layer crashing is exactly the "unavailable" case, not a pass.
            logger.error(f"Verification layer '{layer_row.key}' raised an unexpected error: {e}")
            result = _result(passed=False, available=False, flags=[f"{layer_row.key}_error"])

        layer_results[layer_row.key] = result
        all_flags.extend(result["flags"])

        if layer_row.is_blocking and (not result["passed"] or not result["available"]):
            must_hold = True

    return {"all_flags": all_flags, "must_hold": must_hold, "layer_results": layer_results}
