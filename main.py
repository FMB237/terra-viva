import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import jwt

from app.database import init_db
from app.routers import candidates, votes, payments, admin, auth

SECRET_KEY = os.getenv("SECRET_KEY", "terra-viva-enspm-secret-change-in-prod")
ALGORITHM  = "HS256"
security   = HTTPBearer()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Terra Viva Royalty Day — ENSPM",
    description="Plateforme de vote Miss & Master Terra Viva — ENSPM Maroua",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if os.getenv("DISABLE_DOCS", "false") == "true" else "/docs",
    redoc_url=None if os.getenv("DISABLE_DOCS", "false") == "true" else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

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


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "event":  "Terra Viva Royalty Day",
        "school": "ENSPM Maroua",
    }


