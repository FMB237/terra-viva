import os
import aiosqlite
import asyncio

DB_PATH = os.getenv("DB_PATH", "terra_viva.db")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + DB_PATH)

# Simple DB adapter that supports both sqlite (aiosqlite) and Postgres (asyncpg)
# Provides async methods: fetch_one, fetch_all, execute, executescript, commit

class DBResult:
    def __init__(self, lastrowid=None):
        self.lastrowid = lastrowid


class DB:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_sqlite = database_url.startswith("sqlite") or database_url.startswith("sqlite://")
        self.sqlite_path = DB_PATH
        self._pool = None

    async def connect(self):
        if not self.is_sqlite:
            import asyncpg
            self._pool = await asyncpg.create_pool(self.database_url)

    async def close(self):
        if self._pool:
            await self._pool.close()

    def _convert_placeholders(self, query: str):
        # Replace sqlite-style ? placeholders with $1, $2, ... for asyncpg
        parts = []
        idx = 1
        i = 0
        while True:
            j = query.find("?", i)
            if j == -1:
                parts.append(query[i:])
                break
            parts.append(query[i:j])
            parts.append(f"${idx}")
            idx += 1
            i = j + 1
        return "".join(parts)

    async def fetch_one(self, query: str, params: tuple | list | None = None):
        params = params or []
        if self.is_sqlite:
            async with aiosqlite.connect(self.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute(query, tuple(params))
                row = await cur.fetchone()
                return row
        else:
            async with self._pool.acquire() as conn:
                q = self._convert_placeholders(query)
                row = await conn.fetchrow(q, *params)
                return row

    async def fetch_all(self, query: str, params: tuple | list | None = None):
        params = params or []
        if self.is_sqlite:
            async with aiosqlite.connect(self.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute(query, tuple(params))
                rows = await cur.fetchall()
                return rows
        else:
            async with self._pool.acquire() as conn:
                q = self._convert_placeholders(query)
                rows = await conn.fetch(q, *params)
                return rows

    async def execute(self, query: str, params: tuple | list | None = None):
        params = params or []
        if self.is_sqlite:
            async with aiosqlite.connect(self.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute(query, tuple(params))
                await conn.commit()
                last = getattr(cur, 'lastrowid', None)
                return DBResult(lastrowid=last)
        else:
            async with self._pool.acquire() as conn:
                q = query
                # If params present, convert placeholders
                if params:
                    q = self._convert_placeholders(query)
                # For INSERT, return the inserted id when possible
                if query.strip().lower().startswith('insert') and 'returning' not in query.lower():
                    q = q + ' RETURNING id'
                    row = await conn.fetchrow(self._convert_placeholders(q), *params)
                    return DBResult(lastrowid=row['id'] if row else None)
                else:
                    await conn.execute(q, *params)
                    return DBResult()

    async def executescript(self, script: str):
        if self.is_sqlite:
            async with aiosqlite.connect(self.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.executescript(script)
                await conn.commit()
        else:
            # asyncpg supports multiple statements in execute
            async with self._pool.acquire() as conn:
                await conn.execute(script)

    async def commit(self):
        # No-op: individual operations commit immediately in both adapters
        return


# module-level DB instance
db = DB(DATABASE_URL)


async def get_db():
    # Returns the DB adapter instance (stateless; acquires connections per call)
    yield db


async def init_db():
    # Initialize DB schema using the same script as before
    schema = """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS candidates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                category    TEXT NOT NULL CHECK(category IN ('miss','master')),
                department  TEXT NOT NULL,
                year        TEXT NOT NULL,
                age         INTEGER,
                bio         TEXT,
                quote       TEXT,
                photo_url   TEXT,
                status      TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','draft','disqualified')),
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS voters (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name        TEXT,
                email            TEXT,
                phone            TEXT NOT NULL,
                is_student       INTEGER DEFAULT 0,
                matricule        TEXT UNIQUE,
                has_voted_miss   INTEGER DEFAULT 0,
                has_voted_master INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS votes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id   INTEGER NOT NULL REFERENCES candidates(id),
                voter_id       INTEGER NOT NULL REFERENCES voters(id),
                category       TEXT NOT NULL CHECK(category IN ('miss','master')),
                payment_method TEXT NOT NULL
                               CHECK(payment_method IN ('orange_money','mtn_momo')),
                payment_ref    TEXT,
                ip_address     TEXT,
                created_at     TEXT DEFAULT (datetime('now')),
                UNIQUE(voter_id, category)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                reference       TEXT NOT NULL UNIQUE,
                phone           TEXT NOT NULL,
                amount          INTEGER NOT NULL DEFAULT 25,
                provider        TEXT NOT NULL
                                CHECK(provider IN ('orange_money','mtn_momo')),
                status          TEXT NOT NULL DEFAULT 'pending'
                                CHECK(status IN ('pending','success','failed','cancelled')),
                candidate_id    INTEGER REFERENCES candidates(id),
                voter_matricule TEXT,
                metadata        TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS admins (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'moderator'
                              CHECK(role IN ('super_admin','moderator')),
                last_login    TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- Default settings
            INSERT OR IGNORE INTO settings VALUES ('voting_open',          'true');
            INSERT OR IGNORE INTO settings VALUES ('results_public',       'true');
            INSERT OR IGNORE INTO settings VALUES ('orange_money_enabled', 'true');
            INSERT OR IGNORE INTO settings VALUES ('mtn_momo_enabled',     'true');
            INSERT OR IGNORE INTO settings VALUES ('vote_price',           '25');
            INSERT OR IGNORE INTO settings VALUES ('event_date',           '2026-05-09');
            INSERT OR IGNORE INTO settings VALUES ('event_time',           '13:00');
            INSERT OR IGNORE INTO settings VALUES ('event_venue',          'Alliance Française de Garoua, Antenne de Maroua');
            INSERT OR IGNORE INTO settings VALUES ('voting_deadline',      '2026-05-08 23:59:00');
            INSERT OR IGNORE INTO settings VALUES ('event_name',           'Terra Viva Royalty Day');
            INSERT OR IGNORE INTO settings VALUES ('edition',              '2026');

            -- Seed candidates (from candidate.txt)
            INSERT OR IGNORE INTO candidates(id,name,category,department,year,age,bio,quote,photo_url,status) VALUES
            (1,'MAFOCK KINGNE PELAGIE','miss','Informatique et Télécommunication','Niveau 1',NULL,
             'Je suis née dans les paysages majestueux de l’Ouest, là où les forêts et les rivières racontent des histoires anciennes. Grandi dans le Septentrion, au cœur du Grand Nord, j’ai vu la richesse de nos terres, la beauté des montagnes et la fragilité des écosystèmes face aux changements qui les menacent. Ces observations ont éveillé en moi la volonté de comprendre et d’agir. C’est naturellement que je me suis tournée vers l’informatique et les télécommunications, convaincue que la technologie pouvait devenir un outil puissant pour préserver notre environnement, tout en reliant modernité et respect des racines de ma terre.',
             'Allier technologie et racines pour protéger la biodiversité, préserver notre héritage et réaliser l’ambition de Terra Viva.',
             '/static/images/mafock_kingne_pelagie.jpg','active'),
            (2,'ZAITOUNA ADAMA','miss','Sciences environnementales','Niveau 2',NULL,
             'Mon déclic pour l’environnement est né en observant la résilience de nos paysages du Septentrion. Voir la terre se fragiliser face à l''avancée du désert dans mon Grand Nord natal m’a poussée vers l’ingénierie environnementale.',
             'Mandara du Grand Nord et ingénieur, je lie racines et science pour l’ambition de Terra Viva.',
             '/static/images/zaitouna_adama.jpg','active'),
            (3,'NUCK CÉCILE','miss','Sciences environnementales','IC1',NULL,
             'Participer à un concours de miss a été une expérience marquante pour moi. Au-delà de l’apparence, j’ai appris à m’exprimer, à défendre des valeurs et à représenter une cause. C’est à ce moment que j’ai compris que j’avais une voix. Aujourd’hui, je choisis de l’utiliser pour sensibiliser à la protection de l’environnement. En tant qu’étudiante en sciences environnementales, je veux être une ambassadrice d’une terre vivante… Terra Viva.',
             'Agir localement, penser globalement: sensibiliser, recycler et reverdir pour une terre vivante et résiliente demain.',
             '/static/images/nuck_cecile.jpg','active'),
            (4,'ANGUE OBAM MANUELLA ANNA','miss','Génie civil','Niveau 1',NULL,
             'Mon déclic pour le génie civil est né avec l''intention de protéger la communauté au travers de la construction des routes et des maisons durables, suite à de nombreuses situations telles que des inondations.',
             'Génie civil au service de l''écosystème: bâtir un avenir vert pour la biodiversité camerounaise.',
             '/static/images/angue_obam_manuella_anna.jpg','active'),

            (5,'SIGNING FRANK BRONDON','master','Agriculture, Élevage et Produits Dérivés (AGEPD)','Niveau 4',NULL,
             'Entrepreneuriat.',
             'Valorisation des déjections animales en biogaz pour énergie propre et fertilisation durable des cultures locales.',
             '/static/images/signing_frank_brondon.jpg','active'),
            (6,'ISSA NADJE SAMOUPA','master','Agriculture, Élevage et Produits Dérivés (AGEPD)','Niveau 1',NULL,
             'L’expérience dans le mannequinat et le ventes en ligne.',
             'La valorisation des déchets animaux transforme fumier et résidus en énergie, engrais organiques, réduisant pollution et renforçant agriculture durable.',
             '/static/images/issa_nadje_samoupa.jpg','active'),
            (7,'ANAËL NDENGUE','master','Énergie renouvelable (ENREN)','IC2',NULL,
             'Restaurateur et enseignant.',
             'L''élégance au service de l''environnement, la nature est une source d''inspiration.',
             '/static/images/anael_ndengue.jpg','active'),
            (8,'AMOUGOU METOGO ELYSÉE','master','Sciences environnementales','Niveau 1',NULL,
             'Originaire du Centre du Cameroun. J’ai grandi entouré de verdure… mais j’ai aussi vu cette verdure disparaître, lentement, silencieusement. Là où il y avait des arbres, il y a aujourd’hui de la chaleur. Là où il y avait de la vie, il y a parfois du vide. Ce constat m’a marqué. Il m’a surtout donné une conviction : si nous ne faisons rien, nous perdrons bien plus que des arbres… nous perdrons notre équilibre. Alors j’ai décidé d’agir. Parce que protéger l’environnement, ce n’est pas une option, c’est une urgence, et surtout une responsabilité.',
             'Un jeune, un arbre : Reverdir notre communauté.',
             '/static/images/amougou_metogo_elysee.jpg','active');

            -- Default admin (password: Th@9Sand5uNny — CHANGER EN PRODUCTION!)
            -- First: Update any existing 'admin' user to Miguel
            UPDATE admins SET username='Miguel', password_hash='$2b$12$TB6Oq.ucMurr3duerrjKGufn8VkclzG.HcwGsfldH3s2fwH1w0/FO' WHERE username='admin';
            -- Second: Ensure Miguel exists (creates if not exists, updates if id=1 exists)
            INSERT OR REPLACE INTO admins(id, username, password_hash, role)
            VALUES(1, 'Miguel',
                   '$2b$12$TB6Oq.ucMurr3duerrjKGufn8VkclzG.HcwGsfldH3s2fwH1w0/FO',
                   'super_admin');
            """
    # Create/Connect depending on adapter
    await db.connect()
    await db.executescript(schema)

    # Migrate old voters schema if needed
    row = await db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='voters'")
    if row:
        cols_rows = await db.fetch_all("PRAGMA table_info(voters)")
        cols = [r["name"] if isinstance(r, dict) or hasattr(r, 'get') else r[1] for r in cols_rows]
        if "date_of_birth" in cols or "full_name" not in cols or "is_student" not in cols:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS voters_new (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name        TEXT,
                    email            TEXT,
                    phone            TEXT NOT NULL,
                    is_student       INTEGER DEFAULT 0,
                    matricule        TEXT UNIQUE,
                    has_voted_miss   INTEGER DEFAULT 0,
                    has_voted_master INTEGER DEFAULT 0,
                    created_at       TEXT DEFAULT (datetime('now'))
                );
            """)
            await db.execute("""
                INSERT INTO voters_new (id, full_name, email, phone, is_student, matricule, has_voted_miss, has_voted_master, created_at)
                SELECT id,
                       NULL as full_name,
                       NULL as email,
                       COALESCE(phone, '') as phone,
                       CASE WHEN matricule IS NOT NULL AND matricule != '' THEN 1 ELSE 0 END as is_student,
                       matricule,
                       has_voted_miss,
                       has_voted_master,
                       created_at
                FROM voters
            """)
            await db.executescript("""
                DROP TABLE voters;
                ALTER TABLE voters_new RENAME TO voters;
            """)
    print("✅ DB initialisée — Terra Viva Royalty Day · ENSPM Maroua · 9 Mai 2026")
