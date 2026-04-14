import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import jwt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database import init_db, db as _db_instance

# ── Secret key — fail loud if not set ─────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")

ALGORITHM = "HS256"
security  = HTTPBearer()

# Rate limiter: 100 requests per minute per IP globally
limiter = Limiter(key_func=get_remote_address, default_limits=["100 per minute"])

from app.routers import candidates, votes, payments, admin, auth


# ── JWT verification ───────────────────────────────────────────
def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        role = payload.get("role", "")
        if role not in ("super_admin", "moderator"):
            raise HTTPException(403, "Accès refusé")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expiré — reconnectez-vous")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token invalide")


# ── Lifespan ───────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        try:
            await _db_instance.close()
        except Exception:
            pass


# ── App ────────────────────────────────────────────────────────
app = FastAPI(
    title="Terra Viva Royalty Day — ENSPM",
    description="Plateforme de vote Miss & Master Terra Viva — ENSPM Maroua",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if os.getenv("DISABLE_DOCS", "false") == "true" else "/docs",
    redoc_url=None if os.getenv("DISABLE_DOCS", "false") == "true" else "/redoc",
)

# ── Middleware ─────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Static files & templates ───────────────────────────────────
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ── Global error handlers ──────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Données invalides", "errors": exc.errors()},
    )

@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    # Don't swallow HTTPExceptions — let FastAPI handle them normally
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur serveur interne"},
    )

# ── Public routes ──────────────────────────────────────────────
app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(votes.router,      prefix="/api/votes",      tags=["votes"])
app.include_router(payments.router,   prefix="/api/payments",   tags=["payments"])
app.include_router(auth.router,       prefix="/api/auth",        tags=["auth"])

# ── Protected admin routes ─────────────────────────────────────
app.include_router(
    admin.router,
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(verify_admin_token)],
)

# ── Frontend & health ──────────────────────────────────────────
@app.get("/")
async def root(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception:
        return JSONResponse({"message": "Terra Viva API is running"})

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "event":  "Terra Viva Royalty Day",
        "school": "ENSPM Maroua",
    }