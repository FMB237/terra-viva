"""
Payments router — Orange Money & MTN MoMo via Campay
-----------------------------------------------------
🔒 SÉCURISÉ :
  - mock-confirm supprimé
  - debug endpoints supprimés
  - idempotence sur callback
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import get_db
from app.schemas import PaymentInitiate, PaymentCallback, PaymentOut
import aiosqlite
import uuid, os, json
from datetime import datetime

router = APIRouter()

VOTE_PRICE          = int(os.getenv("VOTE_PRICE", "100"))
CAMPAY_USERNAME     = os.getenv("CAMPAY_APP_USERNAME", "")
CAMPAY_PASSWORD     = os.getenv("CAMPAY_APP_PASSWORD", "")
CAMPAY_BASE_URL     = os.getenv("CAMPAY_BASE_URL", "https://demo.campay.net/api")


def _campay_env() -> str:
    return "DEV" if "demo" in CAMPAY_BASE_URL else "PROD"


def _get_client():
    from campay.sdk import Client
    return Client({
        "app_username": CAMPAY_USERNAME,
        "app_password": CAMPAY_PASSWORD,
        "environment":  _campay_env(),
    })


async def _initiate_campay(phone: str, amount: int, reference: str) -> dict:
    if not CAMPAY_USERNAME:
        print(f"[MOCK] Paiement simulé → {phone} | {amount} XAF | ref:{reference}")
        return {"reference": reference, "status": "PENDING", "message": "Mode démo"}
    try:
        client = _get_client()
        result = client.collect({
            "amount":             str(amount),
            "currency":           "XAF",
            "from":               phone,
            "description":        f"Terra Viva Royalty Day — Vote réf:{reference}",
            "external_reference": reference,
        })
        print(f"[Campay] collect() → {result}")
        return result or {}
    except Exception as exc:
        print(f"[Campay] Erreur initiation: {exc}")
        return {"reference": reference, "status": "PENDING", "message": str(exc)}


async def _get_campay_status(reference: str) -> str:
    if not CAMPAY_USERNAME:
        return "PENDING"
    try:
        client = _get_client()
        result = client.get_payment(reference)
        print(f"[Campay] get_payment({reference}) → {result}")
        return result.get("status", "PENDING")
    except Exception as exc:
        print(f"[Campay] Erreur get_payment: {exc}")
        return "PENDING"


# ── DB helpers ────────────────────────────────────────────────────────────────
async def _get_or_create_voter(db, data: PaymentInitiate) -> dict:
    if data.matricule:
        cur = await db.execute(
            "SELECT * FROM voters WHERE phone=? OR (matricule IS NOT NULL AND matricule=?)",
            (data.phone, data.matricule),
        )
    else:
        cur = await db.execute("SELECT * FROM voters WHERE phone=?", (data.phone,))
    voter = await cur.fetchone()

    if voter:
        await db.execute(
            "UPDATE voters SET full_name=?,email=?,phone=?,is_student=?,matricule=? WHERE id=?",
            (data.full_name, data.email, data.phone,
             1 if data.is_student else 0, data.matricule, voter["id"]),
        )
        await db.commit()
        return dict(voter)

    await db.execute(
        "INSERT INTO voters (full_name,email,phone,is_student,matricule) VALUES (?,?,?,?,?)",
        (data.full_name, data.email, data.phone, 1 if data.is_student else 0, data.matricule),
    )
    await db.commit()
    if data.matricule:
        cur = await db.execute(
            "SELECT * FROM voters WHERE phone=? OR (matricule IS NOT NULL AND matricule=?)",
            (data.phone, data.matricule),
        )
    else:
        cur = await db.execute("SELECT * FROM voters WHERE phone=?", (data.phone,))
    return dict(await cur.fetchone())


async def _record_vote(db, candidate_id, voter, category, provider, payment_ref, ip="webhook"):
    col = "has_voted_miss" if category == "miss" else "has_voted_master"
    if voter.get(col):
        return False
    now = datetime.utcnow().isoformat()
    await db.execute(
        """INSERT OR IGNORE INTO votes
           (candidate_id,voter_id,category,payment_method,payment_ref,ip_address,created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (candidate_id, voter["id"], category, provider, payment_ref, ip, now),
    )
    await db.execute(f"UPDATE voters SET {col}=1 WHERE id=?", (voter["id"],))
    await db.commit()
    return True


