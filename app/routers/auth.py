from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import get_db
from app.schemas import AdminLogin, TokenOut
import jwt, os
from datetime import datetime, timedelta

router = APIRouter()

# helper: defer applying slowapi limiter until request time to avoid circular imports
from functools import wraps

def defer_limit(limit_value):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # find the Request instance
            request = kwargs.get("request")
            if request is None:
                for a in args:
                    try:
                        # FastAPI Request is starlette.requests.Request
                        from fastapi import Request as FastAPIRequest
                        if isinstance(a, FastAPIRequest):
                            request = a
                            break
                    except Exception:
                        continue
            if request is None:
                # no request found; call the original function
                return await func(*args, **kwargs)
            limiter = request.app.state.limiter
            wrapped = limiter.limit(limit_value)(func)
            return await wrapped(*args, **kwargs)
        return wrapper
    return wrapper

SECRET_KEY = os.getenv("SECRET_KEY", "terra-viva-enspm-secret-change-in-prod")
ALGORITHM = "HS256"


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
@defer_limit("5 per minute")
async def login(request: Request, data: AdminLogin, db = Depends(get_db)):
    # FIX: Check database type for proper placeholder syntax
    is_sqlite = db.is_sqlite if hasattr(db, 'is_sqlite') else True
    
    if is_sqlite:
        admin = await db.fetch_one("SELECT * FROM admins WHERE username = ?", (data.username,))
    else:
        admin = await db.fetch_one("SELECT * FROM admins WHERE username = $1", (data.username,))
    
    if not admin or not verify_password_plain(data.password, admin["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects")

    # FIX: Use proper SQL syntax for each database type
    if is_sqlite:
        # SQLite: Use ISO format string for TEXT column
        await db.execute(
            "UPDATE admins SET last_login = ? WHERE id = ?", 
            (datetime.utcnow().isoformat(), admin["id"])
        )
    else:
        # PostgreSQL: Use NOW() for TEXT column (will be stored as string representation)
        # Or use a simple string format that doesn't look like ISO datetime
        await db.execute(
            "UPDATE admins SET last_login = TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS') WHERE id = $1", 
            (admin["id"],)
        )
    await db.commit()

    token = create_token({"sub": admin["username"], "role": admin["role"]})
    return TokenOut(access_token=token, role=admin["role"])