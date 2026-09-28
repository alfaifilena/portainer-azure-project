"""SQLite persistence. WAL files live beside the database on the data disk."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notices(
                id TEXT PRIMARY KEY, env INTEGER NOT NULL, cid TEXT NOT NULL,
                kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, count INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS notice_env ON notices(env,updated);
            CREATE TABLE IF NOT EXISTS reads(
                uid INTEGER NOT NULL, notice TEXT NOT NULL, seen REAL NOT NULL,
                PRIMARY KEY(uid,notice));
            CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, env INTEGER NOT NULL, cid TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
                result TEXT, error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(status,created);
            CREATE TABLE IF NOT EXISTS telegram_alerts(
                id TEXT PRIMARY KEY, message TEXT NOT NULL, created REAL NOT NULL,
                last_sent REAL NOT NULL, attempts INTEGER NOT NULL, due REAL NOT NULL,
                status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage(day TEXT NOT NULL, scope TEXT NOT NULL,
                count INTEGER NOT NULL, PRIMARY KEY(day,scope));
            """)
            db.execute("UPDATE jobs SET status='interrupted',error='Service restarted; request analysis again.',updated=? WHERE status IN ('running','queued')", (time.time(),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, json.dumps(value)))

    def notice(self, env, cid, kind, title, body, identity, occurrences=1):
        now = time.time()
        nid = fingerprint([env, cid, kind, identity])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT body FROM notices WHERE id=?", (nid,)).fetchone()
            encoded = json.dumps(body, sort_keys=True)
            if not old:
                db.execute("INSERT INTO notices VALUES(?,?,?,?,?,?,?,?,?)",
                           (nid, env, cid, kind, title, encoded, now, now, occurrences))
            elif old[0] != encoded:
                db.execute("UPDATE notices SET body=?,updated=?,count=count+? WHERE id=?",
                           (encoded, now, occurrences, nid))
        return nid

    def notices(self, env, uid, allowed_ids, admin=False):
        with self.connect() as db:
            rows = db.execute("""SELECT n.*,COALESCE(r.seen,0) AS seen FROM notices n
                LEFT JOIN reads r ON r.notice=n.id AND r.uid=?
                WHERE n.env=? AND n.kind IN ('rule','lifecycle') ORDER BY n.updated DESC LIMIT 500""", (uid, env)).fetchall()
        return [{**dict(row), "body": json.loads(row["body"]), "unread": row["seen"] < row["updated"]}
                for row in rows if row["cid"] in allowed_ids or admin]

    def mark_read(self, uid, notice_ids):
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO reads VALUES(?,?,?)",
                           [(uid, nid, time.time()) for nid in notice_ids])

    def start_analysis(self, env, cid, payload, uid, user_limit, global_limit):
        identity = secrets.token_hex(16)
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        budgets = [("global_ai", global_limit, "Daily AI request limit reached; resets at 00:00 UTC."),
                   (f"user:{uid}", user_limit, "Your daily analysis request limit has been reached.")]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for scope, limit, message in budgets:
                row = db.execute("SELECT count FROM usage WHERE day=? AND scope=?", (day, scope)).fetchone()
                if row and row[0] >= limit:
                    raise ValueError(message)
            for scope, _, _ in budgets:
                db.execute("INSERT INTO usage VALUES(?,?,1) ON CONFLICT(day,scope) DO UPDATE SET count=count+1", (day, scope))
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (identity, env, cid, "analysis", json.dumps(payload), "running", None, None, now, now))
        return identity

    def job(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
        if not row:
            return None
        return {**dict(row), "payload": json.loads(row["payload"]),
                "result": json.loads(row["result"]) if row["result"] else None}

    def finish(self, identity, status, result=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,result=?,error=?,updated=? WHERE id=?",
                       (status, json.dumps(result) if result is not None else None, error, time.time(), identity))

    def prune(self, days):
        cutoff = time.time() - days * 86400
        with self.connect() as db:
            db.execute("DELETE FROM reads WHERE notice IN (SELECT id FROM notices WHERE updated<?)", (cutoff,))
            db.execute("DELETE FROM notices WHERE updated<?", (cutoff,))
            db.execute("DELETE FROM jobs WHERE updated<? AND status NOT IN ('queued','running')", (cutoff,))
            db.execute("DELETE FROM telegram_alerts WHERE created<? AND status != 'pending'", (cutoff,))
            db.execute("DELETE FROM usage WHERE day<?", (time.strftime("%Y-%m-%d", time.gmtime(cutoff)),))

