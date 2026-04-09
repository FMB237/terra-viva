"""
Payments router — Orange Money & MTN Mobile Money
--------------------------------------------------
Production: configure Campay credentials in .env
Sandbox:    https://demo.campay.net/api
Docs:       https://campay.net/en/developers
"""
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.schemas import PaymentInitiate, PaymentCallback, PaymentOut
import aiosqlite
import uuid
import os
import json
from datetime import datetime

router = APIRouter()

VOTE_PRICE = int(os.getenv("VOTE_PRICE", "100"))
CAMPAY_APP_USERNAME = os.getenv("CAMPAY_APP_USERNAME", "")
CAMPAY_APP_PASSWORD = os.getenv("CAMPAY_APP_PASSWORD", "")
CAMPAY_BASE_URL = os.getenv("CAMPAY_BASE_URL", "https://demo.campay.net/api")


async def get_campay_token() -> str:
    if not CAMPAY_APP_USERNAME:
        return "MOCK_TOKEN_DEV"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{CAMPAY_BASE_URL}/token/",
                json={"username": CAMPAY_APP_USERNAME, "password": CAMPAY_APP_PASSWORD},
            )
            resp.raise_for_status()
            return resp.json().get("token", "")
    except Exception as e:
        print(f"[Campay] Token error: {e}")
        return ""


