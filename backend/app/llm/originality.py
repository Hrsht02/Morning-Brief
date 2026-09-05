"""Groq-powered originality rewrite used when a generated draft is too close to source phrasing."""
import json
import logging
import re
import time
import httpx
from ..config import settings

logger = logging.getLogger("morning_brief.originality")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 10

PROMPT = """Rewrite the supplied news summary into genuinely original editorial language.
Preserve ONLY facts present in the supplied source snippets. Do not add facts, quotes,
numbers, opinions, predictions, or attribution that is not supported. Do not preserve
distinctive source wording, phrases, or sentence structure. Rebuild the summary from
the facts rather than paraphrasing sentence-by-sentence. Keep names, dates, numbers
and factual meaning accurate. Prefer a different ordering of facts when clear and
faithful. Keep it concise and within {max_sentences} sentences. Return JSON only:
{{\"summary\":\"...\"}}.
Summary: {summary}
Source snippets: {sources}"""


def rewrite_for_originality(summary: str, source_snippets: list[str], max_sentences: int = 3) -> str | None:
    if not settings.GROQ_API_KEY or not summary.strip():
        return None
    sources = "\n---\n".join(s[:900] for s in source_snippets[:5])
    prompt = PROMPT.format(summary=summary[:1800], sources=sources, max_sentences=max_sentences)
    payload = {"model": settings.GROQ_MODEL, "messages": [
        {"role": "system", "content": "You are an originality editor. Facts must remain unchanged."},
        {"role": "user", "content": prompt}], "temperature": 0.55, "max_tokens": 700,
        "reasoning_effort": "low", "response_format": {"type": "json_object"}}
    try:
        for attempt in range(2):
            response = httpx.post(ENDPOINT, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 429:
                response.raise_for_status()
                data = response.json()
                raw = data["choices"][0]["message"].get("content", "")
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                result = json.loads(match.group(0) if match else raw)
                rewritten = str(result.get("summary", "")).strip()
                return rewritten[:1800] if rewritten else None
            if attempt == 0:
                retry_after = response.headers.get("retry-after")
                try:
                    wait_seconds = min(float(retry_after), 5.0) if retry_after else 5.0
                except ValueError:
                    wait_seconds = 5.0
                logger.warning("Groq originality rate limit; retrying after %.1fs", wait_seconds)
                time.sleep(wait_seconds)
        return None
    except Exception as exc:
        logger.warning("Originality rewrite unavailable: %s", exc)
        return None
