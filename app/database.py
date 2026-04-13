import os
import aiosqlite
import asyncio
import ssl

# FIX: Import asyncpg at module level for exception handling
try:
    import asyncpg
except ImportError:
    asyncpg = None

DB_PATH = os.getenv("DB_PATH", "terra_viva.db")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + DB_PATH)


class DBResult:
    def __init__(self, lastrowid=None):
        self.lastrowid = lastrowid


class DB:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_sqlite = database_url.startswith("sqlite") or database_url.startswith(
            "sqlite://"
        )
        self.is_postgres = database_url.startswith("postgres://") or database_url.startswith(
            "postgresql://"
        )
        self.sqlite_path = DB_PATH
        self._pool = None

    async def connect(self):
        if self.is_postgres:
            # SSL required for Render PostgreSQL
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60,
                max_inactive_connection_lifetime=300,
                ssl=ssl_context
            )

    async def close(self):
        if self._pool:
            await self._pool.close()

    def _convert_placeholders(self, query: str):
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
            if not self._pool:
                raise RuntimeError("PostgreSQL pool not initialized. Call connect() first.")
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
            if not self._pool:
                raise RuntimeError("PostgreSQL pool not initialized. Call connect() first.")
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
                last = getattr(cur, "lastrowid", None)
                return DBResult(lastrowid=last)
        else:
            if not self._pool:
                raise RuntimeError("PostgreSQL pool not initialized. Call connect() first.")
            async with self._pool.acquire() as conn:
                q = self._convert_placeholders(query)
                
                # Check if this is an INSERT without RETURNING clause
                is_insert = query.strip().lower().startswith("insert")
                has_returning = "returning" in query.lower()
                
                if is_insert and not has_returning:
                    # For INSERTs without RETURNING, try to add RETURNING id
                    q_with_returning = q + " RETURNING id"
                    try:
                        row = await conn.fetchrow(q_with_returning, *params)
                        return DBResult(lastrowid=row["id"] if row else None)
                    except Exception as e:
                        # If RETURNING id fails (no id column), just execute without it
                        error_str = str(e).lower()
                        if "id" in error_str and ("does not exist" in error_str or "undefinedcolumn" in error_str):
                            await conn.execute(q, *params)
                            return DBResult()
                        else:
                            raise
                else:
                    # For UPDATE, DELETE, or INSERT with existing RETURNING
                    await conn.execute(q, *params)
                    return DBResult()

    async def executescript(self, script: str):
        if self.is_sqlite:
            async with aiosqlite.connect(self.sqlite_path) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.executescript(script)
                await conn.commit()
        else:
            if not self._pool:
                raise RuntimeError("PostgreSQL pool not initialized. Call connect() first.")
            async with self._pool.acquire() as conn:
                statements = [s.strip() for s in script.split(';') if s.strip()]
                for stmt in statements:
                    await conn.execute(stmt)

    async def commit(self):
        return


db = DB(DATABASE_URL)


async def get_db():
    yield db