async def initiate_campay_payment(phone: str, amount: int, reference: str) -> dict:
    if not CAMPAY_APP_USERNAME:
        # MOCK mode
        return {"reference": reference, "status": "PENDING", "message": "Mode démo actif"}
    try:
        import httpx
        token = await get_campay_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{CAMPAY_BASE_URL}/collect/",
                headers={"Authorization": f"Token {token}"},
                json={
                    "amount": str(amount),
                    "currency": "XAF",
                    "from": phone,
                    "description": f"Terra Viva Royalty Day — Vote ref:{reference}",
                    "external_reference": reference,
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[Campay] Payment initiation error: {e}")
        return {"reference": reference, "status": "PENDING", "message": str(e)}


@router.post("/initiate", response_model=PaymentOut)
async def initiate_payment(
    data: PaymentInitiate,
    db: aiosqlite.Connection = Depends(get_db),
):
    if data.is_student and not data.matricule:
        raise HTTPException(400, "Le matricule est requis pour les étudiants")

    # Check voting open
    cur = await db.execute("SELECT value FROM settings WHERE key = 'voting_open'")
    row = await cur.fetchone()
    if row is None or row["value"] != "true":
        raise HTTPException(403, "Les votes sont actuellement fermés")

    # Check provider enabled
    key = "orange_money_enabled" if data.provider == "orange_money" else "mtn_momo_enabled"
    cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    if row is None or row["value"] != "true":
        raise HTTPException(403, f"{data.provider} est désactivé")

    # Check candidate
    cur = await db.execute(
        "SELECT id, name, category FROM candidates WHERE id = ? AND status = 'active'",
        (data.candidate_id,),
    )
    candidate = await cur.fetchone()
    if not candidate:
        raise HTTPException(404, "Candidat introuvable")

    # Check voter hasn't already voted (by phone and/or matricule)
    voter = None
    if data.matricule:
        cur = await db.execute(
            "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
            (data.phone, data.matricule),
        )
        voter = await cur.fetchone()
    else:
        cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (data.phone,))
        voter = await cur.fetchone()
    if voter:
        col = "has_voted_miss" if candidate["category"] == "miss" else "has_voted_master"
        if voter[col]:
            raise HTTPException(409, f"Vous avez déjà voté pour la catégorie {candidate['category'].upper()}")
        # Update voter info with latest data
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

    # BUG FIX: check for duplicate pending payment for same matricule+candidate
    cur = await db.execute(
        "SELECT id FROM payments WHERE voter_matricule = ? AND candidate_id = ? AND status = 'pending'",
        (data.matricule, data.candidate_id),
    )
    existing = await cur.fetchone()
    if existing:
        # Return the existing pending payment reference instead of creating a new one
        cur2 = await db.execute("SELECT * FROM payments WHERE id = ?", (existing["id"],))
        existing_pay = await cur2.fetchone()
        return PaymentOut(
            reference=existing_pay["reference"],
            status=existing_pay["status"],
            provider=existing_pay["provider"],
            amount=existing_pay["amount"],
            phone=existing_pay["phone"],
            created_at=existing_pay["created_at"],
        )

    reference = f"TV-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.utcnow().isoformat()

    metadata = json.dumps(
        {
            "full_name": data.full_name,
            "email": data.email,
            "is_student": data.is_student,
            "matricule": data.matricule,
        },
        ensure_ascii=False,
    )

    await db.execute(
        """INSERT INTO payments
           (reference, phone, amount, provider, status, candidate_id, voter_matricule, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (reference, data.phone, VOTE_PRICE, data.provider,
         data.candidate_id, data.matricule, now, now),
    )
    await db.execute(
        "UPDATE payments SET metadata = ? WHERE reference = ?",
        (metadata, reference),
    )
    await db.commit()

    await initiate_campay_payment(data.phone, VOTE_PRICE, reference)

    return PaymentOut(
        reference=reference,
        status="pending",
        provider=data.provider,
        amount=VOTE_PRICE,
        phone=data.phone,
        created_at=now,
    )


@router.post("/callback")
async def payment_callback(
    data: PaymentCallback,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Webhook URL to register in Campay dashboard:
    https://yourdomain.com/api/payments/callback
    """
    cur = await db.execute("SELECT * FROM payments WHERE reference = ?", (data.reference,))
    payment = await cur.fetchone()
    if not payment:
        raise HTTPException(404, "Référence de paiement introuvable")

    # BUG FIX: prevent processing already-completed payments (idempotency)
    if payment["status"] == "success":
        return {"message": "Déjà traité", "status": "success"}

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE payments SET status = ?, updated_at = ? WHERE reference = ?",
        (data.status, now, data.reference),
    )
    await db.commit()

    if data.status == "success":
        cur = await db.execute(
            "SELECT category FROM candidates WHERE id = ?", (payment["candidate_id"],)
        )
        candidate = await cur.fetchone()
        if candidate:
            category = candidate["category"]
            meta = {}
            if payment["metadata"]:
                try:
                    meta = json.loads(payment["metadata"])
                except Exception:
                    meta = {}
            phone = payment["phone"]
            matricule = payment["voter_matricule"] or meta.get("matricule")

            if matricule:
                cur = await db.execute(
                    "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
                    (phone, matricule),
                )
            else:
                cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (phone,))
            voter = await cur.fetchone()

            if not voter:
                await db.execute(
                    "INSERT OR IGNORE INTO voters (full_name, email, phone, is_student, matricule) VALUES (?, ?, ?, ?, ?)",
                    (
                        meta.get("full_name"),
                        meta.get("email"),
                        phone,
                        1 if meta.get("is_student") else 0,
                        matricule,
                    ),
                )
                await db.commit()
                if matricule:
                    cur = await db.execute(
                        "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
                        (phone, matricule),
                    )
                else:
                    cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (phone,))
                voter = await cur.fetchone()

            if voter:
                await db.execute(
                    "UPDATE voters SET full_name = ?, email = ?, phone = ?, is_student = ?, matricule = ? WHERE id = ?",
                    (
                        meta.get("full_name"),
                        meta.get("email"),
                        phone,
                        1 if meta.get("is_student") else 0,
                        matricule,
                        voter["id"],
                    ),
                )
                await db.commit()
                col = "has_voted_miss" if category == "miss" else "has_voted_master"
                if not voter[col]:
                    await db.execute(
                        """INSERT OR IGNORE INTO votes
                           (candidate_id, voter_id, category, payment_method, payment_ref, ip_address, created_at)
                           VALUES (?, ?, ?, ?, ?, 'webhook', ?)""",
                        (payment["candidate_id"], voter["id"], category,
                         payment["provider"], data.reference, now),
                    )
                    await db.execute(f"UPDATE voters SET {col} = 1 WHERE id = ?", (voter["id"],))
                    await db.commit()

    return {"message": "Callback traité", "status": data.status}


@router.get("/status/{reference}")
async def payment_status(reference: str, db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute(
        "SELECT reference, status, provider, amount, phone, created_at FROM payments WHERE reference = ?",
        (reference,),
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Référence introuvable")
    return dict(row)


@router.get("/mock-confirm/{reference}")
async def mock_confirm_payment(
    reference: str, db: aiosqlite.Connection = Depends(get_db)
):
    """DEV ONLY — Remove in production!"""
    cur = await db.execute("SELECT * FROM payments WHERE reference = ?", (reference,))
    payment = await cur.fetchone()
    if not payment:
        raise HTTPException(404, "Référence introuvable")

    # BUG FIX: call callback logic directly, not by importing self
    callback_data = PaymentCallback(
        reference=reference, status="success", provider=payment["provider"]
    )
    return await payment_callback(callback_data, db)
