from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import hash_password, verify_password
from ..auth import create_access_token, get_current_user, verify_google_id_token, generate_random_password_hash
from ..seed import get_setting

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id, email=user.email, is_admin=user.is_admin, role=user.role,
        auth_provider=user.auth_provider, onboarded=user.onboarded,
        timezone=user.timezone, send_hour=user.send_hour, send_minute=user.send_minute,
        content_language=user.content_language,
        categories=[c.category_slug for c in user.categories],
    )


def _default_plan_id(db: Session):
    free_plan = db.query(models.Plan).filter(models.Plan.slug == "free").first()
    return free_plan.id if free_plan else None


@router.post("/signup", response_model=schemas.TokenResponse)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    user = models.User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        auth_provider="password",
        plan_id=_default_plan_id(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return schemas.TokenResponse(access_token=token)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    token = create_access_token(user.id)
    return schemas.TokenResponse(access_token=token)


@router.post("/google", response_model=schemas.TokenResponse)
def google_login(payload: schemas.GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Works for both users and admins - Google Sign-In just authenticates the
    person; their existing role (user/developer/admin) is unaffected. A brand
    new Google sign-in creates a regular 'user' account, same as email signup.
    """
    claims = verify_google_id_token(payload.id_token)
    google_sub = claims.get("sub")
    email = claims.get("email", "").lower()

    if not google_sub or not email:
        raise HTTPException(status_code=401, detail="Google token did not include the expected account information")

    user = db.query(models.User).filter(models.User.google_sub == google_sub).first()

    if user is None:
        # Not seen this Google account before - but if the email already has a
        # password-based account, link Google sign-in to it rather than
        # creating a confusing duplicate account with the same email.
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is not None:
            user.google_sub = google_sub
        else:
            user = models.User(
                email=email,
                hashed_password=generate_random_password_hash(),
                auth_provider="google",
                google_sub=google_sub,
                plan_id=_default_plan_id(db),
            )
            db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    token = create_access_token(user.id)
    return schemas.TokenResponse(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def get_me(user: models.User = Depends(get_current_user)):
    return _user_out(user)


@router.get("/google-client-id")
def get_google_client_id(db: Session = Depends(get_db)):
    """Public endpoint so the frontend knows whether to show the Google
    Sign-In button at all, and what client ID to initialize it with -
    avoids hardcoding the client ID into the frontend build."""
    from ..config import settings
    return {"google_client_id": settings.GOOGLE_CLIENT_ID or None}
