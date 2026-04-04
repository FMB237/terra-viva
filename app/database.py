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

            -- Seed demo candidates
            INSERT OR IGNORE INTO candidates(id,name,category,department,year,age,bio,quote,status) VALUES
            (1,'Aïcha Mahamat','miss','Sciences Environnementales','Licence 3',22,
             'Ambassadrice du Club SCI-ENV, Aïcha mène des recherches sur la biodiversité du bassin du lac Tchad. Passionnée de danses traditionnelles soudano-sahéliennes, elle représente la fierté de la région.',
             'La nature n''est pas un héritage de nos parents, c''est un emprunt de nos enfants.','active'),
            (2,'Fatima Youssouf','miss','Agriculture Élevage et Produits Dérivés','Licence 2',21,
             'Membre active du Club AGEPD-ENSPM, Fatima œuvre pour la valorisation des produits agro-pastoraux locaux. Musicienne traditionnelle grassfield, elle allie science et culture.',
             'Nourrir le Cameroun par l''intelligence de ses fils et filles.','active'),
            (3,'Claudine Ngassa','miss','Sciences Environnementales','Master 1',23,
             'Chercheuse en écologie des zones arides, Claudine développe des solutions numériques de surveillance environnementale. Représentante du peuple Fang-Béti au sein de l''ENSPM.',
             'Le code peut sauver la planète si on lui donne la bonne direction.','active'),
            (4,'Mariam Bello','miss','Agriculture Élevage et Produits Dérivés','Licence 1',20,
             'Première de sa famille à accéder à l''enseignement supérieur polytechnique, Mariam porte les valeurs rurales du Nord Cameroun. Danseuse traditionnelle sawa.',
             'Les racines profondes résistent aux tempêtes les plus violentes.','active'),
            (5,'Edith Tchana','miss','Sciences Environnementales','Licence 3',22,
             'Spécialiste en gestion durable des ressources forestières, Edith participe activement aux expositions stands culturels de l''ENSPM. Interprète musicale traditionnelle.',
             'Protéger la forêt, c''est protéger notre avenir.','active'),
            (6,'Nadia Sali','miss','Agriculture Élevage et Produits Dérivés','Master 2',24,
             'Chercheuse en agro-écologie sahélienne, Nadia représente l''excellence académique de l''ENSPM. Elle coordonne les ateliers photo lors des foires culturelles.',
             'Chaque graine plantée est un espoir pour demain.','active'),

            (7,'Ibrahim Moussa','master','Sciences Environnementales','Master 2',25,
             'Président du Club SCI-ENV, Ibrahim est spécialiste de la gestion durable des ressources en eau dans le bassin du lac Tchad. Leader engagé et danseur grassfield.',
             'L''eau est la vie — préservons-la pour les générations futures.','active'),
            (8,'Rodrigue Nkamba','master','Agriculture Élevage et Produits Dérivés','Master 1',24,
             'Co-fondateur du Club AGEPD-ENSPM, Rodrigue mène des recherches sur l''élevage durable en zone sahélienne. Représentant culturel du peuple Sawa.',
             'L''agro-pastoralisme durable est la clé de la sécurité alimentaire africaine.','active'),
            (9,'Alexis Foka','master','Sciences Environnementales','Licence 3',23,
             'Développeur de systèmes SIG pour le suivi de la déforestation, Alexis allie informatique et écologie. Passionné de stand-up et sketches lors des foires culturelles ENSPM.',
             'La data au service de la planète, l''humain au centre de tout.','active'),
            (10,'Moïse Mbessa','master','Agriculture Élevage et Produits Dérivés','Licence 2',22,
             'Passionné d''agro-écologie régénérative, Moïse développe des modèles agricoles adaptés aux zones semi-arides du Nord Cameroun. Interprète musical traditionnel fang-béti.',
             'La terre nous nourrit si on prend soin d''elle.','active'),
            (11,'Patrick Essama','master','Sciences Environnementales','Licence 3',24,
             'Chercheur en climatologie sahélienne, Patrick sensibilise les communautés locales aux effets des changements climatiques. Coordinateur des parades culturelles ENSPM.',
             'Le Sahel n''est pas condamné si nous agissons ensemble maintenant.','active'),
            (12,'Junior Wanko','master','Agriculture Élevage et Produits Dérivés','Licence 1',20,
             'Fils d''éleveur, Junior utilise la technologie pour moderniser les pratiques pastorales traditionnelles. Photographe lors des ateliers photo des foires culturelles.',
             'Honorer nos traditions tout en embrassant l''avenir technologique.','active');

            -- Default admin (password: admin123 — CHANGER EN PRODUCTION!)
            INSERT OR IGNORE INTO admins(username, password_hash, role)
            VALUES('admin',
                   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGniAg7uk1.hZWq.zNDAMwm6KqW',
                   'super_admin');
        """)
        await db.commit()
        print("✅ DB initialisée — Terra Viva Royalty Day · ENSPM Maroua · 9 Mai 2026")
