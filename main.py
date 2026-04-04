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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
    return {"status": "ok", "event": "Terra Viva Royalty Day", "organizers": ["Club Sciences de l'Environnement", "Club AGEPD"], "school": "ENSPM Maroua"}
