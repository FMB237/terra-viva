# 🌿 Terra Viva Royalty Day — Plateforme de Vote
> **Club Sciences de l'Environnement × Club AGEPD — ENSPM Maroua**

Plateforme de vote pour **Miss Terra Viva** et **Master Terra Viva** 2025.  
Paiement mobile money : **Orange Money** et **MTN MoMo** (100 FCFA / vote).

---

## 📁 Structure du projet

```
terra-viva/
├── main.py                  # Entry point FastAPI
├── requirements.txt
├── .env.example             # Variables d'environnement (copier en .env)
├── terra_viva.db            # SQLite (auto-créé au démarrage)
├── app/
│   ├── database.py          # Init DB + seed données
│   ├── schemas.py           # Modèles Pydantic
│   └── routers/
│       ├── candidates.py    # CRUD candidats
│       ├── votes.py         # Vote + résultats
│       ├── payments.py      # Orange Money / MTN MoMo (Campay)
│       ├── admin.py         # Stats + settings admin
│       └── auth.py          # Authentification JWT
├── templates/
│   └── index.html           # Frontend complet (SPA)
└── static/                  # Assets statiques (images, etc.)
```

---

## 🚀 Installation et lancement

### 1. Cloner et installer les dépendances

```bash
cd terra-viva
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos credentials Campay
```

### 3. Lancer le serveur

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Ouvrir dans le navigateur

```
http://localhost:8000          # Site public (vote)
http://localhost:8000/docs     # Documentation API Swagger
http://localhost:8000/redoc    # Documentation API ReDoc
```

---

## 🔑 Accès Admin

- **URL** : Cliquer sur "Admin" dans la nav
- **Username** : `admin`
- **Password** : `admin123`  ⚠️ *Changer en production !*

---

## 📱 Intégration paiements mobiles

### Option recommandée : Campay (agrégateur Cameroun)

[Campay](https://campay.net) gère **Orange Money ET MTN MoMo** avec une seule API.

1. S'inscrire sur [campay.net](https://campay.net/en/developers)
2. Obtenir les credentials sandbox
3. Configurer dans `.env` :
   ```
   CAMPAY_APP_USERNAME=votre_username
   CAMPAY_APP_PASSWORD=votre_password
   CAMPAY_BASE_URL=https://demo.campay.net/api
   ```
4. Enregistrer le webhook dans votre dashboard Campay :
   ```
   https://votre-domaine.com/api/payments/callback
   ```

### Mode démo (sans credentials)

Sans credentials Campay, le système tourne en **mode démo** :
- Les paiements sont simulés
- Utiliser le bouton "J'ai confirmé le paiement" → appelle `/api/payments/mock-confirm/{ref}`
- **Retirer cet endpoint en production !**

---

## 🗃️ Base de données

SQLite (légère, pas de serveur requis). Pour passer à PostgreSQL :

```bash
pip install asyncpg databases
# Modifier DB_PATH dans .env avec une URL PostgreSQL
```

---

## 🌐 Déploiement (production)

### Render.com (gratuit)
```bash
# Dans render.yaml ou dashboard :
Build: pip install -r requirements.txt
Start: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Railway
```bash
railway init
railway up
```

### VPS avec Nginx
```nginx
server {
    listen 80;
    server_name voteterraviva.enspm.cm;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

---

## 📡 API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/candidates/` | Liste des candidats |
| `GET` | `/api/candidates/{id}` | Profil d'un candidat |
| `POST` | `/api/candidates/` | Ajouter un candidat (admin) |
| `GET` | `/api/votes/results` | Résultats en direct |
| `GET` | `/api/votes/check/{matricule}` | Vérifier si déjà voté |
| `POST` | `/api/payments/initiate` | Initier paiement OM/MTN |
| `POST` | `/api/payments/callback` | Webhook paiement |
| `GET` | `/api/payments/status/{ref}` | Statut paiement |
| `GET` | `/api/admin/stats` | Statistiques admin |
| `GET` | `/api/admin/settings` | Paramètres |
| `PUT` | `/api/admin/settings` | Modifier paramètres |
| `POST` | `/api/auth/login` | Connexion admin |

---

## 🛡️ Sécurité anti-fraude

- Un vote par catégorie (Miss/Master) par matricule
- Vérification date de naissance
- IP logging et détection anomalies
- Paiement obligatoire avant enregistrement du vote
- Webhook sécurisé pour confirmation paiement

---

*Développé pour le Terra Viva Royalty Day — ENSPM Maroua 2025*  
*Club Sciences de l'Environnement × Club AGEPD*
