"""
Payments router — Orange Money & MTN Mobile Money via SDK Campay
----------------------------------------------------------------
SDK docs: https://campay.net/en/developers
Package:  campay==1.1.0 (déjà dans requirements.txt)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from app.database import get_db
from app.schemas import PaymentInitiate, PaymentCallback, PaymentOut
import aiosqlite
import uuid
import os
import json
from datetime import datetime

router = APIRouter()

VOTE_PRICE      = int(os.getenv("VOTE_PRICE", "100"))
CAMPAY_USERNAME = os.getenv("CAMPAY_APP_USERNAME", "")
CAMPAY_PASSWORD = os.getenv("CAMPAY_APP_PASSWORD", "")
CAMPAY_BASE_URL = os.getenv("CAMPAY_BASE_URL", "https://demo.campay.net/api")


def _campay_environment() -> str:
    """Retourne 'DEV' pour la sandbox, 'PROD' pour la production."""
    return "DEV" if "demo" in CAMPAY_BASE_URL else "PROD"


def _get_client():
    """Instancie le client SDK Campay."""
    from campay.sdk import Client  # type: ignore
    return Client({
        "app_username": CAMPAY_USERNAME,
        "app_password": CAMPAY_PASSWORD,
        "environment": _campay_environment(),
    })


async def _initiate_campay_payment(phone: str, amount: int, reference: str) -> dict:
    """
    Envoie une demande de collecte (push USSD) via Campay.
    En mode démo (pas de credentials), simule la réponse.
    """
    if not CAMPAY_USERNAME:
        print(f"[MOCK] Paiement simulé → {phone} | {amount} XAF | ref:{reference}")
        return {"reference": reference, "status": "PENDING", "message": "Mode démo actif"}

    try:
        client = _get_client()
        result = client.collect({
            "amount":             str(amount),
            "currency":           "XAF",
            "from":               phone,
            "description":        f"Terra Viva Royalty Day — Vote ref:{reference}",
            "external_reference": reference,
        })
        print(f"[Campay] collect() → {result}")
        return result or {}
    except Exception as exc:
        # On logue l'erreur mais on ne bloque pas le flux —
        # le webhook confirmera le paiement quand l'utilisateur validera.
        print(f"[Campay] Erreur initiation: {exc}")
        return {"reference": reference, "status": "PENDING", "message": str(exc)}


async def _get_campay_payment_status(reference: str) -> str:
    """
    Interroge Campay pour le statut d'un paiement.
    Retourne : 'SUCCESSFUL' | 'FAILED' | 'PENDING'
    """
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


# ── helpers DB ────────────────────────────────────────────────────────────────

async def _get_or_create_voter(db: aiosqlite.Connection, data: PaymentInitiate) -> dict:
    """Cherche le votant par téléphone ou matricule, le crée si inexistant."""
    if data.matricule:
        cur = await db.execute(
            "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
            (data.phone, data.matricule),
        )
    else:
        cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (data.phone,))
    voter = await cur.fetchone()

    if voter:
        await db.execute(
            """UPDATE voters
               SET full_name = ?, email = ?, phone = ?, is_student = ?, matricule = ?
               WHERE id = ?""",
            (data.full_name, data.email, data.phone,
             1 if data.is_student else 0, data.matricule, voter["id"]),
        )
        await db.commit()
        return dict(voter)

    await db.execute(
        "INSERT INTO voters (full_name, email, phone, is_student, matricule) VALUES (?, ?, ?, ?, ?)",
        (data.full_name, data.email, data.phone,
         1 if data.is_student else 0, data.matricule),
    )
    await db.commit()
    if data.matricule:
        cur = await db.execute(
            "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
            (data.phone, data.matricule),
        )
    else:
        cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (data.phone,))
    return dict(await cur.fetchone())


async def _record_vote(
    db: aiosqlite.Connection,
    candidate_id: int,
    voter: dict,
    category: str,
    provider: str,
    payment_ref: str,
    ip: str = "webhook",
) -> bool:
    """
    Enregistre le vote en base si le votant n'a pas encore voté
    dans cette catégorie. Retourne True si le vote a été créé.
    """
    col = "has_voted_miss" if category == "miss" else "has_voted_master"
    if voter.get(col):
        return False  # déjà voté

    now = datetime.utcnow().isoformat()
    await db.execute(
        """INSERT OR IGNORE INTO votes
           (candidate_id, voter_id, category, payment_method, payment_ref, ip_address, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (candidate_id, voter["id"], category, provider, payment_ref, ip, now),
    )
    await db.execute(f"UPDATE voters SET {col} = 1 WHERE id = ?", (voter["id"],))
    await db.commit()
    return True


