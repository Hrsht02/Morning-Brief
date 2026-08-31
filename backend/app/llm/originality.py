"""Groq-powered originality rewrite used when a generated draft is too close to source phrasing."""
import json
import logging
import re
import time
import httpx
from ..config import settings

logger = logging.getLogger("morning_brief.originality")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

PROMPT = """Rewrite the supplied news summary into genuinely original editorial language.
Preserve ONLY facts present in the supplied source snippets. Do not add facts,
quotes, numbers, opinions, predictions, or attribution that is not supported.
Do not preserve distinctive source wording or sentence structure. Keep the
meaning, names, dates, and numbers accurate. Return JSON only: {\"summary\":\"...\"}.
Summary: {summary}
Source snippets: {sources}"""


def rewrite_for_originality(summary: str, source_snippets: list[str], max_sentences: int = 3) -> str | None:
    if not settings.GROQ_API_KEY or not summary.strip():
        return None
    sources = "\n---\n".join(s[:900] for s in source_snippets[:5])
    prompt = PROMPT.format(summary=summary[:1800], sources=sources)
    try:
        response = httpx.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            json={
                "model": settings.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You are an originality editor. Facts must remain unchanged."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.25,
                "max_tokens": 700,
                "reasoning_effort": "low",
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            try: time.sleep(min(float(retry_after), 30.0)) if retry_after else time.sleep(10)
            except ValueError: time.sleep(10)
            response = httpx.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={"model": settings.GROQ_MODEL, "messages":[
                    {"role":"system","content":"You are an originality editor. Facts must remain unchanged."},
                    {"role":"user","content":prompt}], "temperature":0.25, "max_tokens":700,
                    "reasoning_effort":"low", "response_format":{"type":"json_object"}}, timeout=30)
        response.raise_for_status()
        data = response.json()
        raw = data["choices"][0]["message"].get("content", "")
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(match.group(0) if match else raw)
        rewritten = str(result.get("summary", "")).strip()
        return rewritten[:1800] if rewritten else None
    except Exception as exc:
        logger.warning("Originality rewrite unavailable: %s", exc)
        return None
