"""Independent second-opinion verifier using Google Gemini."""
import json
import logging
import re
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..config import settings

logger = logging.getLogger("morning_brief.verifier")
GEMINI_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SECONDS = 10

VERIFIER_SYSTEM_PROMPT = """You are an independent fact-checking verifier for a news aggregation service. You will be given original source excerpts and a draft summary generated from them. Verify strictly against the excerpts, not outside knowledge.
Check for unsupported claims, contradictions, and substantial copied wording.
Respond with ONLY valid JSON: {\"overall_verdict\": \"SUPPORTED\" or \"UNSUPPORTED_CLAIMS\" or \"CONTRADICTION_FOUND\", \"unsupported_claims\": [\"...\"], \"contradiction_found\": false, \"confidence\": 0.0}."""

class VerifierUnavailableError(Exception):
    pass

def _extract_json(raw_text: str) -> dict:
    text = re.sub(r"^```(json)?", "", raw_text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0) if match else text)

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def _call_gemini(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise VerifierUnavailableError("GEMINI_API_KEY is not set - add it to your .env file")
    url = GEMINI_ENDPOINT_TEMPLATE.format(model=settings.GEMINI_MODEL)
    resp = httpx.post(url, params={"key": settings.GEMINI_API_KEY}, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
    }, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise VerifierUnavailableError(f"Unexpected Gemini response shape: {exc}")

def verify_draft(draft_summary: str, original_snippets: list[str]) -> dict:
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
    except Exception as exc:
        logger.warning("Independent verifier (Gemini) unavailable, story will be held for human review: %s", exc)
        return {"available": False, "overall_verdict": "VERIFIER_UNAVAILABLE", "unsupported_claims": [], "contradiction_found": False, "confidence": 0.0}
