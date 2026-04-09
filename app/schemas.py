from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


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
    name: Optional[str] = None
    department: Optional[str] = None
    year: Optional[str] = None
    age: Optional[int] = None
    bio: Optional[str] = None
    quote: Optional[str] = None
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
    created_at: str


# ── VOTER ──────────────────────────────────────────
class VoterRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = Field(None, max_length=120)
    phone: str = Field(..., min_length=9, max_length=15)
    is_student: bool = False
    matricule: Optional[str] = Field(None, min_length=3, max_length=30)


# ── VOTE ───────────────────────────────────────────
class VoteCreate(BaseModel):
    candidate_id: int
    category: Literal["miss", "master"]
    full_name: str = Field(..., min_length=2, max_length=120)
    email: Optional[str] = Field(None, max_length=120)
    is_student: bool = False
    matricule: Optional[str] = Field(None, min_length=3, max_length=30)
    payment_method: Literal["orange_money", "mtn_momo"]
    phone: str = Field(..., min_length=9, max_length=15)


class VoteOut(BaseModel):
    id: int
    candidate_id: int
    candidate_name: str
    category: str
    payment_method: str
    created_at: str


# ── PAYMENT ────────────────────────────────────────
class PaymentInitiate(BaseModel):
    phone: str = Field(..., min_length=9, max_length=15)
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
    created_at: str


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
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ── SETTINGS ───────────────────────────────────────
class SettingUpdate(BaseModel):
    key: str
    value: str


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
