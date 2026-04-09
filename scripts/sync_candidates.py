import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "terra_viva.db")

CANDIDATE_UPDATES = [
    {
        "id": 1,
        "name": "MAFOCK KINGNE PELAGIE",
        "category": "miss",
        "department": "Informatique et Télécommunication",
        "year": "Niveau 1",
        "age": None,
        "bio": "Je suis née dans les paysages majestueux de l’Ouest, là où les forêts et les rivières racontent des histoires anciennes. Grandi dans le Septentrion, au cœur du Grand Nord, j’ai vu la richesse de nos terres, la beauté des montagnes et la fragilité des écosystèmes face aux changements qui les menacent. Ces observations ont éveillé en moi la volonté de comprendre et d’agir. C’est naturellement que je me suis tournée vers l’informatique et les télécommunications, convaincue que la technologie pouvait devenir un outil puissant pour préserver notre environnement, tout en reliant modernité et respect des racines de ma terre.",
        "quote": "Allier technologie et racines pour protéger la biodiversité, préserver notre héritage et réaliser l’ambition de Terra Viva.",
        "photo_url": "/static/images/mafock_kingne_pelagie.jpg",
        "status": "active",
    },
    {
        "id": 2,
        "name": "ZAITOUNA ADAMA",
        "category": "miss",
        "department": "Sciences environnementales",
        "year": "Niveau 2",
        "age": None,
        "bio": "Mon déclic pour l’environnement est né en observant la résilience de nos paysages du Septentrion. Voir la terre se fragiliser face à l'avancée du désert dans mon Grand Nord natal m’a poussée vers l’ingénierie environnementale.",
        "quote": "Mandara du Grand Nord et ingénieur, je lie racines et science pour l’ambition de Terra Viva.",
        "photo_url": "/static/images/zaitouna_adama.jpg",
        "status": "active",
    },
    {
        "id": 3,
        "name": "NUCK CÉCILE",
        "category": "miss",
        "department": "Sciences environnementales",
        "year": "IC1",
        "age": None,
        "bio": "Participer à un concours de miss a été une expérience marquante pour moi. Au-delà de l’apparence, j’ai appris à m’exprimer, à défendre des valeurs et à représenter une cause. C’est à ce moment que j’ai compris que j’avais une voix. Aujourd’hui, je choisis de l’utiliser pour sensibiliser à la protection de l’environnement. En tant qu’étudiante en sciences environnementales, je veux être une ambassadrice d’une terre vivante… Terra Viva.",
        "quote": "Agir localement, penser globalement: sensibiliser, recycler et reverdir pour une terre vivante et résiliente demain.",
        "photo_url": "/static/images/nuck_cecile.jpg",
        "status": "active",
    },
    {
        "id": 4,
        "name": "ANGUE OBAM MANUELLA ANNA",
        "category": "miss",
        "department": "Génie civil",
        "year": "Niveau 1",
        "age": None,
        "bio": "Mon déclic pour le génie civil est né avec l'intention de protéger la communauté au travers de la construction des routes et des maisons durables, suite à de nombreuses situations telles que des inondations.",
        "quote": "Génie civil au service de l'écosystème: bâtir un avenir vert pour la biodiversité camerounaise.",
        "photo_url": "/static/images/angue_obam_manuella_anna.jpg",
        "status": "active",
    },
    {
        "id": 5,
        "name": "SIGNING FRANK BRONDON",
        "category": "master",
        "department": "Agriculture, Élevage et Produits Dérivés (AGEPD)",
        "year": "Niveau 4",
        "age": None,
        "bio": "Entrepreneuriat.",
        "quote": "Valorisation des déjections animales en biogaz pour énergie propre et fertilisation durable des cultures locales.",
        "photo_url": "/static/images/signing_frank_brondon.jpg",
        "status": "active",
    },
    {
        "id": 6,
        "name": "ISSA NADJE SAMOUPA",
        "category": "master",
        "department": "Agriculture, Élevage et Produits Dérivés (AGEPD)",
        "year": "Niveau 1",
        "age": None,
        "bio": "L’expérience dans le mannequinat et le ventes en ligne.",
        "quote": "La valorisation des déchets animaux transforme fumier et résidus en énergie, engrais organiques, réduisant pollution et renforçant agriculture durable.",
        "photo_url": "/static/images/issa_nadje_samoupa.jpg",
        "status": "active",
    },
    {
        "id": 7,
        "name": "ANAËL NDENGUE",
        "category": "master",
        "department": "Énergie renouvelable (ENREN)",
        "year": "IC2",
        "age": None,
        "bio": "Restaurateur et enseignant.",
        "quote": "L'élégance au service de l'environnement, la nature est une source d'inspiration.",
        "photo_url": "/static/images/anael_ndengue.jpg",
        "status": "active",
    },
    {
        "id": 8,
        "name": "AMOUGOU METOGO ELYSÉE",
        "category": "master",
        "department": "Sciences environnementales",
        "year": "Niveau 1",
        "age": None,
        "bio": "Originaire du Centre du Cameroun. J’ai grandi entouré de verdure… mais j’ai aussi vu cette verdure disparaître, lentement, silencieusement. Là où il y avait des arbres, il y a aujourd’hui de la chaleur. Là où il y avait de la vie, il y a parfois du vide. Ce constat m’a marqué. Il m’a surtout donné une conviction : si nous ne faisons rien, nous perdrons bien plus que des arbres… nous perdrons notre équilibre. Alors j’ai décidé d’agir. Parce que protéger l’environnement, ce n’est pas une option, c’est une urgence, et surtout une responsabilité.",
        "quote": "Un jeune, un arbre : Reverdir notre communauté.",
        "photo_url": "/static/images/amougou_metogo_elysee.jpg",
        "status": "active",
    },
]


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        updated = 0
        inserted = 0
        for c in CANDIDATE_UPDATES:
            cur = conn.execute("SELECT id FROM candidates WHERE id = ?", (c["id"],))
            exists = cur.fetchone()
            if exists:
                conn.execute(
                    """UPDATE candidates
                       SET name = ?, category = ?, department = ?, year = ?, age = ?, bio = ?, quote = ?, photo_url = ?, status = ?
                       WHERE id = ?""",
                    (
                        c["name"], c["category"], c["department"], c["year"], c["age"],
                        c["bio"], c["quote"], c["photo_url"], c["status"], c["id"],
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    """INSERT INTO candidates
                       (id, name, category, department, year, age, bio, quote, photo_url, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        c["id"], c["name"], c["category"], c["department"], c["year"], c["age"],
                        c["bio"], c["quote"], c["photo_url"], c["status"],
                    ),
                )
                inserted += 1
        conn.commit()
        print(f"Done. updated={updated} inserted={inserted}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