# ── ROUTES ────────────────────────────────────────────────────────────────────

@router.post("/initiate", response_model=PaymentOut)
async def initiate_payment(
    data: PaymentInitiate,
    db: aiosqlite.Connection = Depends(get_db),
):
    # Validation métier
    if data.is_student and not data.matricule:
        raise HTTPException(400, "Le matricule est requis pour les étudiants")

    # Votes ouverts ?
    cur = await db.execute("SELECT value FROM settings WHERE key = 'voting_open'")
    row = await cur.fetchone()
    if row is None or row["value"] != "true":
        raise HTTPException(403, "Les votes sont actuellement fermés")

    # Opérateur activé ?
    provider_key = "orange_money_enabled" if data.provider == "orange_money" else "mtn_momo_enabled"
    cur = await db.execute("SELECT value FROM settings WHERE key = ?", (provider_key,))
    row = await cur.fetchone()
    if row is None or row["value"] != "true":
        raise HTTPException(403, f"{data.provider} est désactivé")

    # Candidat valide ?
    cur = await db.execute(
        "SELECT id, name, category FROM candidates WHERE id = ? AND status = 'active'",
        (data.candidate_id,),
    )
    candidate = await cur.fetchone()
    if not candidate:
        raise HTTPException(404, "Candidat introuvable")

    # Déjà voté ?
    voter = await _get_or_create_voter(db, data)
    col = "has_voted_miss" if candidate["category"] == "miss" else "has_voted_master"
    if voter.get(col):
        raise HTTPException(409, f"Vous avez déjà voté pour la catégorie {candidate['category'].upper()}")

    # Paiement pending déjà existant pour ce votant + candidat ?
    cur = await db.execute(
        """SELECT * FROM payments
           WHERE voter_matricule = ? AND candidate_id = ? AND status = 'pending'""",
        (data.matricule or data.phone, data.candidate_id),
    )
    existing = await cur.fetchone()
    if existing:
        return PaymentOut(
            reference=existing["reference"],
            status=existing["status"],
            provider=existing["provider"],
            amount=existing["amount"],
            phone=existing["phone"],
            created_at=existing["created_at"],
        )

    # Créer le paiement en base
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
           (reference, phone, amount, provider, status, candidate_id,
            voter_matricule, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
        (reference, data.phone, VOTE_PRICE, data.provider,
         data.candidate_id, data.matricule or data.phone,
         metadata, now, now),
    )
    await db.commit()

    # Lancer la collecte Campay (push USSD)
    await _initiate_campay_payment(data.phone, VOTE_PRICE, reference)

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
    Webhook Campay — à enregistrer dans le dashboard Campay :
        https://terra-viva.onrender.com/api/payments/callback
    """
    cur = await db.execute("SELECT * FROM payments WHERE reference = ?", (data.reference,))
    payment = await cur.fetchone()
    if not payment:
        raise HTTPException(404, "Référence de paiement introuvable")

    # Idempotence — ne pas retraiter un paiement déjà confirmé
    if payment["status"] == "success":
        return {"message": "Déjà traité", "status": "success"}

    now = datetime.utcnow().isoformat()
    await db.execute(
        "UPDATE payments SET status = ?, updated_at = ? WHERE reference = ?",
        (data.status, now, data.reference),
    )
    await db.commit()

    if data.status == "success":
        # Récupérer la catégorie du candidat
        cur = await db.execute(
            "SELECT category FROM candidates WHERE id = ?", (payment["candidate_id"],)
        )
        candidate = await cur.fetchone()
        if not candidate:
            return {"message": "Candidat introuvable", "status": data.status}

        # Reconstruire les infos voter depuis le metadata
        meta = {}
        if payment["metadata"]:
            try:
                meta = json.loads(payment["metadata"])
            except Exception:
                pass

        # Chercher le voter existant
        phone     = payment["phone"]
        matricule = payment["voter_matricule"]
        if matricule and matricule != phone:
            cur = await db.execute(
                "SELECT * FROM voters WHERE phone = ? OR (matricule IS NOT NULL AND matricule = ?)",
                (phone, matricule),
            )
        else:
            cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (phone,))
        voter = await cur.fetchone()

        # Créer le voter s'il n'existe pas (cas rare)
        if not voter:
            await db.execute(
                """INSERT OR IGNORE INTO voters
                   (full_name, email, phone, is_student, matricule)
                   VALUES (?, ?, ?, ?, ?)""",
                (meta.get("full_name"), meta.get("email"), phone,
                 1 if meta.get("is_student") else 0,
                 None if matricule == phone else matricule),
            )
            await db.commit()
            cur = await db.execute("SELECT * FROM voters WHERE phone = ?", (phone,))
            voter = await cur.fetchone()

        if voter:
            await _record_vote(
                db,
                candidate_id=payment["candidate_id"],
                voter=dict(voter),
                category=candidate["category"],
                provider=payment["provider"],
                payment_ref=data.reference,
                ip="webhook",
            )

    return {"message": "Callback traité", "status": data.status}


@router.get("/status/{reference}")
async def payment_status(reference: str, db: aiosqlite.Connection = Depends(get_db)):
    """
    Polling côté frontend (toutes les 3s).
    Interroge aussi Campay pour mettre à jour le statut si encore pending.
    """
    cur = await db.execute(
        "SELECT * FROM payments WHERE reference = ?", (reference,)
    )
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Référence introuvable")

    payment = dict(row)

    # Si encore pending, interroger Campay pour avoir le statut réel
    if payment["status"] == "pending" and CAMPAY_USERNAME:
        campay_status = await _get_campay_payment_status(reference)
        # Campay retourne "SUCCESSFUL" — on normalise en "success"
        if campay_status == "SUCCESSFUL":
            now = datetime.utcnow().isoformat()
            await db.execute(
                "UPDATE payments SET status = 'success', updated_at = ? WHERE reference = ?",
                (now, reference),
            )
            await db.commit()
            # Déclencher l'enregistrement du vote
            fake_callback = PaymentCallback(
                reference=reference, status="success", provider=payment["provider"]
            )
            await payment_callback(fake_callback, db)
            payment["status"] = "success"
        elif campay_status in ("FAILED", "CANCELLED"):
            status_map = {"FAILED": "failed", "CANCELLED": "cancelled"}
            new_status = status_map[campay_status]
            await db.execute(
                "UPDATE payments SET status = ?, updated_at = ? WHERE reference = ?",
                (new_status, datetime.utcnow().isoformat(), reference),
            )
            await db.commit()
            payment["status"] = new_status

    return {
        "reference":  payment["reference"],
        "status":     payment["status"],
        "provider":   payment["provider"],
        "amount":     payment["amount"],
        "phone":      payment["phone"],
        "created_at": payment["created_at"],
    }


@router.get("/mock-confirm/{reference}")
async def mock_confirm_payment(
    reference: str, db: aiosqlite.Connection = Depends(get_db)
):
    """
    ⚠️  DEV ONLY — Simule une confirmation de paiement.
    À SUPPRIMER avant de passer en production réelle !
    """
    cur = await db.execute("SELECT * FROM payments WHERE reference = ?", (reference,))
    payment = await cur.fetchone()
    if not payment:
        raise HTTPException(404, "Référence introuvable")

    fake_callback = PaymentCallback(
        reference=reference, status="success", provider=payment["provider"]
    )
    return await payment_callback(fake_callback, db)
