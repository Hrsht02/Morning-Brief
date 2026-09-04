import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from sqlalchemy.orm import Session
from .. import models, compliance_models
from ..database import get_db
from ..auth import get_current_user, get_current_admin

router = APIRouter(prefix="/legal", tags=["legal & compliance"])
CONSENT_VERSION = "2026-09-04-v1"

class ConsentRequest(BaseModel): email_news_opt_in: bool
class ContentReportRequest(BaseModel):
    story_id: int | None = None; reporter_email: EmailStr | None = None; reason: str = Field(min_length=3, max_length=120); details: str | None = Field(default=None, max_length=5000)
class ReportStatusRequest(BaseModel): status: str = Field(pattern="^(open|investigating|resolved|rejected)$")
class SourceRegistryRequest(BaseModel):
    tos_url: str | None = None; licence_status: str = Field(default="unreviewed", pattern="^(open|licensed|grey_area|unreviewed)$"); terms_reviewed_at: datetime.datetime | None = None; usage_notes: str | None = Field(default=None, max_length=5000); reviewer: str | None = Field(default=None, max_length=200); active_for_commercial_use: bool = False

@router.get("/disclosure")
def disclosure():
    return {"ai_disclosure":"Morning Brief uses AI to generate and translate summaries from ingested news sources. Stories pass automated verification and may require human editorial review before publication.","source_policy":"Stories link to their source articles. Morning Brief does not claim affiliation with source publishers.","notice":"This is a product disclosure, not legal advice. Review the service's legal obligations with qualified Indian counsel before launch."}

@router.get("/privacy-notice")
def privacy_notice():
    return {"version":CONSENT_VERSION,"notice":"Morning Brief processes your email address and preferences to authenticate your account, personalize your digest, and deliver requested news emails. You can withdraw email-news consent at any time. Data is not silently repurposed for unrelated advertising.","rights":["withdraw email-news consent","request correction","request deletion where applicable","raise a privacy grievance"],"contact":"Use the product's privacy/grievance contact published by the operator."}

@router.get("/consent")
def get_consent(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    row=db.query(compliance_models.UserConsent).filter_by(user_id=user.id).first(); return {"email_news_opt_in":bool(row and row.email_news_opt_in),"consent_version":row.consent_version if row else None,"consented_at":row.consented_at if row else None,"withdrawn_at":row.withdrawn_at if row else None}

@router.put("/consent")
def update_consent(payload: ConsentRequest, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    row=db.query(compliance_models.UserConsent).filter_by(user_id=user.id).first(); now=datetime.datetime.utcnow()
    if row is None: row=compliance_models.UserConsent(user_id=user.id); db.add(row)
    row.email_news_opt_in=payload.email_news_opt_in; row.consent_version=CONSENT_VERSION; row.consented_at=now if payload.email_news_opt_in else row.consented_at; row.withdrawn_at=None if payload.email_news_opt_in else now; db.commit()
    return {"status":"updated","email_news_opt_in":row.email_news_opt_in,"consent_version":row.consent_version}

@router.post("/report")
def report_content(payload: ContentReportRequest, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    if payload.story_id is not None and not db.query(models.Story).filter(models.Story.id==payload.story_id).first(): raise HTTPException(status_code=404, detail="Story not found")
    row=compliance_models.ContentReport(story_id=payload.story_id, reporter_email=user.email if user else payload.reporter_email, reason=payload.reason, details=payload.details); db.add(row); db.commit(); db.refresh(row); return {"status":"received","report_id":row.id}

@router.get("/reports")
def list_reports(db: Session=Depends(get_db), _=Depends(get_current_admin)):
    rows=db.query(compliance_models.ContentReport).order_by(compliance_models.ContentReport.created_at.desc()).limit(500).all(); return [{"id":r.id,"story_id":r.story_id,"reporter_email":r.reporter_email,"reason":r.reason,"details":r.details,"status":r.status,"created_at":r.created_at,"resolved_at":r.resolved_at} for r in rows]

@router.put("/reports/{report_id}")
def update_report(report_id:int,payload:ReportStatusRequest,db:Session=Depends(get_db),admin=Depends(get_current_admin)):
    row=db.query(compliance_models.ContentReport).filter_by(id=report_id).first()
    if not row: raise HTTPException(status_code=404, detail="Report not found")
    row.status=payload.status; row.resolved_at=datetime.datetime.utcnow() if payload.status in {"resolved","rejected"} else None; db.add(models.AuditLog(entity_type="content_report",entity_id=str(row.id),action=f"status_{payload.status}",actor=f"user:{admin.id}({admin.email})",notes=row.details)); db.commit(); return {"status":row.status,"report_id":row.id}

@router.get("/source-registry")
def source_registry(db:Session=Depends(get_db),_=Depends(get_current_admin)):
    rows=db.query(compliance_models.SourceCompliance).order_by(compliance_models.SourceCompliance.source_id.asc()).all(); return [{"source_id":r.source_id,"tos_url":r.tos_url,"licence_status":r.licence_status,"terms_reviewed_at":r.terms_reviewed_at,"usage_notes":r.usage_notes,"reviewer":r.reviewer,"active_for_commercial_use":r.active_for_commercial_use} for r in rows]

@router.put("/source-registry/{source_id}")
def update_source_registry(source_id:int,payload:SourceRegistryRequest,db:Session=Depends(get_db),admin=Depends(get_current_admin)):
    if not db.query(models.Source).filter_by(id=source_id).first(): raise HTTPException(status_code=404, detail="Source not found")
    row=db.query(compliance_models.SourceCompliance).filter_by(source_id=source_id).first()
    if row is None: row=compliance_models.SourceCompliance(source_id=source_id); db.add(row)
    for key,value in payload.model_dump().items(): setattr(row,key,value)
    db.add(models.AuditLog(entity_type="source_compliance",entity_id=str(source_id),action="updated",actor=f"user:{admin.id}({admin.email})",notes=f"licence_status={row.licence_status}; active_for_commercial_use={row.active_for_commercial_use}")); db.commit()
    return {"status":"updated","source_id":source_id,"licence_status":row.licence_status,"active_for_commercial_use":row.active_for_commercial_use}
