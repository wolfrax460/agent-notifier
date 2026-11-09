"""SQLite store. One connection + lock: plenty for a small service, tiny RAM footprint."""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time

from .security import PAT_PREFIX, new_secret, sha

SESSION_TTL = 30 * 86400
PRE_AUTH_TTL = 600

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, tg_chat_id TEXT UNIQUE NOT NULL, tg_name TEXT,
  ntfy_topic TEXT NOT NULL, ntfy_enabled INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  login_code TEXT UNIQUE, ip TEXT, ua TEXT, created REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tokens(
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  hash TEXT UNIQUE NOT NULL, label TEXT, created REAL NOT NULL, last_used REAL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS oauth_clients(client_id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_pending(id TEXT PRIMARY KEY, client_id TEXT NOT NULL, params TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_codes(code_hash TEXT PRIMARY KEY, data TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_tokens(
  hash TEXT PRIMARY KEY, kind TEXT NOT NULL, client_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  scopes TEXT NOT NULL, expires REAL, pair_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text TEXT NOT NULL, ts REAL NOT NULL, delivered INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS inbox_user ON inbox(user_id, delivered, ts);
CREATE TABLE IF NOT EXISTS admin_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, admin_id TEXT NOT NULL, action TEXT NOT NULL, target TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS usage(
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, day TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, day));
"""


class DB:
    def __init__(self, path: str):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.executescript(SCHEMA)
            cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(users)").fetchall()]
            if "suspended" not in cols:
                self.conn.execute("ALTER TABLE users ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    # -- primitives --------------------------------------------------------
    def all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def run(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            return self.conn.execute(sql, args).rowcount

    # -- users -------------------------------------------------------------
    def user_by_id(self, uid: str):
        return self.one("SELECT * FROM users WHERE id=?", (uid,))

    def user_by_chat(self, chat_id: str):
        return self.one("SELECT * FROM users WHERE tg_chat_id=?", (str(chat_id),))

    def get_or_create_user(self, chat_id: str, name: str):
        user = self.user_by_chat(chat_id)
        if user:
            if name and name != user["tg_name"]:
                self.run("UPDATE users SET tg_name=? WHERE id=?", (name[:80], user["id"]))
            return self.user_by_chat(chat_id)
        uid = "u_" + secrets.token_hex(8)
        self.run(
            "INSERT INTO users(id,tg_chat_id,tg_name,ntfy_topic,created) VALUES(?,?,?,?,?)",
            (uid, str(chat_id), name[:80], "cn-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y"), time.time()),
        )
        return self.user_by_id(uid)

    @staticmethod
    def active(user):
        """The user row if the account is usable, else None (suspended accounts are locked out everywhere)."""
        return user if user and not user["suspended"] else None

    def delete_user(self, uid: str) -> None:
        self.run("DELETE FROM users WHERE id=?", (uid,))

    def set_ntfy(self, uid: str, enabled: bool) -> None:
        self.run("UPDATE users SET ntfy_enabled=? WHERE id=?", (1 if enabled else 0, uid))

    # -- browser sessions / telegram login ----------------------------------
    def new_session(self, ip: str, ua: str) -> tuple[str, str]:
        sid, code = new_secret(32), "L" + secrets.token_hex(6)
        now = time.time()
        self.run(
            "INSERT INTO sessions(id,login_code,ip,ua,created,expires) VALUES(?,?,?,?,?,?)",
            (sha(sid), code, ip[:64], ua[:200], now, now + PRE_AUTH_TTL),
        )
        return sid, code

    def get_session(self, sid: str):
        return self.one("SELECT * FROM sessions WHERE id=? AND expires>?", (sha(sid), time.time()))

    def session_for_code(self, code: str):
        return self.one("SELECT * FROM sessions WHERE login_code=? AND user_id IS NULL AND expires>?", (code, time.time()))

    def bind_session(self, code: str, user_id: str) -> bool:
        now = time.time()
        return self.run(
            "UPDATE sessions SET user_id=?, login_code=NULL, expires=? WHERE login_code=? AND user_id IS NULL AND expires>?",
            (user_id, now + SESSION_TTL, code, now),
        ) == 1

    def kill_code(self, code: str) -> None:
        self.run("DELETE FROM sessions WHERE login_code=? AND user_id IS NULL", (code,))

    def delete_session(self, sid: str) -> None:
        self.run("DELETE FROM sessions WHERE id=?", (sha(sid),))

    # -- personal access tokens ---------------------------------------------
    def create_pat(self, user_id: str, label: str) -> str | None:
        active = self.one("SELECT COUNT(*) c FROM tokens WHERE user_id=? AND revoked=0", (user_id,))["c"]
        if active >= 10:
            return None
        token = PAT_PREFIX + new_secret(32)
        self.run(
            "INSERT INTO tokens(id,user_id,hash,label,created) VALUES(?,?,?,?,?)",
            ("t_" + secrets.token_hex(6), user_id, sha(token), (label or "token")[:40], time.time()),
        )
        return token

    def list_pats(self, user_id: str):
        return self.all("SELECT id,label,created,last_used FROM tokens WHERE user_id=? AND revoked=0 ORDER BY created", (user_id,))

    def revoke_pat(self, user_id: str, token_id: str) -> None:
        self.run("UPDATE tokens SET revoked=1 WHERE id=? AND user_id=?", (token_id, user_id))

    def pat_user(self, token: str) -> str | None:
        row = self.one("SELECT id,user_id,last_used FROM tokens WHERE hash=? AND revoked=0", (sha(token),))
        if not row:
            return None
        now = time.time()
        if not row["last_used"] or now - row["last_used"] > 300:
            self.run("UPDATE tokens SET last_used=? WHERE id=?", (now, row["id"]))
        return row["user_id"]

    # -- inbox (replies from the user) ----------------------------------------
    def add_inbox(self, user_id: str, text: str) -> None:
        self.run("INSERT INTO inbox(user_id,text,ts) VALUES(?,?,?)", (user_id, text[:2000], time.time()))
        self.run(
            "DELETE FROM inbox WHERE user_id=? AND id NOT IN (SELECT id FROM inbox WHERE user_id=? ORDER BY id DESC LIMIT 50)",
            (user_id, user_id),
        )

    def pop_inbox(self, user_id: str, since: float | None = None, limit: int = 20) -> list[dict]:
        sql = "SELECT id,text,ts FROM inbox WHERE user_id=? AND delivered=0"
        args: list = [user_id]
        if since is not None:
            sql += " AND ts>=?"
            args.append(since)
        rows = self.all(sql + " ORDER BY id LIMIT ?", tuple(args + [limit]))
        for r in rows:
            self.run("UPDATE inbox SET delivered=1 WHERE id=?", (r["id"],))
        return [{"text": r["text"], "ts": r["ts"]} for r in rows]

    # -- usage -----------------------------------------------------------------
    def usage_today(self, user_id: str) -> int:
        row = self.one("SELECT n FROM usage WHERE user_id=? AND day=?", (user_id, time.strftime("%Y-%m-%d", time.gmtime())))
        return row["n"] if row else 0

    def bump_usage(self, user_id: str) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if self.run("UPDATE usage SET n=n+1 WHERE user_id=? AND day=?", (user_id, day)) == 0:
            self.run("INSERT INTO usage(user_id,day,n) VALUES(?,?,1)", (user_id, day))

    def usage_series(self, user_id: str, days: int = 14) -> list[tuple[str, int]]:
        now = time.time()
        rows = {r["day"]: r["n"] for r in self.all("SELECT day,n FROM usage WHERE user_id=?", (user_id,))}
        out = []
        for i in range(days - 1, -1, -1):
            t = time.gmtime(now - i * 86400)
            out.append((time.strftime("%m-%d", t), rows.get(time.strftime("%Y-%m-%d", t), 0)))
        return out

    def inbox_pending(self, user_id: str) -> int:
        return self.one("SELECT COUNT(*) c FROM inbox WHERE user_id=? AND delivered=0", (user_id,))["c"]

    def oauth_apps(self, user_id: str) -> int:
        return self.one("SELECT COUNT(DISTINCT client_id) c FROM oauth_tokens WHERE user_id=?", (user_id,))["c"]

    # -- admin (read-mostly; never touches message contents) -----------------------
    @staticmethod
    def _day(offset: int = 0) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(time.time() - offset * 86400))

    def admin_stats(self, days: int = 14) -> dict:
        today, d7, d14 = self._day(0), self._day(6), self._day(days - 1)
        one = lambda sql, a=(): self.one(sql, a)[0]
        now = time.time()
        sent = {r["day"]: r["n"] for r in self.all("SELECT day,SUM(n) n FROM usage WHERE day>=? GROUP BY day", (d14,))}
        joined = {r["d"]: r["n"] for r in self.all(
            "SELECT strftime('%Y-%m-%d',created,'unixepoch') d,COUNT(*) n FROM users WHERE created>=? GROUP BY d", (now - days * 86400,))}
        sent_series, new_series = [], []
        for i in range(days - 1, -1, -1):
            day = self._day(i)
            sent_series.append((day[5:], sent.get(day, 0)))
            new_series.append((day[5:], joined.get(day, 0)))
        return {
            "users": one("SELECT COUNT(*) FROM users"),
            "new7": one("SELECT COUNT(*) FROM users WHERE created>=?", (now - 7 * 86400,)),
            "suspended": one("SELECT COUNT(*) FROM users WHERE suspended=1"),
            "active_today": one("SELECT COUNT(DISTINCT user_id) FROM usage WHERE day=? AND n>0", (today,)),
            "active7": one("SELECT COUNT(DISTINCT user_id) FROM usage WHERE day>=? AND n>0", (d7,)),
            "sent_today": one("SELECT COALESCE(SUM(n),0) FROM usage WHERE day=?", (today,)),
            "sent14": sum(v for _, v in sent_series),
            "tokens": one("SELECT COUNT(*) FROM tokens WHERE revoked=0"),
            "oauth_apps": one("SELECT COUNT(*) FROM (SELECT DISTINCT user_id,client_id FROM oauth_tokens)"),
            "ntfy": one("SELECT COUNT(*) FROM users WHERE ntfy_enabled=1"),
            "pending": one("SELECT COUNT(*) FROM inbox WHERE delivered=0"),
            "sent_series": sent_series,
            "new_series": new_series,
            "top_today": [dict(r) for r in self.all(
                "SELECT u.id,u.tg_name,u.suspended,x.n FROM usage x JOIN users u ON u.id=x.user_id WHERE x.day=? AND x.n>0 ORDER BY x.n DESC LIMIT 5", (today,))],
            "recent": [dict(r) for r in self.all("SELECT id,tg_name,created,suspended FROM users ORDER BY created DESC LIMIT 6")],
        }

    def admin_users(self, q: str = "", limit: int = 25, offset: int = 0, status: str = "all") -> tuple[list[dict], int]:
        d14, today = self._day(13), self._day(0)
        where, args = [], []
        if q:
            like = "%" + q.replace("%", "").replace("_", "")[:60] + "%"
            where.append("(u.tg_name LIKE ? OR u.tg_chat_id LIKE ? OR u.id LIKE ?)")
            args += [like, like, like]
        if status == "suspended":
            where.append("u.suspended=1")
        elif status == "active":
            where.append("u.suspended=0")
        w = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.one(f"SELECT COUNT(*) FROM users u{w}", tuple(args))[0]
        rows = self.all(
            f"""SELECT u.id,u.tg_chat_id,u.tg_name,u.created,u.ntfy_enabled,u.suspended,
              (SELECT COALESCE(SUM(n),0) FROM usage WHERE user_id=u.id AND day>=?) m14,
              (SELECT COALESCE(SUM(n),0) FROM usage WHERE user_id=u.id AND day=?) m_today,
              (SELECT MAX(day) FROM usage WHERE user_id=u.id AND n>0) last_day,
              (SELECT COUNT(*) FROM tokens WHERE user_id=u.id AND revoked=0) toks
            FROM users u{w} ORDER BY u.created DESC LIMIT ? OFFSET ?""",
            tuple([d14, today] + args + [limit, offset]),
        )
        return [dict(r) for r in rows], total

    def admin_user(self, uid: str):
        return self.user_by_id(uid)

    def admin_tokens(self, uid: str) -> list[dict]:
        return [dict(r) for r in self.all("SELECT id,label,created,last_used FROM tokens WHERE user_id=? AND revoked=0 ORDER BY created", (uid,))]

    def set_suspended(self, uid: str, value: bool) -> None:
        self.run("UPDATE users SET suspended=? WHERE id=?", (1 if value else 0, uid))
        if value:
            self.kill_user_sessions(uid)

    def kill_user_sessions(self, uid: str) -> None:
        self.run("DELETE FROM sessions WHERE user_id=?", (uid,))

    def revoke_everything(self, uid: str) -> None:
        self.run("UPDATE tokens SET revoked=1 WHERE user_id=?", (uid,))
        self.run("DELETE FROM oauth_tokens WHERE user_id=?", (uid,))
        self.kill_user_sessions(uid)

    def broadcast_targets(self) -> list[dict]:
        return [dict(r) for r in self.all("SELECT id,tg_chat_id FROM users WHERE suspended=0")]

    def audit(self, admin_id: str, action: str, target: str = "", detail: str = "") -> None:
        self.run("INSERT INTO admin_log(ts,admin_id,action,target,detail) VALUES(?,?,?,?,?)", (time.time(), admin_id, action, target[:60], detail[:200]))
        self.run("DELETE FROM admin_log WHERE id NOT IN (SELECT id FROM admin_log ORDER BY id DESC LIMIT 1000)")

    def audit_list(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.all(
            "SELECT l.ts,l.action,l.target,l.detail,u.tg_name admin FROM admin_log l LEFT JOIN users u ON u.id=l.admin_id ORDER BY l.id DESC LIMIT ?", (limit,))]

    def db_size(self, path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    # -- housekeeping ------------------------------------------------------------
    def purge(self) -> None:
        now = time.time()
        self.run("DELETE FROM sessions WHERE expires<?", (now,))
        self.run("DELETE FROM oauth_codes WHERE expires<?", (now,))
        self.run("DELETE FROM oauth_pending WHERE created<?", (now - 900,))
        self.run("DELETE FROM oauth_tokens WHERE expires IS NOT NULL AND expires<?", (now,))
        self.run("DELETE FROM inbox WHERE ts<?", (now - 7 * 86400,))
        self.run("DELETE FROM usage WHERE day<?", (time.strftime("%Y-%m-%d", time.gmtime(now - 40 * 86400)),))
