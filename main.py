import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import candidates, votes, payments, admin, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Terra Viva Royalty Day — ENSPM",
    description="Plateforme de vote pour Miss & Master Terra Viva — Club Sciences de l'Environnement & Club AGEPD — ENSPM Maroua",
    version="1.0.0",
    lifespan=lifespan,
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

# API Routers
app.include_router(candidates.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(votes.router, prefix="/api/votes", tags=["votes"])
app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    static_exists = os.path.isdir(STATIC_DIR)
    templates_exists = os.path.isdir(TEMPLATES_DIR)
    return {
        "status": "ok",
        "event": "Terra Viva Royalty Day",
        "organizers": ["Club Sciences de l'Environnement", "Club AGEPD"],
        "school": "ENSPM Maroua",
        "static_dir": static_exists,
        "templates_dir": templates_exists,
    }
@app.get("/debug-env")
async def debug_env():
    import os
    username = os.getenv("CAMPAY_APP_USERNAME", "")
    password = os.getenv("CAMPAY_APP_PASSWORD", "")
    base_url = os.getenv("CAMPAY_BASE_URL", "")
    
    # Test direct du SDK
    result = {}
    try:
        from campay.sdk import Client
        client = Client({
            "app_username": username,
            "app_password": password,
            "environment": "DEV" if "demo" in base_url else "PROD",
        })
        # Essaie de récupérer le token
        token = client.get_token()
        result = {"token_ok": True, "token": str(token)[:20] + "..."}
    except Exception as e:
        result = {"token_ok": False, "error": str(e)}
    
    return {
        "campay_username_set": bool(username),
        "campay_password_set": bool(password),
        "campay_base_url": base_url,
        "sdk_test": result,
    }
