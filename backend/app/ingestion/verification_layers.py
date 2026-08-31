"""Configurable, fail-closed verification pipeline."""
import logging
from . import verification as v
from ..llm.gemini_client import verify_draft as gemini_verify_draft

logger = logging.getLogger("morning_brief.verification_layers")


def _result(passed: bool, available: bool = True, flags: list = None, details: dict = None) -> dict:
    return {"passed": passed, "available": available, "flags": flags or [], "details": details or {}}


def layer_source_policy(context):
    is_blocked, is_high_risk = v.check_source_risk(context["cluster_articles"], context["blocked_domains"])
    if is_blocked: return _result(False, flags=["blocked_source"])
    if is_high_risk: return _result(False, flags=["high_risk_source"])
    return _result(True)


def layer_citation_completeness(context):
    ok = len(context["cluster_articles"]) > 0
    return _result(ok, flags=[] if ok else ["no_citations"])


def layer_near_verbatim_similarity(context):
    score = v.compute_max_similarity(context["draft"]["summary"], context["original_snippets"])
    context["max_similarity"] = score
    threshold = context["thresholds"].get("near_verbatim_similarity_threshold", 0.55)
    return _result(score < threshold, flags=[] if score < threshold else ["near_verbatim_risk"], details={"similarity": score})


def layer_long_phrase_similarity(context):
    phrase_words = int(context["thresholds"].get("long_phrase_words", 6))
    score = v.compute_max_long_phrase_overlap(context["draft"]["summary"], context["original_snippets"], phrase_words)
    context["max_long_phrase_overlap"] = score
    threshold = context["thresholds"].get("long_phrase_overlap_threshold", 0.20)
    return _result(score < threshold, flags=[] if score < threshold else ["long_phrase_copy_risk"], details={"overlap": score, "phrase_words": phrase_words})


def layer_confidence_threshold(context):
    confidence = context["draft"]["confidence"]
    threshold = context["thresholds"].get("min_confidence_score", 0.55)
    return _result(confidence >= threshold, flags=[] if confidence >= threshold else ["low_confidence"], details={"confidence": confidence})


def layer_independent_ai_verifier(context):
    verdict = gemini_verify_draft(context["draft"]["summary"], context["original_snippets"])
    context["verifier_report"] = verdict
    if not verdict["available"]: return _result(False, available=False, flags=["verifier_unavailable"], details=verdict)
    flags = []
    if verdict["overall_verdict"] == "UNSUPPORTED_CLAIMS": flags.append("unsupported_claims")
    if verdict["contradiction_found"]: flags.append("contradiction_found")
    return _result(not flags, flags=flags, details=verdict)


LAYER_REGISTRY = {
    "source_policy": layer_source_policy,
    "citation_completeness": layer_citation_completeness,
    "near_verbatim_similarity": layer_near_verbatim_similarity,
    "long_phrase_similarity": layer_long_phrase_similarity,
    "confidence_threshold": layer_confidence_threshold,
    "independent_ai_verifier": layer_independent_ai_verifier,
}


def run_verification_pipeline(enabled_layers, context):
    all_flags, must_hold, layer_results = [], False, {}
    for layer_row in enabled_layers:
        fn = LAYER_REGISTRY.get(layer_row.key)
        if fn is None:
            logger.warning("Enabled verification layer '%s' is not implemented", layer_row.key)
            continue
        try:
            result = fn(context)
        except Exception as exc:
            logger.error("Verification layer '%s' failed: %s", layer_row.key, exc)
            result = _result(False, available=False, flags=[f"{layer_row.key}_error"])
        layer_results[layer_row.key] = result
        all_flags.extend(result["flags"])
        if layer_row.is_blocking and (not result["passed"] or not result["available"]): must_hold = True
    return {"all_flags": list(dict.fromkeys(all_flags)), "must_hold": must_hold, "layer_results": layer_results}
