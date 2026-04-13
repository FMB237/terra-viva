from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import get_db
from app.schemas import VoteCreate, VoteOut, ResultsOut, ResultEntry
import uuid
from datetime import datetime

router = APIRouter()

# BUG FIX: /results and /check MUST be registered before /{param} routes
# to avoid FastAPI treating "results" as a path parameter value.

@router.get("/results", response_model=ResultsOut)
async def get_results(db = Depends(get_db)):
    row = await db.fetch_one("SELECT value FROM settings WHERE key = 'results_public'")
    if row is None or row["value"] != "true":
        raise HTTPException(403, "Les résultats ne sont pas encore disponibles publiquement")

    row = await db.fetch_one("SELECT value FROM settings WHERE key = 'voting_open'")
    voting_open = row is not None and row["value"] == "true"

    rows = await db.fetch_all("""
        SELECT c.id, c.name, c.category, c.department, c.year, c.photo_url,
               COUNT(v.id) as vote_count
        FROM candidates c
        LEFT JOIN votes v ON v.candidate_id = c.id
        WHERE c.status = 'active'
        GROUP BY c.id
        ORDER BY c.category, vote_count DESC
    """)

    miss_list: list[dict] = []
    master_list: list[dict] = []
    total_miss = 0
    total_master = 0

    for row in rows:
        r = dict(row)
        if r["category"] == "miss":
            miss_list.append(r)
            total_miss += r["vote_count"]
        else:
            master_list.append(r)
            total_master += r["vote_count"]

    def build_entries(lst: list[dict], total: int) -> list[ResultEntry]:
        return [
            ResultEntry(
                rank=i + 1,
                candidate_id=c["id"],
                name=c["name"],
                category=c["category"],
                department=c["department"],
                year=c["year"],
                photo_url=c.get("photo_url"),
                vote_count=c["vote_count"],
                percentage=round(c["vote_count"] / total * 100, 1) if total > 0 else 0.0,
            )
            for i, c in enumerate(lst)
        ]

    return ResultsOut(
        miss=build_entries(miss_list, total_miss),
        master=build_entries(master_list, total_master),
        total_votes=total_miss + total_master,
        total_miss_votes=total_miss,
        total_master_votes=total_master,
        voting_open=voting_open,
    )


@router.get("/check/{matricule}")
async def check_voter(matricule: str, db = Depends(get_db)):
    row = await db.fetch_one(
        "SELECT has_voted_miss, has_voted_master FROM voters WHERE matricule = ?",
        (matricule,),
    )
    if not row:
        return {"has_voted_miss": False, "has_voted_master": False, "registered": False}
    return {
        "has_voted_miss": bool(row["has_voted_miss"]),
        "has_voted_master": bool(row["has_voted_master"]),
        "registered": True,
    }


@router.post("/", response_model=VoteOut, status_code=201)
async def cast_vote(
    data: VoteCreate,
    request: Request,
    db = Depends(get_db),
):
    row = await db.fetch_one("SELECT value FROM settings WHERE key = 'voting_open'")
    if row is None or row["value"] != "true":
        raise HTTPException(403, "Les votes sont actuellement fermés")

    method_key = "orange_money_enabled" if data.payment_method == "orange_money" else "mtn_momo_enabled"
    row = await db.fetch_one("SELECT value FROM settings WHERE key = ?", (method_key,))
    if row is None or row["value"] != "true":
        raise HTTPException(403, f"{data.payment_method} est désactivé")

    candidate = await db.fetch_one(
        "SELECT * FROM candidates WHERE id = ? AND status = 'active'", (data.candidate_id,)
    )
    if not candidate:
        raise HTTPException(404, "Candidat introuvable ou inactif")
    if candidate["category"] != data.category:
        raise HTTPException(400, "Catégorie du candidat incorrecte")

    if data.is_student and not data.matricule:
        raise HTTPException(400, "Le matricule est requis pour les étudiants")

    voter = None
    if data.matricule:
        voter = await db.fetch_one(
            "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
            (data.phone, data.matricule),
        )
    else:
        voter = await db.fetch_one("SELECT * FROM voters WHERE phone = ?", (data.phone,))

    if voter:
        col = "has_voted_miss" if data.category == "miss" else "has_voted_master"
        if voter[col]:
            raise HTTPException(409, f"Vous avez déjà voté dans la catégorie {data.category.upper()}")
        await db.execute(
            "UPDATE voters SET full_name = ?, email = ?, phone = ?, is_student = ?, matricule = ? WHERE id = ?",
            (
                data.full_name,
                data.email,
                data.phone,
                1 if data.is_student else 0,
                data.matricule,
                voter["id"],
            ),
        )
        await db.commit()
    else:
        await db.execute(
            "INSERT INTO voters (full_name, email, phone, is_student, matricule) VALUES (?, ?, ?, ?, ?)",
            (
                data.full_name,
                data.email,
                data.phone,
                1 if data.is_student else 0,
                data.matricule,
            ),
        )
        await db.commit()
        if data.matricule:
            voter = await db.fetch_one(
                "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
                (data.phone, data.matricule),
            )
        else:
            voter = await db.fetch_one("SELECT * FROM voters WHERE phone = ?", (data.phone,))

    if voter is None:
        raise HTTPException(500, "Erreur lors de la création du votant")

    ip = request.client.host if request.client else "unknown"
    now = datetime.utcnow().isoformat()

    res = await db.execute(
        """INSERT INTO votes
           (candidate_id, voter_id, category, payment_method, payment_ref, ip_address, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data.candidate_id, voter["id"], data.category,
         data.payment_method, str(uuid.uuid4())[:8].upper(), ip, now),
    )
    vote_id = res.lastrowid

    col = "has_voted_miss" if data.category == "miss" else "has_voted_master"
    await db.execute(f"UPDATE voters SET {col} = 1 WHERE id = ?", (voter["id"],))
    await db.commit()

    return VoteOut(
        id=vote_id,
        candidate_id=data.candidate_id,
        candidate_name=candidate["name"],
        category=data.category,
        payment_method=data.payment_method,
        created_at=now,
    )