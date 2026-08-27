"""
Independent second-opinion verifier, using Google Gemini - deliberately a
DIFFERENT provider/account from Groq (the generator). This is the actual
point of having two models: the verifier is checking the generator's work,
not grading its own homework.

Free tier, no credit card: https://aistudio.google.com/apikey

Follows the same fail-closed principle as the rest of the verification layer:
if the verifier is unreachable, returns unavailable=True rather than silently
treating the story as verified. The pipeline is responsible for turning an
unavailable verifier into a "hold for human review" outcome, never a pass.
"""
import json
import logging
import re
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..config import settings

logger = logging.getLogger("morning_brief.verifier")

GEMINI_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 30

VERIFIER_SYSTEM_PROMPT = """You are an independent fact-checking verifier for a news aggregation \
service. You will be given: (1) a set of ORIGINAL source excerpts about a real-world event, and \
(2) a DRAFT summary that another AI generated from those excerpts. Your job is to verify the draft \
strictly against the original excerpts - not against your own outside knowledge.

Check for:
- Any claim in the draft NOT supported by the original excerpts (unsupported claim)
- Any contradiction between the draft and the original excerpts
- Whether the draft appears to copy substantial wording rather than paraphrase

Respond with ONLY valid JSON, no markdown fences, in this exact shape:
{"overall_verdict": "SUPPORTED" or "UNSUPPORTED_CLAIMS" or "CONTRADICTION_FOUND",
 "unsupported_claims": ["..."], "contradiction_found": false, "confidence": 0.0}

confidence is your 0.0-1.0 confidence in the verdict itself, based on how clear the source material is.
"""


class VerifierUnavailableError(Exception):
    """Raised when the verifier could not be reached or gave an unparseable
    response. The caller MUST treat this as 'hold for review', never as pass."""
    pass


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def _call_gemini(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise VerifierUnavailableError("GEMINI_API_KEY is not set - add it to your .env file")

    url = GEMINI_ENDPOINT_TEMPLATE.format(model=settings.GEMINI_MODEL)
    resp = httpx.post(
        url,
        params={"key": settings.GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise VerifierUnavailableError(f"Unexpected Gemini response shape: {e}")


def verify_draft(draft_summary: str, original_snippets: list[str]) -> dict:
    """
    Returns a structured verdict dict:
    {overall_verdict, unsupported_claims, contradiction_found, confidence, available: True}

    On ANY failure (network, parsing, missing key), returns available=False -
    the caller must treat this as a blocking hold, not a pass, per the
    fail-closed principle.
    """
    sources_text = "\n\n".join(f"Original excerpt {i+1}: {s[:500]}" for i, s in enumerate(original_snippets[:5]))
    prompt = f"{VERIFIER_SYSTEM_PROMPT}\n\n{sources_text}\n\nDRAFT SUMMARY TO VERIFY:\n{draft_summary}"

    try:
        raw = _call_gemini(prompt)
        result = _extract_json(raw)
        return {
            "available": True,
            "overall_verdict": str(result.get("overall_verdict", "UNSUPPORTED_CLAIMS")),
            "unsupported_claims": result.get("unsupported_claims", []) if isinstance(result.get("unsupported_claims"), list) else [],
            "contradiction_found": bool(result.get("contradiction_found", False)),
            "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.5)))),
        }
    except Exception as e:
        logger.warning(f"Independent verifier (Gemini) unavailable, story will be held for human review: {e}")
        return {
            "available": False,
            "overall_verdict": "VERIFIER_UNAVAILABLE",
            "unsupported_claims": [],
            "contradiction_found": False,
            "confidence": 0.0,
        }
