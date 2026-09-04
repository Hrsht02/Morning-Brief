"""Sends transactional email via Brevo's HTTP API."""
import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..config import settings

logger = logging.getLogger("morning_brief.email")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
REQUEST_TIMEOUT_SECONDS = 20

class EmailSendError(Exception): pass

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6), retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)), reraise=True)
def send_email(to_email: str, subject: str, html_content: str) -> None:
    if not settings.BREVO_API_KEY: raise EmailSendError("BREVO_API_KEY is not set - add it to your .env file")
    resp = httpx.post(BREVO_ENDPOINT, headers={"api-key": settings.BREVO_API_KEY, "Content-Type": "application/json", "Accept": "application/json"}, json={"sender": {"name": settings.EMAIL_FROM_NAME, "email": settings.EMAIL_FROM_ADDRESS}, "to": [{"email": to_email}], "subject": subject, "htmlContent": html_content}, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code >= 400: raise EmailSendError(f"Brevo API error {resp.status_code}: {resp.text[:300]}")


def render_digest_email(stories: list, edition_date: str, frontend_url: str, max_stories: int = 8) -> str:
    top_stories = stories[:max_stories]; rows = ""
    for s in top_stories:
        headline = _escape(s.headline); hook = _escape(s.hook or s.summary[:120]); category = _escape(s.category_slug.replace("-", " ").title()); citation_links = ""
        if getattr(s, "citations", None):
            badges = ""
            for c in s.citations[:3]:
                source_name = _escape(c.source_name); url = _escape(c.url)
                badges += f'''<a href="{url}" style="display:inline-block;font-size:11.5px;color:#555;background:#f1efe9;border:1px solid #e7e4de;padding:3px 10px;border-radius:12px;text-decoration:none;margin:0 6px 6px 0;">🔗 {source_name}</a>'''
            if len(s.citations) > 3: badges += f'<span style="font-size:11.5px;color:#999;">+{len(s.citations)-3} more</span>'
            citation_links = f'<div style="margin-top:8px;">{badges}</div>'
        rows += f'''<tr><td style="padding:14px 0;border-bottom:1px solid #eee;"><span style="display:inline-block;background:#111;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:6px;">{category}</span><div style="font-size:17px;font-weight:700;color:#111;margin-top:6px;font-family:Georgia,'Times New Roman',serif;">{headline}</div><div style="font-size:14px;color:#555;margin-top:4px;line-height:1.4;">{hook}</div>{citation_links}</td></tr>'''
    read_minutes = max(1, round(len(top_stories) * 0.5)); edition_link = f"{frontend_url}/edition?date={edition_date}"; preferences_link = f"{frontend_url}/preferences"
    return f'''<div style="max-width:560px;margin:0 auto;font-family:-apple-system,Helvetica,Arial,sans-serif;"><div style="text-align:center;padding:24px 0 8px;"><div style="font-size:12px;letter-spacing:2px;color:#888;text-transform:uppercase;">{edition_date}</div><div style="font-size:26px;font-weight:800;font-family:Georgia,'Times New Roman',serif;margin-top:4px;">Your Morning Brief</div><div style="font-size:13px;color:#999;margin-top:4px;">~{read_minutes} min read today</div></div><table role="presentation" width="100%" style="border-collapse:collapse;">{rows}</table><div style="text-align:center;padding:28px 0;"><a href="{edition_link}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:14px;font-weight:600;">Read Today's Edition</a></div><div style="text-align:center;font-size:11px;color:#999;line-height:1.5;padding:0 8px 20px;">AI-summarized from linked news sources with automated verification and editorial safety checks. Morning Brief is not affiliated with the cited publishers. <a href="{preferences_link}" style="color:#777;">Manage email preferences / withdraw consent</a>.</div></div>'''


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
