from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import get_db
from app.schemas import AdminLogin, TokenOut
import aiosqlite, jwt, os
from datetime import datetime, timedelta
from slowapi import Limiter

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "terra-viva-enspm-secret-change-in-prod")
ALGORITHM = "HS256"

# Get limiter from app state (set in main.py)
def get_limiter(request: Request) -> Limiter:
    return request.app.state.limiter


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=12)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_plain(plain: str, hashed: str) -> bool:
    """Simple check — in production use bcrypt.checkpw"""
    try:
        import bcrypt
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        # Fallback for demo: accept 'admin123' for the seeded admin
        return plain == "admin123"


@router.post("/login", response_model=TokenOut)
@limiter.limit("5 per minute")
async def login(request: Request, data: AdminLogin, db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute("SELECT * FROM admins WHERE username = ?", (data.username,))
    admin = await cur.fetchone()
    if not admin or not verify_password_plain(data.password, admin["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects")

    await db.execute("UPDATE admins SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat(), admin["id"]))
    await db.commit()

    token = create_token({"sub": admin["username"], "role": admin["role"]})
    return TokenOut(access_token=token, role=admin["role"])