async def init_db():
    is_sqlite = db.is_sqlite

    if db.is_postgres:
        await db.connect()

    if is_sqlite:
        await db.executescript("PRAGMA journal_mode=WAL;")

    # FIX: For PostgreSQL, drop existing tables to ensure clean schema with id columns
    # WARNING: This will delete existing data! Remove this in production after first deploy.
    if not is_sqlite:
        drop_tables = """
        DROP TABLE IF EXISTS votes CASCADE;
        DROP TABLE IF EXISTS payments CASCADE;
        DROP TABLE IF EXISTS candidates CASCADE;
        DROP TABLE IF EXISTS voters CASCADE;
        DROP TABLE IF EXISTS admins CASCADE;
        DROP TABLE IF EXISTS settings CASCADE;
        """
        await db.executescript(drop_tables)
        print("Dropped existing PostgreSQL tables for clean recreation")

    if is_sqlite:
        candidates_schema = """CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('miss','master')),
            department TEXT NOT NULL, year TEXT NOT NULL, age INTEGER, bio TEXT,
            quote TEXT, photo_url TEXT, status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','draft','disqualified')),
            created_at TEXT DEFAULT (datetime('now')));"""
        voters_schema = """CREATE TABLE IF NOT EXISTS voters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT, email TEXT,
            phone TEXT NOT NULL, is_student INTEGER DEFAULT 0, matricule TEXT UNIQUE,
            has_voted_miss INTEGER DEFAULT 0, has_voted_master INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')));"""
        votes_schema = """CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL
            REFERENCES candidates(id), voter_id INTEGER NOT NULL REFERENCES voters(id),
            category TEXT NOT NULL CHECK(category IN ('miss','master')),
            payment_method TEXT NOT NULL CHECK(payment_method IN ('orange_money','mtn_momo')),
            payment_ref TEXT, ip_address TEXT, created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(voter_id, category));"""
        payments_schema = """CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, reference TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 25,
            provider TEXT NOT NULL CHECK(provider IN ('orange_money','mtn_momo')),
            status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','success','failed','cancelled')),
            candidate_id INTEGER REFERENCES candidates(id), voter_matricule TEXT,
            metadata TEXT, created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')));"""
        admins_schema = """CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'moderator'
            CHECK(role IN ('super_admin','moderator')), last_login TEXT,
            created_at TEXT DEFAULT (datetime('now')));"""
        settings_schema = """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL);"""
    else:
        candidates_schema = """CREATE TABLE IF NOT EXISTS candidates (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('miss','master')),
            department TEXT NOT NULL, year TEXT NOT NULL, age INTEGER, bio TEXT,
            quote TEXT, photo_url TEXT, status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','draft','disqualified')),
            created_at TIMESTAMP DEFAULT NOW());"""
        voters_schema = """CREATE TABLE IF NOT EXISTS voters (
            id SERIAL PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT NOT NULL,
            is_student INTEGER DEFAULT 0, matricule TEXT UNIQUE,
            has_voted_miss INTEGER DEFAULT 0, has_voted_master INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW());"""
        votes_schema = """CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY, candidate_id INTEGER NOT NULL
            REFERENCES candidates(id), voter_id INTEGER NOT NULL REFERENCES voters(id),
            category TEXT NOT NULL CHECK(category IN ('miss','master')),
            payment_method TEXT NOT NULL CHECK(payment_method IN ('orange_money','mtn_momo')),
            payment_ref TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(voter_id, category));"""
        payments_schema = """CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 25,
            provider TEXT NOT NULL CHECK(provider IN ('orange_money','mtn_momo')),
            status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','success','failed','cancelled')),
            candidate_id INTEGER REFERENCES candidates(id), voter_matricule TEXT,
            metadata TEXT, created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW());"""
        admins_schema = """CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'moderator'
            CHECK(role IN ('super_admin','moderator')), last_login TEXT,
            created_at TIMESTAMP DEFAULT NOW());"""
        settings_schema = """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL);"""

    for sql in [
        candidates_schema,
        voters_schema,
        votes_schema,
        payments_schema,
        admins_schema,
        settings_schema,
    ]:
        await db.execute(sql, [])

    settings = [
        ("voting_open", "true"),
        ("results_public", "true"),
        ("orange_money_enabled", "true"),
        ("mtn_momo_enabled", "true"),
        ("vote_price", "25"),
        ("event_date", "2026-05-09"),
        ("event_time", "13:00"),
        ("event_venue", "Alliance Francaise de Garoua, Antenne de Maroua"),
        ("voting_deadline", "2026-05-08 23:59:00"),
        ("event_name", "Terra Viva Royalty Day"),
        ("edition", "2026"),
    ]
    for k, v in settings:
        if is_sqlite:
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", [k, v]
            )
        else:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                [k, v],
            )

    candidates = [
        (
            1,
            "MAFOCK KINGNE PELAGIE",
            "miss",
            "Informatique et Telecommunication",
            "Niveau 1",
            None,
            "Je suis nee dans les paysages majestueux de l'Ouest, la ou les forets et les rivieres racontent des histoires anciennes. Grandi dans le Septentrion, au coeur du Grand Nord, j'ai vu la richesse de nos terres, la beaute des montagnes et la fragilitie des ecosysthemes face aux changements qui les menacent. Ces observations ont eveillien moi la volonti de comprendre et d'agir. C'est naturellement que je me suis tourni vers l'informatique et les telecommunications, convaincue que la technologie pouvait devenir un outil puissant pour preserver notre environnement, tout en reliant modernite et respect des racines de ma terre.",
            "Allier technologie et racines pour proteger la biodiversite, preserver notre heritage et realiser l'ambition de Terra Viva.",
            "/static/images/mafock_kingne_pelagie.jpg",
            "active",
        ),
        (
            2,
            "ZAITOUNA ADAMA",
            "miss",
            "Sciences environnementales",
            "Niveau 2",
            None,
            "Mon declic pour l'environnement est ne en observant la resilience de nos paysages du Septentrion. Voir la terre se fragiliser face a l'avancee du desert dans mon Grand Nord natal m'a poussee vers l'ingenierie environnementale.",
            "Mandara du Grand Nord et ingenieur, je lie racines et science pour l'ambition de Terra Viva.",
            "/static/images/zaitouna_adama.jpg",
            "active",
        ),
        (
            3,
            "NUCK CECILE",
            "miss",
            "Sciences environnementales",
            "IC1",
            None,
            "Participer a un concours de miss a ete une experience marquante pour moi. Au-dela de l'apparence, j'ai appris a m'exprimer, a defender des valeurs et a representer une cause. C'est a ce moment que j'ai compris que j'avais une voix. Aujourd'hui, je choisis de l'utiliser pour sensibilizer a la protection de l'environnement. En tant qu'etudiante en sciences environnementales, je veux etre une ambassadrice d'une terre vivante Terra Viva.",
            "Agir localement, penser globalement: sensibilizer, recycler et reverdir pour une terre vivante et resiliente demain.",
            "/static/images/nuck_cecile.jpg",
            "active",
        ),
        (
            4,
            "ANGUE OBAM MANUELLA ANNA",
            "miss",
            "Genie civil",
            "Niveau 1",
            None,
            "Mon declic pour le genie civil est ne avec l'intention de proteger la communaute au travers de la construction des routes et des maisons durables, suite a de nombreuses situations telles que des inondations.",
            "Genie civil au service de l'ecosysteme: batir un avenir vert pour la biodiversite camerounaise.",
            "/static/images/angue_obam_manuella_anna.jpg",
            "active",
        ),
        (
            5,
            "SIGNING FRANK BRONDON",
            "master",
            "Agriculture, Elevage et Produits Derives (AGEPD)",
            "Niveau 4",
            None,
            "Entrepreneuriat.",
            "Valorisation des dejections animales en biogaz pour energie propre et fertilisation durable des cultures locales.",
            "/static/images/signing_frank_brondon.jpg",
            "active",
        ),
        (
            6,
            "ISSA NADJE SAMOUPA",
            "master",
            "Agriculture, Elevage et Produits Derives (AGEPD)",
            "Niveau 1",
            None,
            "L'experience dans le mannequinat et le ventes en ligne.",
            "La valorisation des dechets animaux transforme fumier et residus en energie, engrais organiques, reduisant pollution et renforcant agriculture durable.",
            "/static/images/issa_nadje_samoupa.jpg",
            "active",
        ),
        (
            7,
            "ANAEL NDENGUE",
            "master",
            "Energie renouvelable (ENREN)",
            "IC2",
            None,
            "Restaurateur et enseignant.",
            "L'elegance au service de l'environnement, la nature est une source d'inspiration.",
            "/static/images/anael_ndengue.jpg",
            "active",
        ),
        (
            8,
            "AMOUGOU METOGO ELYSEE",
            "master",
            "Sciences environnementales",
            "Niveau 1",
            None,
            "Originaire du Centre du Cameroun. J'ai grandi entoure de verdure mais j'ai aussi vu cette verdure disparaitre, lentement, silencieusement. La ou il y avait des arbres, il y a aujourd'hui de la chaleur. La ou il y avait de la vie, il y a parfois du vide. Ce constat m'a marque. Il m'a surtout donne une conviction : si nous ne faisons rien, nous perdrons bien plus que des arbres nous perdrons notre equilibre. Alors j'ai decide d'agir. Parce que proteger l'environnement, ce n'est pas une option, c'est une urgence, et surtout une responsabilite.",
            "Un jeune, un arbre : Reverdir notre communaute.",
            "/static/images/amougou_metogo_elysee.jpg",
            "active",
        ),
    ]

    for row in candidates:
        if is_sqlite:
            await db.execute(
                "INSERT OR IGNORE INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                list(row),
            )
        else:
            await db.execute(
                """INSERT INTO candidates (id, name, category, department, year, age, bio, quote, photo_url, status) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) 
                   ON CONFLICT (id) DO NOTHING""",
                list(row),
            )

    admin_pw = "$2b$12$TB6Oq.ucMurr3duerrjKGufn8VkclzG.HcwGsfldH3s2fwH1w0/FO"
    if is_sqlite:
        await db.execute(
            "UPDATE admins SET username='Miguel', password_hash=? WHERE username='admin'",
            [admin_pw],
        )
        await db.execute(
            "INSERT OR REPLACE INTO admins(id, username, password_hash, role) VALUES(1, 'Miguel', ?, 'super_admin')",
            [admin_pw],
        )
    else:
        await db.execute(
            """INSERT INTO admins (id, username, password_hash, role) 
               VALUES (1, 'Miguel', $1, 'super_admin') 
               ON CONFLICT (id) DO UPDATE SET username = 'Miguel', password_hash = $1, role = 'super_admin'""",
            [admin_pw],
        )
    print("DB initialisee - Terra Viva Royalty Day - ENSPM Maroua - 9 Mai 2026")