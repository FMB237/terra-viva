from pydantic import BaseModel, Field, field_validator, field_serializer, model_validator
from typing import Optional, Literal, Union
from datetime import datetime
import re


# ── SHARED MIXIN — phone & email validators ────────
class PhoneEmailMixin(BaseModel):
    """Reusable validators for phone and email fields."""

    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def validate_email(cls, v):
        if v is None or v == "":
            return None
        pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v.strip()):
            raise ValueError("Format email invalide. Ex: nom@gmail.com")
        return v.strip().lower()

    @field_validator("phone", mode="before", check_fields=False)
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return v
        cleaned = re.sub(r'[\s\-\(\)]', '', str(v))
        if not re.match(r'^\+\d{7,15}$', cleaned):
            raise ValueError(
                "Format téléphone invalide. "
                "Incluez l'indicatif pays. Ex: +237699000001, +33612345678"
            )
        return cleaned


def serialize_dt(v: Union[datetime, str]) -> str:
    """Serialize datetime or ISO string to ISO string consistently."""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)  # already a string from SQLite


# ── CANDIDATE ──────────────────────────────────────
class CandidateCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    category: Literal["miss", "master"]
    department: str = Field(..., min_length=2, max_length=100)
    year: str = Field(..., max_length=50)
    age: Optional[int] = Field(None, ge=16, le=35)
    bio: Optional[str] = Field(None, max_length=1500)
    quote: Optional[str] = Field(None, max_length=300)
    photo_url: Optional[str] = None
    status: Literal["active", "draft", "disqualified"] = "active"


class CandidateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    department: Optional[str] = Field(None, min_length=2, max_length=100)
    year: Optional[str] = Field(None, max_length=50)
    age: Optional[int] = Field(None, ge=16, le=35)
    bio: Optional[str] = Field(None, max_length=1500)
    quote: Optional[str] = Field(None, max_length=300)
    photo_url: Optional[str] = None
    status: Optional[Literal["active", "draft", "disqualified"]] = None


class CandidateOut(BaseModel):
    id: int
    name: str
    category: str
    department: str
    year: str
    age: Optional[int]
    bio: Optional[str]
    quote: Optional[str]
    photo_url: Optional[str]
    status: str
    vote_count: int = 0
    rank: int = 0
    created_at: Union[datetime, str]

    @field_serializer("created_at")
    def serialize_created_at(self, v) -> str:
        return serialize_dt(v)

    class Config:
        from_attributes = True


# ── VOTER ──────────────────────────────────────────
class VoterRegister(PhoneEmailMixin):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = Field(None, max_length=120)
    phone: str = Field(..., min_length=8, max_length=20)
    is_student: bool = False
    matricule: Optional[str] = Field(None, min_length=3, max_length=30)


# ── VOTE ───────────────────────────────────────────
class VoteCreate(PhoneEmailMixin):
    candidate_id: int
    category: Literal["miss", "master"]
    full_name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = Field(None, max_length=120)
    is_student: bool = False
    matricule: Optional[str] = Field(None, min_length=3, max_length=30)
    payment_method: Literal["orange_money", "mtn_momo"]
    phone: str = Field(..., min_length=8, max_length=20)


class VoteOut(BaseModel):
    id: int
    candidate_id: int
    candidate_name: str
    category: str
    payment_method: str
    created_at: Union[datetime, str]

    @field_serializer("created_at")
    def serialize_created_at(self, v) -> str:
        return serialize_dt(v)


# ── PAYMENT ────────────────────────────────────────
class PaymentInitiate(PhoneEmailMixin):
    phone: str = Field(..., min_length=8, max_length=20)
    provider: Literal["orange_money", "mtn_momo"]
    candidate_id: int
    full_name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = Field(None, max_length=120)
    is_student: bool = False
    matricule: Optional[str] = Field(None, min_length=3, max_length=30)


class PaymentCallback(BaseModel):
    reference: str
    status: Literal["success", "failed", "cancelled"]
    provider: str
    metadata: Optional[dict] = None


class PaymentOut(BaseModel):
    reference: str
    status: str
    provider: str
    amount: int
    phone: str
    created_at: Union[datetime, str]

    @field_serializer("created_at")
    def serialize_created_at(self, v) -> str:
        return serialize_dt(v)


# ── RESULTS ────────────────────────────────────────
class ResultEntry(BaseModel):
    rank: int
    candidate_id: int
    name: str
    category: str
    department: str
    year: str
    photo_url: Optional[str]
    vote_count: int
    percentage: float


class ResultsOut(BaseModel):
    miss: list[ResultEntry]
    master: list[ResultEntry]
    total_votes: int
    total_miss_votes: int
    total_master_votes: int
    voting_open: bool


# ── ADMIN AUTH ─────────────────────────────────────
class AdminLogin(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ── SETTINGS ───────────────────────────────────────
class SettingUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=500)


class StatsOut(BaseModel):
    total_votes: int
    total_miss_votes: int
    total_master_votes: int
    total_candidates: int
    total_active_candidates: int
    unique_voters: int
    total_revenue_fcfa: int
    orange_money_votes: int
    mtn_momo_votes: int
    voting_open: bool