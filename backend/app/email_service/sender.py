"""Timezone-aware, country/category-personalized email delivery."""
import copy
import datetime
import logging
from sqlalchemy.orm import Session, joinedload
from .. import models, compliance_models
from ..seed import get_setting
from ..services.personalization import select_personalized_stories
from .brevo_client import send_email, render_digest_email, EmailSendError
from ..config import settings
from ..services.time_settings import admin_timezone, configured_email_time

logger=logging.getLogger("morning_brief.email")

def _is_scheduled_time_now(db:Session)->bool:
    tz=admin_timezone(db);now=datetime.datetime.now(datetime.timezone.utc).astimezone(tz);hour,minute=configured_email_time(db);return now.hour==hour and now.minute==minute

def _localize_for_email(story,language):
    item=copy.copy(story)
    if language=="hi" and story.headline_hi and story.summary_hi:
        item.headline=story.headline_hi;item.hook=story.hook_hi or story.hook;item.summary=story.summary_hi
    return item

def _get_approved_stories_for_edition(db:Session,edition_date:str):
    return db.query(models.Story).options(joinedload(models.Story.citations)).filter(models.Story.edition_date==edition_date,models.Story.is_published.is_(True),models.Story.publication_status=="approved",models.Story.is_test_content.is_(False)).order_by(models.Story.is_pinned.desc(),models.Story.confidence_score.desc(),models.Story.created_at.asc()).all()

def _already_delivered_current_content(db:Session,user_id:int,edition_date:str,stories):
    last_log=db.query(models.EmailLog).filter(models.EmailLog.user_id==user_id,models.EmailLog.edition_date==edition_date,models.EmailLog.status=="sent").order_by(models.EmailLog.sent_at.desc()).first()
    if not last_log:return False
    newest_approval=max((getattr(s,"reviewed_at",None) or getattr(s,"created_at",None) for s in stories if getattr(s,"reviewed_at",None) is not None or getattr(s,"created_at",None)),default=None)
    return not(newest_approval is not None and last_log.sent_at is not None and newest_approval>last_log.sent_at)

def send_daily_emails(db:Session,force=False):
    if not force and not _is_scheduled_time_now(db):
        hour,minute=configured_email_time(db);return {"status":"scheduled","sent":0,"failed":0,"skipped":0,"detail":f"Waiting for scheduled time {hour:02d}:{minute:02d}"}
    users=db.query(models.User).filter(models.User.is_active.is_(True),models.User.onboarded.is_(True),models.User.role=="user").all()
    sent=failed=skipped=0;skip_reasons={"no_today_edition":0,"already_delivered":0,"no_personalized_stories":0,"no_email_consent":0}
    admin_today=datetime.datetime.now(datetime.timezone.utc).astimezone(admin_timezone(db)).date().isoformat();stories=_get_approved_stories_for_edition(db,admin_today);email_top_n=max(1,int(get_setting(db,"email_top_n","25")))
    for user in users:
        try:
            consent=db.query(compliance_models.UserConsent).filter_by(user_id=user.id).first()
            if not consent or not consent.email_news_opt_in:skipped+=1;skip_reasons["no_email_consent"]+=1;continue
            if not stories:skipped+=1;skip_reasons["no_today_edition"]+=1;continue
            if _already_delivered_current_content(db,user.id,admin_today,stories):skipped+=1;skip_reasons["already_delivered"]+=1;continue
            selected,_=select_personalized_stories(stories,user.country_code,{c.category_slug for c in user.categories},email_top_n)
            if not selected:skipped+=1;skip_reasons["no_personalized_stories"]+=1;continue
            localized=[_localize_for_email(s,user.content_language) for s in selected]
            try:
                html=render_digest_email(localized,admin_today,settings.FRONTEND_URL,max_stories=len(localized));send_email(to_email=user.email,subject=f"Your Morning Brief — {admin_today}",html_content=html);user.last_sent_date=admin_today;db.add(models.EmailLog(user_id=user.id,edition_date=admin_today,status="sent"));sent+=1
            except EmailSendError as exc:db.rollback();db.add(models.EmailLog(user_id=user.id,edition_date=admin_today,status="failed",error=str(exc)[:500]));failed+=1
            except Exception as exc:logger.exception("Unexpected email error for user %s",user.id);db.rollback();db.add(models.EmailLog(user_id=user.id,edition_date=admin_today,status="failed",error=str(exc)[:500]));failed+=1
        except Exception as exc:
            logger.exception("Unexpected personalization error for user %s",user.id);db.rollback();failed+=1
    db.commit();return {"status":"completed","sent":sent,"failed":failed,"skipped":skipped,"edition_date":admin_today,"email_top_n":email_top_n,"skip_reasons":skip_reasons}

def send_test_email(db:Session,test_recipient:str,language:str="en"):
    today=datetime.datetime.now(datetime.timezone.utc).astimezone(admin_timezone(db)).date().isoformat();stories=_get_approved_stories_for_edition(db,today);email_top_n=max(1,int(get_setting(db,"email_top_n","25")))
    if not stories:return {"status":"skipped","detail":f"No approved production stories are available for today ({today})"}
    localized=[_localize_for_email(s,language) for s in stories[:email_top_n]]
    try:
        html=render_digest_email(localized,today,settings.FRONTEND_URL,max_stories=len(localized));send_email(to_email=test_recipient,subject=f"[TEST] Your Morning Brief — {today}",html_content=html);return {"status":"completed","detail":f"Test email sent to {test_recipient} using today's approved edition {today}","stories_sent":len(localized)}
    except Exception as exc:return {"status":"failed","detail":str(exc)[:500]}
