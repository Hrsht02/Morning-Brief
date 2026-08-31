import datetime
import json
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if v.strip() != v:
            raise ValueError("Password must not start/end with whitespace")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool
    role: str = "user"
    auth_provider: str = "password"
    onboarded: bool
    country_code: str = "IN"
    timezone: str
    send_hour: int
    send_minute: int
    content_language: str = "en"
    categories: List[str] = []
    class Config:
        from_attributes = True


class OnboardingRequest(BaseModel):
    timezone: str = "Asia/Kolkata"
    country_code: str = Field(default="IN", min_length=2, max_length=2)
    send_hour: int = Field(ge=0, le=23, default=6)
    send_minute: int = Field(ge=0, le=59, default=0)
    category_slugs: List[str] = []
    content_language: str = Field(default="en", pattern="^(en|hi)$")


class CategoryOut(BaseModel):
    slug: str
    name: str
    parent_slug: Optional[str] = None
    class Config:
        from_attributes = True


class CategoryCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9\-]+$")
    name: str = Field(min_length=1, max_length=128)
    parent_slug: Optional[str] = None
    sort_order: int = 0


class CitationOut(BaseModel):
    source_name: str
    title: Optional[str] = None
    url: str
    class Config:
        from_attributes = True


def _parse_json_list(v):
    if v is None: return []
    if isinstance(v, str):
        try: return json.loads(v)
        except (json.JSONDecodeError, TypeError): return []
    return v


def _parse_json_dict(v):
    if v is None: return None
    if isinstance(v, str):
        try: return json.loads(v)
        except (json.JSONDecodeError, TypeError): return None
    return v


class StoryOut(BaseModel):
    id: int
    headline: str
    hook: Optional[str] = None
    summary: str
    headline_hi: Optional[str] = None
    hook_hi: Optional[str] = None
    summary_hi: Optional[str] = None
    category_slug: str
    country_code: str = "GLOBAL"
    is_pinned: bool
    needs_review: bool
    confidence_score: float
    publication_status: str = "pending"
    pipeline_stage: str = "draft_generated"
    verification_flags: List[str] = []
    max_source_similarity: float = 0.0
    max_long_phrase_overlap: float = 0.0
    originality_rewrite_applied: bool = False
    generator_model: Optional[str] = None
    verifier_model: Optional[str] = None
    verifier_report: Optional[dict] = None
    contradiction_flag: bool = False
    citation_complete: bool = True
    is_test_content: bool = False
    reviewed_at: Optional[datetime.datetime] = None
    review_notes: Optional[str] = None
    citations: List[CitationOut] = []
    class Config:
        from_attributes = True
    @field_validator("verification_flags", mode="before")
    @classmethod
    def parse_verification_flags(cls, v): return _parse_json_list(v)
    @field_validator("verifier_report", mode="before")
    @classmethod
    def parse_verifier_report(cls, v): return _parse_json_dict(v)


class EditionOut(BaseModel):
    edition_date: str
    story_count: int
    estimated_read_minutes: int
    stories: List[StoryOut]
    country_requested: Optional[str] = None
    country_effective: str = "GLOBAL"
    country_supported: bool = True
    fallback_used: bool = False


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rss_url: str = Field(min_length=5, max_length=500)
    default_category: Optional[str] = None
    country_code: str = Field(default="IN", min_length=2, max_length=8)
    trust_tier: int = Field(ge=1, le=3, default=2)
    legal_risk_level: str = Field(default="standard", pattern="^(standard|high_risk|blocked)$")


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    rss_url: Optional[str] = None
    default_category: Optional[str] = None
    country_code: Optional[str] = Field(default=None, min_length=2, max_length=8)
    trust_tier: Optional[int] = Field(default=None, ge=1, le=3)
    is_active: Optional[bool] = None
    legal_risk_level: Optional[str] = Field(default=None, pattern="^(standard|high_risk|blocked)$")


class SourceOut(BaseModel):
    id: int
    name: str
    rss_url: str
    default_category: Optional[str] = None
    country_code: str = "IN"
    trust_tier: int
    is_active: bool
    legal_risk_level: str = "standard"
    last_fetched_at: Optional[datetime.datetime] = None
    last_fetch_error: Optional[str] = None
    class Config:
        from_attributes = True


class SettingOut(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    value: str


class AdminUserOut(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool
    role: str = "user"
    auth_provider: str = "password"
    is_active: bool
    onboarded: bool
    country_code: str = "IN"
    created_at: datetime.datetime
    last_sent_date: Optional[str] = None
    class Config:
        from_attributes = True


class DeveloperAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class StoryUpdate(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    category_slug: Optional[str] = None
    country_code: Optional[str] = None
    is_published: Optional[bool] = None
    is_pinned: Optional[bool] = None
    needs_review: Optional[bool] = None
    publication_status: Optional[str] = Field(default=None, pattern="^(pending|approved|rejected)$")


class StoryDecision(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=2000)


class VerificationLayerOut(BaseModel):
    id: int
    key: str
    name: str
    is_enabled: bool
    is_blocking: bool
    sort_order: int
    config: Optional[dict] = None
    class Config:
        from_attributes = True
    @field_validator("config", mode="before")
    @classmethod
    def parse_config(cls, v): return _parse_json_dict(v)


class VerificationLayerUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    is_blocking: Optional[bool] = None
    sort_order: Optional[int] = None
    config: Optional[dict] = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime.datetime
    last_used_at: Optional[datetime.datetime] = None
    class Config:
        from_attributes = True


class ApiKeyCreatedOut(ApiKeyOut):
    raw_key: str


class AuditLogOut(BaseModel):
    id: int
    entity_type: str
    entity_id: Optional[str] = None
    action: str
    actor: str
    notes: Optional[str] = None
    created_at: datetime.datetime
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message: str
