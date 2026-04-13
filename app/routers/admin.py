"""
Admin router — toutes les routes protégées par JWT via main.py
Les routes sont déjà sécurisées par le Depends(verify_admin_token)
injecté dans main.py au niveau du router.
"""
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.schemas import StatsOut, SettingUpdate
import aiosqlite

router = APIRouter()


@router.get("/stats", response_model=StatsOut)
async def get_stats(db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute("SELECT COUNT(*) as cnt FROM votes")
    total = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM votes WHERE category='miss'")
    miss = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM votes WHERE category='master'")
    master = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM candidates")
    total_cands = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM candidates WHERE status='active'")
    active_cands = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM voters")
    unique_voters = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM votes WHERE payment_method='orange_money'")
    orange = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT COUNT(*) as cnt FROM votes WHERE payment_method='mtn_momo'")
    mtn = (await cur.fetchone())["cnt"]
    cur = await db.execute("SELECT value FROM settings WHERE key='voting_open'")
    row = await cur.fetchone()
    voting_open = row is not None and row["value"] == "true"
    cur = await db.execute("SELECT value FROM settings WHERE key='vote_price'")
    price_row = await cur.fetchone()
    price = int(price_row["value"]) if price_row else 25

    return StatsOut(
        total_votes=total, total_miss_votes=miss, total_master_votes=master,
        total_candidates=total_cands, total_active_candidates=active_cands,
        unique_voters=unique_voters, total_revenue_fcfa=total * price,
        orange_money_votes=orange, mtn_momo_votes=mtn, voting_open=voting_open,
    )


@router.get("/settings")
async def get_all_settings(db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute("SELECT key, value FROM settings")
    rows = await cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.put("/settings")
async def update_setting(data: SettingUpdate, db: aiosqlite.Connection = Depends(get_db)):
    # Sécurité — clés autorisées seulement
    ALLOWED_KEYS = {
        "voting_open", "results_public",
        "orange_money_enabled", "mtn_momo_enabled",
        "vote_price", "voting_deadline",
    }
    if data.key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Clé non autorisée: {data.key}")
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (data.key, data.value),
    )
    await db.commit()
    return {"message": "Paramètre mis à jour", "key": data.key, "value": data.value}


@router.get("/audit-log")
async def get_audit_log(limit: int = 50, db: aiosqlite.Connection = Depends(get_db)):
    if limit > 200:
        limit = 200
    cur = await db.execute("""
        SELECT v.id, v.created_at, c.name as candidate_name, c.category,
               v.payment_method, v.ip_address, vo.matricule, vo.phone
        FROM votes v
        JOIN candidates c ON v.candidate_id = c.id
        JOIN voters vo ON v.voter_id = vo.id
        ORDER BY v.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/payments-log")
async def get_payments_log(limit: int = 50, db: aiosqlite.Connection = Depends(get_db)):
    if limit > 200:
        limit = 200
    cur = await db.execute("""
        SELECT p.reference, p.phone, p.amount, p.provider, p.status, p.created_at,
               c.name as candidate_name, c.category
        FROM payments p
        LEFT JOIN candidates c ON p.candidate_id = c.id
        ORDER BY p.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/voters")
async def get_voters(limit: int = 100, db: aiosqlite.Connection = Depends(get_db)):
    """Liste des votants — admin seulement"""
    if limit > 500:
        limit = 500
    cur = await db.execute("""
        SELECT id, full_name, phone, is_student, matricule,
               has_voted_miss, has_voted_master, created_at
        FROM voters ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = await cur.fetchall()
    return [dict(r) for r in rows]
