import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "terra_viva.db")


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
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
                matricule        TEXT NOT NULL UNIQUE,
                date_of_birth    TEXT NOT NULL,
                phone            TEXT,
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
                amount          INTEGER NOT NULL DEFAULT 100,
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
            INSERT OR IGNORE INTO settings VALUES ('vote_price',           '100');
            INSERT OR IGNORE INTO settings VALUES ('event_date',           '2026-05-09');
            INSERT OR IGNORE INTO settings VALUES ('event_time',           '13:00');
            INSERT OR IGNORE INTO settings VALUES ('event_venue',          'Alliance Française de Garoua, Antenne de Maroua');
            INSERT OR IGNORE INTO settings VALUES ('voting_deadline',      '2026-05-08 23:59:00');
            INSERT OR IGNORE INTO settings VALUES ('event_name',           'Terra Viva Royalty Day');
            INSERT OR IGNORE INTO settings VALUES ('edition',              '2026');

            -- Seed candidates (from candidate.txt)
            INSERT OR IGNORE INTO candidates(id,name,category,department,year,age,bio,quote,status) VALUES
            (1,'MAFOCK KINGNE PELAGIE','miss','Informatique et télécommunications','Niveau 1',NULL,
             'Groupe ethnique : grassfields',NULL,'active'),
            (2,'ZAITOUNA ADAMA','miss','Sciences environnementales','Niveau 2',NULL,
             'Groupe ethnique : soudano sahélien',NULL,'active'),
            (3,'NUCK CÉCILE','miss','Sciences environnementales','Niveau 1',NULL,
             'Groupe ethnique : SAWA',NULL,'active'),
            (4,'ANGUE OBAM MANUELLA','miss','Génie civil','Niveau 1',NULL,
             'Groupe ethnique : fang-beti',NULL,'active'),

            (5,'SIGNING FRANK BRONDON','master','AGEPD/PAA','Niveau 4',NULL,
             'Groupe ethnique : grassfields',NULL,'active'),
            (6,'ISSA NADJE SAMOUPA','master','AGEPD','Niveau 1',NULL,
             'Groupe ethnique : soudano sahélien',NULL,'active'),
            (7,'ANAËL NDENGUE','master','Énergie renouvelable','Niveau 2',NULL,
             'Groupe ethnique : SAWA',NULL,'active'),
            (8,'AMOUGOU METOGO ELYSÉE','master','Sciences environnementales','Niveau 1',NULL,
             'Groupe ethnique : fang-beti',NULL,'active');

            -- Default admin (password: admin123 — CHANGER EN PRODUCTION!)
            INSERT OR IGNORE INTO admins(username, password_hash, role)
            VALUES('admin',
                   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGniAg7uk1.hZWq.zNDAMwm6KqW',
                   'super_admin');
        """)
        await db.commit()
        print("✅ DB initialisée — Terra Viva Royalty Day · ENSPM Maroua · 9 Mai 2026")
