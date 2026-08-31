from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
import zoneinfo,re
from .. import models,schemas
from ..database import get_db
from ..auth import get_current_user
from ..services.personalization import SUPPORTED_COUNTRIES
router=APIRouter(prefix="/users",tags=["users"])

def _validate_timezone(tz_name):
    try: zoneinfo.ZoneInfo(tz_name)
    except Exception: raise HTTPException(status_code=400,detail=f"Unknown timezone: '{tz_name}'")

def _validate_requested_country(value):
    code=(value or "").strip().upper()
    # Store unsupported ISO-style country codes too; the editorial service then
    # resolves them to GLOBAL instead of rejecting the reader or returning no news.
    if not re.fullmatch(r"[A-Z]{2}",code): raise HTTPException(status_code=400,detail="Country code must be a 2-letter ISO-style code")
    return code

def _user_out(user):
    return schemas.UserOut(id=user.id,email=user.email,is_admin=user.is_admin,role=user.role,auth_provider=user.auth_provider,onboarded=user.onboarded,country_code=user.country_code,timezone=user.timezone,send_hour=user.send_hour,send_minute=user.send_minute,content_language=user.content_language,categories=[c.category_slug for c in user.categories])

@router.get("/supported-countries")
def supported_countries():
    return {"countries":[{"code":c,"name":n} for c,n in SUPPORTED_COUNTRIES.items() if c!="GLOBAL"],"fallback":{"code":"GLOBAL","name":"Global"},"default":"IN"}

@router.post("/onboarding",response_model=schemas.UserOut)
def complete_onboarding(payload:schemas.OnboardingRequest,db:Session=Depends(get_db),user:models.User=Depends(get_current_user)):
    _validate_timezone(payload.timezone); country=_validate_requested_country(payload.country_code)
    valid={c.slug for c in db.query(models.Category).filter(models.Category.is_active.is_(True)).all()}; unknown=set(payload.category_slugs)-valid
    if unknown: raise HTTPException(status_code=400,detail=f"Unknown category slug(s): {', '.join(unknown)}")
    user.country_code=country; user.timezone=payload.timezone; user.send_hour=payload.send_hour; user.send_minute=payload.send_minute; user.content_language=payload.content_language; user.onboarded=True
    db.query(models.UserCategory).filter(models.UserCategory.user_id==user.id).delete()
    for slug in payload.category_slugs: db.add(models.UserCategory(user_id=user.id,category_slug=slug))
    db.commit(); db.refresh(user); return _user_out(user)

@router.put("/preferences",response_model=schemas.UserOut)
def update_preferences(payload:schemas.OnboardingRequest,db:Session=Depends(get_db),user:models.User=Depends(get_current_user)):
    return complete_onboarding(payload,db,user)