async def _finalize_vote(db, payment: dict):
    cur = await db.execute("SELECT category FROM candidates WHERE id=?", (payment["candidate_id"],))
    candidate = await cur.fetchone()
    if not candidate:
        return

    meta = {}
    if payment.get("metadata"):
        try: meta = json.loads(payment["metadata"])
        except: pass

    phone     = payment["phone"]
    matricule = payment["voter_matricule"]

    if matricule and matricule != phone:
        cur = await db.execute(
            "SELECT * FROM voters WHERE phone=? OR (matricule IS NOT NULL AND matricule=?)",
            (phone, matricule),
        )
    else:
        cur = await db.execute("SELECT * FROM voters WHERE phone=?", (phone,))
    voter = await cur.fetchone()

    if not voter:
        await db.execute(
            "INSERT OR IGNORE INTO voters (full_name,email,phone,is_student,matricule) VALUES (?,?,?,?,?)",
            (meta.get("full_name"), meta.get("email"), phone,
             1 if meta.get("is_student") else 0,
             None if matricule == phone else matricule),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM voters WHERE phone=?", (phone,))
        voter = await cur.fetchone()

    if voter:
        await _record_vote(
            db, payment["candidate_id"], dict(voter),
            candidate["category"], payment["provider"], payment["reference"],
        )


# ── ROUTES ────────────────────────────────────────────────────────────────────

@router.post("/initiate", response_model=PaymentOut)
async def initiate_payment(data: PaymentInitiate, db: aiosqlite.Connection = Depends(get_db)):
    if data.is_student and not data.matricule:
        raise HTTPException(400, "Le matricule est requis pour les étudiants")

    cur = await db.execute("SELECT value FROM settings WHERE key='voting_open'")
    row = await cur.fetchone()
    if not row or row["value"] != "true":
        raise HTTPException(403, "Les votes sont actuellement fermés")

    pk = "orange_money_enabled" if data.provider == "orange_money" else "mtn_momo_enabled"
    cur = await db.execute("SELECT value FROM settings WHERE key=?", (pk,))
    row = await cur.fetchone()
    if not row or row["value"] != "true":
        raise HTTPException(403, f"{data.provider} est désactivé")

    cur = await db.execute(
        "SELECT id,name,category FROM candidates WHERE id=? AND status='active'",
        (data.candidate_id,),
    )
    candidate = await cur.fetchone()
    if not candidate:
        raise HTTPException(404, "Candidat introuvable")

    voter = await _get_or_create_voter(db, data)
    col   = "has_voted_miss" if candidate["category"] == "miss" else "has_voted_master"
    if voter.get(col):
        raise HTTPException(409, f"Vous avez déjà voté pour {candidate['category'].upper()}")

    # Paiement pending existant ?
    cur = await db.execute(
        "SELECT * FROM payments WHERE voter_matricule=? AND candidate_id=? AND status='pending'",
        (data.matricule or data.phone, data.candidate_id),
    )
    existing = await cur.fetchone()
    if existing:
        return PaymentOut(
            reference=existing["reference"], status=existing["status"],
            provider=existing["provider"],   amount=existing["amount"],
            phone=existing["phone"],          created_at=existing["created_at"],
        )

    reference = f"TV-{uuid.uuid4().hex[:10].upper()}"
    now       = datetime.utcnow().isoformat()
    metadata  = json.dumps({
        "full_name":  data.full_name,
        "email":      data.email,
        "is_student": data.is_student,
        "matricule":  data.matricule,
    }, ensure_ascii=False)

    await db.execute(
        """INSERT INTO payments
           (reference,phone,amount,provider,status,candidate_id,voter_matricule,metadata,created_at,updated_at)
           VALUES (?,?,?,?,'pending',?,?,?,?,?)""",
        (reference, data.phone, VOTE_PRICE, data.provider,
         data.candidate_id, data.matricule or data.phone,
         metadata, now, now),
    )
    await db.commit()

    await _initiate_campay(data.phone, VOTE_PRICE, reference)

    return PaymentOut(
        reference=reference, status="pending",
        provider=data.provider, amount=VOTE_PRICE,
        phone=data.phone, created_at=now,
    )


@router.post("/callback")
async def payment_callback(data: PaymentCallback, db: aiosqlite.Connection = Depends(get_db)):
    """Webhook Campay — POST https://terra-viva.onrender.com/api/payments/callback"""
    cur = await db.execute("SELECT * FROM payments WHERE reference=?", (data.reference,))
    payment = await cur.fetchone()
    if not payment:
        raise HTTPException(404, "Référence introuvable")

    # Idempotence
    if payment["status"] == "success":
        return {"message": "Déjà traité", "status": "success"}

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE payments SET status=?,updated_at=? WHERE reference=?",
        (data.status, now, data.reference),
    )
    await db.commit()

    if data.status == "success":
        await _finalize_vote(db, dict(payment))

    return {"message": "Callback traité", "status": data.status}


@router.get("/status/{reference}")
async def payment_status(reference: str, db: aiosqlite.Connection = Depends(get_db)):
    """Polling frontend toutes les 3s."""
    cur = await db.execute("SELECT * FROM payments WHERE reference=?", (reference,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Référence introuvable")

    payment = dict(row)

    if payment["status"] == "pending" and CAMPAY_USERNAME:
        campay_status = await _get_campay_status(reference)
        status_map = {"SUCCESSFUL": "success", "FAILED": "failed", "CANCELLED": "cancelled"}
        if campay_status in status_map:
            new_status = status_map[campay_status]
            now = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE payments SET status=?,updated_at=? WHERE reference=?",
                (new_status, now, reference),
            )
            await db.commit()
            if new_status == "success":
                await _finalize_vote(db, payment)
            payment["status"] = new_status

    return {
        "reference":  payment["reference"],
        "status":     payment["status"],
        "provider":   payment["provider"],
        "amount":     payment["amount"],
        "phone":      payment["phone"],
        "created_at": payment["created_at"],
    }
