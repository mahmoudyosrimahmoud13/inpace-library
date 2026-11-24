"""Project 2: the same data in three data models, and the query each one makes easy or hard.

1. RELATIONAL (SQLite): a profile spread over tables, put back together with joins.
2. DOCUMENT (JSON): the whole profile in one document. One read, good locality, but many-to-one data (the region
   name) is copied into every document, and changing it means rewriting them all.
3. GRAPH (vertices and edges in SQLite): "who was born in the United States and lives in Europe?", the book's
   example, answered with a RECURSIVE query that walks 'within' edges to any depth.
4. SCHEMA ON READ versus SCHEMA ON WRITE: changing how names are stored.

Run:  python p02_data_models.py
"""
import json
import sqlite3

db = sqlite3.connect(":memory:")

# ---------------- 1. Relational ----------------
db.executescript("""
CREATE TABLE regions   (region_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE users     (user_id INTEGER PRIMARY KEY, name TEXT, region_id INTEGER REFERENCES regions);
CREATE TABLE positions (user_id INTEGER REFERENCES users, title TEXT, company TEXT);
CREATE TABLE education (user_id INTEGER REFERENCES users, school TEXT, years TEXT);
INSERT INTO regions VALUES (1, 'Greater Cairo'), (2, 'Alexandria');
INSERT INTO users VALUES (1, 'Mona Hassan', 1), (2, 'Omar Saleh', 1), (3, 'Laila Nabil', 2);
INSERT INTO positions VALUES (1, 'Data engineer', 'Inkwell'), (1, 'Analyst', 'Nile Bank'), (2, 'Backend developer', 'Chirp'),
                             (3, 'SRE', 'Delta Cloud');
INSERT INTO education VALUES (1, 'Cairo University', '2015-2019'), (2, 'AUC', '2016-2020'), (3, 'Alexandria University', '2014-2018');
""")
q = """SELECT u.name, r.name, p.title, p.company, e.school
       FROM users u JOIN regions r USING (region_id) LEFT JOIN positions p USING (user_id)
       LEFT JOIN education e USING (user_id) WHERE u.user_id = 1"""
rows = db.execute(q).fetchall()
print("1. Relational: profile of user 1 needs 3 joins and comes back as", len(rows), "rows to stitch together:")
for r in rows:
    print("  ", r)

# ---------------- 2. Document ----------------
docs = {}
for uid, name, region in db.execute("SELECT user_id, u.name, r.name FROM users u JOIN regions r USING (region_id)"):
    docs[uid] = {
        "user_id": uid, "name": name, "region": region,          # the region NAME is copied into the document
        "positions": [{"title": t, "company": c} for t, c in
                      db.execute("SELECT title, company FROM positions WHERE user_id = ?", (uid,))],
        "education": [{"school": s, "years": y} for s, y in
                      db.execute("SELECT school, years FROM education WHERE user_id = ?", (uid,))],
    }
print("\n2. Document: the same profile is one read of one JSON document:")
print("  ", json.dumps(docs[1])[:150], "...")

# The region is renamed. Relational: one row. Documents: every document that copied it.
db.execute("UPDATE regions SET name = 'Cairo metropolitan area' WHERE region_id = 1")
touched = 0
for d in docs.values():
    if d["region"] == "Greater Cairo":
        d["region"] = "Cairo metropolitan area"
        touched += 1
print(f"   Renaming a region: relational updates 1 row; documents needed {touched} rewrites "
      f"(and a missed one would disagree forever).")

# ---------------- 3. Graph ----------------
db.executescript("""
CREATE TABLE vertices (vertex_id INTEGER PRIMARY KEY, label TEXT, name TEXT);
CREATE TABLE edges    (tail INTEGER, head INTEGER, label TEXT);
INSERT INTO vertices VALUES
  (1,'location','North America'),(2,'location','United States'),(3,'location','Idaho'),
  (4,'location','Europe'),(5,'location','France'),(6,'location','United Kingdom'),(7,'location','London'),
  (8,'location','Africa'),(9,'location','Egypt'),(10,'location','Cairo'),
  (20,'person','Lucy'),(21,'person','Alain'),(22,'person','Mona'),(23,'person','Sam');
INSERT INTO edges VALUES
  (2,1,'within'),(3,2,'within'),(5,4,'within'),(6,4,'within'),(7,6,'within'),(9,8,'within'),(10,9,'within'),
  (20,3,'born_in'),(20,7,'lives_in'),          -- Lucy: born in Idaho, lives in London
  (21,5,'born_in'),(21,7,'lives_in'),          -- Alain: born in France, lives in London
  (22,10,'born_in'),(22,7,'lives_in'),         -- Mona: born in Cairo, lives in London
  (23,2,'born_in'),(23,10,'lives_in');         -- Sam: born in the US, lives in Cairo
""")
q_graph = """
WITH RECURSIVE
  in_usa(vertex_id) AS (SELECT vertex_id FROM vertices WHERE name = 'United States'
                        UNION SELECT e.tail FROM edges e JOIN in_usa ON e.head = in_usa.vertex_id WHERE e.label = 'within'),
  in_europe(vertex_id) AS (SELECT vertex_id FROM vertices WHERE name = 'Europe'
                        UNION SELECT e.tail FROM edges e JOIN in_europe ON e.head = in_europe.vertex_id WHERE e.label = 'within'),
  born_usa(vertex_id) AS (SELECT e.tail FROM edges e JOIN in_usa ON e.head = in_usa.vertex_id WHERE e.label = 'born_in'),
  lives_europe(vertex_id) AS (SELECT e.tail FROM edges e JOIN in_europe ON e.head = in_europe.vertex_id WHERE e.label = 'lives_in')
SELECT name FROM vertices JOIN born_usa USING (vertex_id) JOIN lives_europe USING (vertex_id)"""
print("\n3. Graph: born in the United States, living in Europe:", [r[0] for r in db.execute(q_graph)])
print("   Lucy was born in Idaho (1 'within' step below the US) and lives in London (2 steps below Europe).")
print("   The query doesn't know the depth in advance: that's what recursive queries and graph languages are for.")


def path_up(vertex: int) -> list:
    """The same walk in plain Python: follow 'within' edges until there are none."""
    out = []
    while True:
        nxt = db.execute("SELECT head FROM edges WHERE tail = ? AND label = 'within'", (vertex,)).fetchone()
        name = db.execute("SELECT name FROM vertices WHERE vertex_id = ?", (vertex,)).fetchone()[0]
        out.append(name)
        if not nxt:
            return out
        vertex = nxt[0]


print("   Walk from Idaho:", " -> ".join(path_up(3)))

# ---------------- 4. Schema on read versus schema on write ----------------
# The app now wants first names. Schema on write (relational): migrate every row once, then every reader is simple.
db.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
db.execute("UPDATE users SET first_name = substr(name, 1, instr(name, ' ') - 1)")
# Schema on read (documents): leave old documents alone; new ones get the field; READERS handle both shapes.
docs[4] = {"user_id": 4, "first_name": "Sara", "name": "Sara Kamel", "region": "Alexandria", "positions": [], "education": []}


def first_name(doc: dict) -> str:
    return doc.get("first_name") or doc["name"].split(" ")[0]   # every reader needs this fallback, forever


print("\n4. Schema on write:", [r[0] for r in db.execute("SELECT first_name FROM users")])
print("   Schema on read: ", [first_name(d) for d in docs.values()])
