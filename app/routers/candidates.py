from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.schemas import CandidateCreate, CandidateOut, CandidateUpdate
from typing import Optional

router = APIRouter()

# Allowlist of fields that can be updated — prevents SQL injection
ALLOWED_UPDATE_FIELDS = {
    "name", "category", "department", "year",
    "age", "bio", "quote", "photo_url", "status"
}


async def get_vote_counts(db) -> dict:
    rows = await db.fetch_all(
        "SELECT candidate_id, COUNT(*) as cnt FROM votes GROUP BY candidate_id"
    )
    return {r["candidate_id"]: r["cnt"] for r in rows}


@router.get("/", response_model=list[CandidateOut])
async def list_candidates(
    category: Optional[str] = None,
    status: str = "active",
    db=Depends(get_db),
):
    query = "SELECT * FROM candidates WHERE status = ?"
    params: list = [status]
    if category in ("miss", "master"):
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY category, id"

    rows = await db.fetch_all(query, params)
    vote_counts = await get_vote_counts(db)

    by_category: dict[str, list] = {"miss": [], "master": []}
    for row in rows:
        r = dict(row)
        r["vote_count"] = vote_counts.get(r["id"], 0)
        # Guard against unexpected category values
        if r["category"] in by_category:
            by_category[r["category"]].append(r)

    candidates: list[dict] = []
    for cat_list in by_category.values():
        cat_list.sort(key=lambda x: x["vote_count"], reverse=True)
        for i, c in enumerate(cat_list):
            c["rank"] = i + 1
            candidates.append(c)

    # SQL already filtered by category — no need to filter again in Python
    return candidates


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: int, db=Depends(get_db)):
    row = await db.fetch_one(
        "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Candidat introuvable")

    vote_counts = await get_vote_counts(db)
    c = dict(row)
    c["vote_count"] = vote_counts.get(c["id"], 0)

    # Compute rank within category
    ranked_rows = await db.fetch_all(
        """SELECT candidate_id, COUNT(*) as cnt
           FROM votes
           WHERE candidate_id IN (
               SELECT id FROM candidates WHERE category = ? AND status = 'active'
           )
           GROUP BY candidate_id
           ORDER BY cnt DESC""",
        (c["category"],),
    )
    rank_ids = [r["candidate_id"] for r in ranked_rows]

    if c["id"] in rank_ids:
        c["rank"] = rank_ids.index(c["id"]) + 1
    else:
        # Candidate with 0 votes ranks after all who have votes
        c["rank"] = len(rank_ids) + 1

    return c


@router.post("/", response_model=CandidateOut, status_code=201)
async def create_candidate(data: CandidateCreate, db=Depends(get_db)):
    res = await db.execute(
        """INSERT INTO candidates (name, category, department, year, age, bio, quote, photo_url, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.name, data.category, data.department, data.year,
            data.age, data.bio, data.quote, data.photo_url, data.status,
        ),
    )
    await db.commit()
    return await get_candidate(res.lastrowid, db)


@router.put("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: int,
    data: CandidateUpdate,
    db=Depends(get_db),
):
    # Check candidate exists
    existing = await db.fetch_one(
        "SELECT id FROM candidates WHERE id = ?", (candidate_id,)
    )
    if not existing:
        raise HTTPException(404, "Candidat introuvable")

    # Only allow known safe fields — prevents SQL injection
    fields = {
        k: v
        for k, v in data.model_dump(exclude_none=True).items()
        if k in ALLOWED_UPDATE_FIELDS
    }
    if not fields:
        raise HTTPException(400, "Aucun champ valide à mettre à jour")

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [candidate_id]
    await db.execute(
        f"UPDATE candidates SET {set_clause} WHERE id = ?", values
    )
    await db.commit()
    return await get_candidate(candidate_id, db)


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: int, db=Depends(get_db)):
    # Check candidate exists
    existing = await db.fetch_one(
        "SELECT id FROM candidates WHERE id = ?", (candidate_id,)
    )
    if not existing:
        raise HTTPException(404, "Candidat introuvable")

    # Soft delete — preserves referential integrity with votes table
    # Hard DELETE would break foreign keys in votes, audit logs, and results
    await db.execute(
        "UPDATE candidates SET status = 'disqualified' WHERE id = ?",
        (candidate_id,),
    )
    await db.commit()
    return {"message": "Candidat supprimé"}