"""
Admin router — toutes les routes protégées par JWT via main.py
Les routes sont déjà sécurisées par le Depends(verify_admin_token)
injecté dans main.py au niveau du router.
"""
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.schemas import StatsOut, SettingUpdate

router = APIRouter()


@router.get("/stats", response_model=StatsOut)
async def get_stats(db=Depends(get_db)):
    try:
        # Single query for all vote counts instead of multiple round trips
        vote_row = await db.fetch_one("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN category='miss' THEN 1 ELSE 0 END) as miss,
                SUM(CASE WHEN category='master' THEN 1 ELSE 0 END) as master,
                SUM(CASE WHEN payment_method='orange_money' THEN 1 ELSE 0 END) as orange,
                SUM(CASE WHEN payment_method='mtn_momo' THEN 1 ELSE 0 END) as mtn
            FROM votes
        """)
        total  = vote_row["total"]  if vote_row else 0
        miss   = vote_row["miss"]   if vote_row else 0
        master = vote_row["master"] if vote_row else 0
        orange = vote_row["orange"] if vote_row else 0
        mtn    = vote_row["mtn"]    if vote_row else 0

        # Single query for candidate counts
        cand_row = await db.fetch_one("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active
            FROM candidates
        """)
        total_cands  = cand_row["total"]  if cand_row else 0
        active_cands = cand_row["active"] if cand_row else 0

        unique_voters_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM voters")
        unique_voters = unique_voters_row["cnt"] if unique_voters_row else 0

        row = await db.fetch_one(
            "SELECT value FROM settings WHERE key=?", ("voting_open",)
        )
        voting_open = row is not None and row["value"] == "true"

        price_row = await db.fetch_one(
            "SELECT value FROM settings WHERE key=?", ("vote_price",)
        )
        price = int(price_row["value"]) if price_row else 25

    except Exception as e:
        raise HTTPException(500, f"Erreur lors de la récupération des stats: {str(e)}")

    return StatsOut(
        total_votes=total,
        total_miss_votes=miss,
        total_master_votes=master,
        total_candidates=total_cands,
        total_active_candidates=active_cands,
        unique_voters=unique_voters,
        total_revenue_fcfa=total * price,
        orange_money_votes=orange,
        mtn_momo_votes=mtn,
        voting_open=voting_open,
    )


@router.get("/settings")
async def get_all_settings(db=Depends(get_db)):
    rows = await db.fetch_all("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


@router.put("/settings")
async def update_setting(data: SettingUpdate, db=Depends(get_db)):
    # Security — only allow known keys
    ALLOWED_KEYS = {
        "voting_open", "results_public",
        "orange_money_enabled", "mtn_momo_enabled",
        "vote_price", "voting_deadline",
    }
    if data.key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Clé non autorisée: {data.key}")

    # ON CONFLICT works on both SQLite and PostgreSQL
    await db.execute(
        """INSERT INTO settings (key, value) VALUES (?, ?)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
        (data.key, data.value),
    )
    await db.commit()
    return {"message": "Paramètre mis à jour", "key": data.key, "value": data.value}


@router.get("/audit-log")
async def get_audit_log(limit: int = 50, db=Depends(get_db)):
    if limit > 200:
        limit = 200
    rows = await db.fetch_all("""
        SELECT v.id, v.created_at, c.name as candidate_name, c.category,
               v.payment_method, v.ip_address, vo.matricule, vo.phone
        FROM votes v
        JOIN candidates c ON v.candidate_id = c.id
        JOIN voters vo ON v.voter_id = vo.id
        ORDER BY v.created_at DESC
        LIMIT ?
    """, (limit,))
    return [dict(r) for r in rows]


@router.get("/payments-log")
async def get_payments_log(limit: int = 50, db=Depends(get_db)):
    if limit > 200:
        limit = 200
    rows = await db.fetch_all("""
        SELECT p.reference, p.phone, p.amount, p.provider, p.status, p.created_at,
               c.name as candidate_name, c.category
        FROM payments p
        LEFT JOIN candidates c ON p.candidate_id = c.id
        ORDER BY p.created_at DESC
        LIMIT ?
    """, (limit,))
    return [dict(r) for r in rows]


@router.get("/voters")
async def get_voters(limit: int = 100, db=Depends(get_db)):
    """Liste des votants — admin seulement"""
    if limit > 500:
        limit = 500
    rows = await db.fetch_all("""
        SELECT id, full_name, phone, is_student, matricule,
               has_voted_miss, has_voted_master, created_at
        FROM voters ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    return [dict(r) for r in rows]