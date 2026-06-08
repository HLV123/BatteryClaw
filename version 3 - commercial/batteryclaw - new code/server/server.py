"""
BatteryClaw Server
- Quan ly API key + email user
- Admin co the xoa key, xoa user
- Key chi dung duoc 1 lan tren 1 may (khoa machine_id sau khi kich hoat)
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from contextlib import asynccontextmanager
import sqlite3, secrets, string, datetime, os, hashlib, logging, time

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [server] %(levelname)s %(message)s")
log = logging.getLogger("batteryclaw.server")


# [NEW-01] Lifespan: chay TRUOC khi nhan request, voi MOI cach deploy
#  (python server.py, uvicorn server:app, gunicorn -k uvicorn...).
#  Truoc day require_strong_token()+init() nam trong __main__ nen bi bo qua
#  khi deploy bang `uvicorn server:app` -> token yeu van chay + DB chua init.
@asynccontextmanager
async def lifespan(app: FastAPI):
    require_strong_token()   # chan token yeu/mac dinh
    init()                   # tao bang DB
    log.info("BatteryClaw Server san sang (lifespan startup).")
    yield
    # (cleanup neu can khi tat server)

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

DB   = "batteryclaw.db"
KEY_DAYS    = 4

# [BUG-02] Admin token: KHONG dung mac dinh cong khai.
#  - Lay tu bien moi truong BC_ADMIN_TOKEN.
#  - Neu chua dat: sinh token ngau nhien CHO PHIEN NAY (in ra log mot lan),
#    tot hon la de "admin123". Khi deploy that nen dat bien moi truong.
#  - require_strong_token() (goi luc khoi dong that) se chan neu yeu/mac dinh.
_WEAK_TOKENS = {"", "admin123", "admin", "password", "123456", "changeme"}
ADMIN_TOKEN = os.environ.get("BC_ADMIN_TOKEN", "").strip()
_TOKEN_AUTOGEN = False
if not ADMIN_TOKEN:
    ADMIN_TOKEN = secrets.token_urlsafe(24)
    _TOKEN_AUTOGEN = True


def require_strong_token():
    """Goi khi khoi dong server that. Chan token yeu/mac dinh."""
    env = os.environ.get("BC_ADMIN_TOKEN", "").strip()
    if env in _WEAK_TOKENS and not _TOKEN_AUTOGEN:
        raise RuntimeError(
            "BC_ADMIN_TOKEN qua yeu hoac la mac dinh. "
            "Dat mat khau manh: export BC_ADMIN_TOKEN='<chuoi ngau nhien dai>'")
    if _TOKEN_AUTOGEN:
        log.warning("BC_ADMIN_TOKEN chua dat -> dung token NGAU NHIEN phien nay:")
        log.warning("  %s", ADMIN_TOKEN)
        log.warning("Dat bien moi truong BC_ADMIN_TOKEN de co token co dinh.")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


# [BUG-03] Rate limiting nhe theo IP (in-memory, khong them thu vien).
#  Chong brute-force key (/api/activate, /api/verify) va spam dataset upload.
#  Cua so truot don gian: toi da N request / WINDOW giay moi IP moi nhom.
_RATE_BUCKETS: dict = {}
_RATE_GC_COUNTER = 0          # [NEW-02] dem de don bucket dinh ky
_RATE_RULES = {
    "auth":    (20, 60),     # 20 req / 60s cho activate+verify
    "dataset": (10, 60),     # 10 upload / 60s
}

# [REMAIN-01] Khi deploy sau nginx (khuyen nghi), request.client.host luon la
#  127.0.0.1 -> moi IP that gop chung 1 bucket -> rate limit vo nghia.
#  Bat BEHIND_PROXY=1 de doc IP that tu header X-Forwarded-For do proxy set.
#  CHI bat khi server THUC SU nam sau proxy minh kiem soat (tranh client gia mao
#  header de vuot rate limit).
BEHIND_PROXY = os.environ.get("BEHIND_PROXY", "0") == "1"

def _client_ip(request: Request) -> str:
    if BEHIND_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        ip = fwd.split(",")[0].strip()
        if ip:
            return ip
    return request.client.host if request.client else "unknown"

def rate_limit(request: Request, group: str):
    limit, window = _RATE_RULES.get(group, (60, 60))
    ip = _client_ip(request)
    now = time.time()
    key = (group, ip)
    hits = [t for t in _RATE_BUCKETS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        log.warning("Rate limit: IP %s nhom %s vuot %d/%ds", ip, group, limit, window)
        raise HTTPException(status_code=429, detail="Qua nhieu request, thu lai sau.")
    hits.append(now)
    _RATE_BUCKETS[key] = hits
    # [NEW-02] don dinh ky cac bucket da het han hoan toan de dict khong phinh
    #  theo so IP da tung ket noi. Chay nhe (moi ~200 request mot lan).
    global _RATE_GC_COUNTER
    _RATE_GC_COUNTER += 1
    if _RATE_GC_COUNTER >= 200:
        _RATE_GC_COUNTER = 0
        for k in list(_RATE_BUCKETS.keys()):
            g = k[0]
            _, w = _RATE_RULES.get(g, (60, 60))
            if all(now - t >= w for t in _RATE_BUCKETS[k]):
                _RATE_BUCKETS.pop(k, None)

def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS keys (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        key         TEXT UNIQUE NOT NULL,
        email       TEXT DEFAULT '',
        machine_id  TEXT DEFAULT '',
        activated   INTEGER DEFAULT 0,
        active      INTEGER DEFAULT 1,
        created_at  TEXT NOT NULL,
        expires_at  TEXT NOT NULL,
        days        INTEGER DEFAULT 4,
        note        TEXT DEFAULT '',
        price       INTEGER DEFAULT 0,
        buyer_zalo  TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        key        TEXT,
        email      TEXT,
        machine_id TEXT,
        ip         TEXT,
        action     TEXT,
        ts         TEXT
    );
    -- [Phase 2 - 2.4] Multi-Device Dataset: dữ liệu ẩn danh từ nhiều máy
    CREATE TABLE IF NOT EXISTS dataset (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        device_hash  TEXT NOT NULL,   -- hash ẩn danh của máy (KHÔNG phải machine_id thật)
        device_class TEXT DEFAULT '', -- vd "i7-11800H+RTX3050" (gom nhóm máy giống nhau)
        n_rows       INTEGER DEFAULT 0,
        payload      TEXT NOT NULL,   -- JSON các transition (đã ẩn danh)
        ts           TEXT NOT NULL
    );
    """)
    c.commit(); c.close()

def now(): return datetime.datetime.utcnow().isoformat()
def expires(days): return (datetime.datetime.utcnow()+datetime.timedelta(days=days)).isoformat()
def gen_key():
    ch = string.ascii_uppercase + string.digits
    p  = [''.join(secrets.choice(ch) for _ in range(4)) for _ in range(3)]
    return f"BC-{'-'.join(p)}"

def check_admin(req: Request):
    if req.headers.get("X-Admin-Token","") != ADMIN_TOKEN:
        raise HTTPException(403,"Forbidden")

# ── Client API ────────────────────────────────────────────────────────────────

class ActivateReq(BaseModel):
    key        : str
    email      : str
    machine_id : str

class VerifyReq(BaseModel):
    key        : str
    machine_id : str

@app.post("/api/activate")
async def activate(req: ActivateReq, request: Request):
    """
    Kich hoat key lan dau: gan email + machine_id vao key
    Chi goi 1 lan duy nhat - sau do khoa
    """
    rate_limit(request, "auth")   # [BUG-03] chong brute-force
    c   = db()
    row = c.execute("SELECT * FROM keys WHERE key=?", (req.key,)).fetchone()
    ip  = request.client.host

    if not row:
        c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'ACTIVATE_NOT_FOUND',?)",
                  (req.key,req.email,req.machine_id,ip,now()))
        c.commit(); c.close()
        return {"ok": False, "msg": "Key khong ton tai"}

    if not row["active"]:
        c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'ACTIVATE_REVOKED',?)",
                  (req.key,req.email,req.machine_id,ip,now()))
        c.commit(); c.close()
        return {"ok": False, "msg": "Key da bi thu hoi"}

    exp = datetime.datetime.fromisoformat(row["expires_at"])
    if datetime.datetime.utcnow() > exp:
        c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'ACTIVATE_EXPIRED',?)",
                  (req.key,req.email,req.machine_id,ip,now()))
        c.commit(); c.close()
        return {"ok": False, "msg": "Key da het han"}

    if row["activated"]:
        # Da kich hoat roi - kiem tra xem co dung may do khong
        if row["machine_id"] != req.machine_id:
            c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'ACTIVATE_WRONG_MACHINE',?)",
                      (req.key,req.email,req.machine_id,ip,now()))
            c.commit(); c.close()
            return {"ok": False,
                    "msg": "Key nay da duoc kich hoat tren may khac.\n"
                           "Moi may chi dung 1 key. Lien he admin de duoc ho tro."}
        # Dung may do - cho phep (re-install)
    else:
        # Lan dau kich hoat - khoa vao may nay + email nay
        c.execute("""UPDATE keys SET activated=1, machine_id=?, email=?
                     WHERE key=?""", (req.machine_id, req.email, req.key))

    days_left = (exp - datetime.datetime.utcnow()).days
    c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'ACTIVATE_OK',?)",
              (req.key,req.email,req.machine_id,ip,now()))
    c.commit(); c.close()
    return {"ok": True, "days_left": days_left, "expires_at": row["expires_at"]}

@app.post("/api/verify")
async def verify(req: VerifyReq, request: Request):
    """Kiem tra key moi lan khoi dong (online check)"""
    rate_limit(request, "auth")   # [BUG-03] chong brute-force
    c   = db()
    row = c.execute("SELECT * FROM keys WHERE key=?", (req.key,)).fetchone()
    ip  = request.client.host

    if not row or not row["active"]:
        c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'VERIFY_FAIL',?)",
                  (req.key,"",req.machine_id,ip,now()))
        c.commit(); c.close()
        return {"ok": False, "msg": "Key khong hop le hoac da bi thu hoi"}

    exp = datetime.datetime.fromisoformat(row["expires_at"])
    if datetime.datetime.utcnow() > exp:
        c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'VERIFY_EXPIRED',?)",
                  (req.key,"",req.machine_id,ip,now()))
        c.commit(); c.close()
        return {"ok": False, "msg": "Key da het han"}

    if row["machine_id"] and row["machine_id"] != req.machine_id:
        c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'VERIFY_WRONG_MACHINE',?)",
                  (req.key,"",req.machine_id,ip,now()))
        c.commit(); c.close()
        return {"ok": False, "msg": "Key nay khong thuoc may nay"}

    days_left = max(0, (exp - datetime.datetime.utcnow()).days)
    c.execute("INSERT INTO log VALUES(NULL,?,?,?,?,'VERIFY_OK',?)",
              (req.key,row["email"],req.machine_id,ip,now()))
    c.commit(); c.close()
    return {"ok": True, "days_left": days_left, "email": row["email"]}

# ── Admin API ─────────────────────────────────────────────────────────────────

@app.post("/admin/key/create")
async def create_key(request: Request,
                     days: int=4, price: int=0,
                     note: str="", buyer_zalo: str=""):
    check_admin(request)
    key = gen_key()
    c   = db()
    c.execute("""INSERT INTO keys
                 (key,created_at,expires_at,days,price,note,buyer_zalo)
                 VALUES(?,?,?,?,?,?,?)""",
              (key, now(), expires(days), days, price, note, buyer_zalo))
    c.commit(); c.close()
    return {"key": key, "days": days}

@app.post("/admin/key/revoke/{key}")
async def revoke_key(key: str, request: Request):
    check_admin(request)
    c = db()
    c.execute("UPDATE keys SET active=0 WHERE key=?", (key,))
    c.commit(); c.close()
    return {"ok": True}

@app.delete("/admin/key/{key}")
async def delete_key(key: str, request: Request):
    check_admin(request)
    c = db()
    c.execute("DELETE FROM keys WHERE key=?", (key,))
    c.commit(); c.close()
    return {"ok": True}

@app.post("/admin/key/extend/{key}")
async def extend_key(key: str, days: int, request: Request):
    check_admin(request)
    c   = db()
    row = c.execute("SELECT expires_at FROM keys WHERE key=?", (key,)).fetchone()
    if not row: raise HTTPException(404)
    old = datetime.datetime.fromisoformat(row["expires_at"])
    new = max(old, datetime.datetime.utcnow()) + datetime.timedelta(days=days)
    c.execute("UPDATE keys SET expires_at=? WHERE key=?", (new.isoformat(), key))
    c.commit(); c.close()
    return {"ok": True, "new_expires": new.isoformat()}

@app.get("/admin/keys")
async def list_keys(request: Request):
    check_admin(request)
    c    = db()
    rows = c.execute("SELECT * FROM keys ORDER BY created_at DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]

@app.get("/admin/logs")
async def list_logs(request: Request, limit: int=100):
    check_admin(request)
    c    = db()
    rows = c.execute("SELECT * FROM log ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

@app.get("/admin/stats")
async def stats(request: Request):
    check_admin(request)
    c = db()
    total   = c.execute("SELECT COUNT(*) FROM keys").fetchone()[0]
    active  = c.execute("SELECT COUNT(*) FROM keys WHERE active=1 AND expires_at>?",
                        (now(),)).fetchone()[0]
    expired = c.execute("SELECT COUNT(*) FROM keys WHERE expires_at<=?",
                        (now(),)).fetchone()[0]
    revenue = c.execute("SELECT COALESCE(SUM(price),0) FROM keys").fetchone()[0]
    c.close()
    return {"total":total,"active":active,"expired":expired,"revenue":revenue}

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/health")
async def health(): return {"ok": True, "time": now()}

# ── [Phase 2 - 2.4] Multi-Device Dataset ───────────────────────────────────
#  Client gửi dữ liệu ẩn danh (state/action/reward), KHÔNG kèm email/khóa.
#  Server gom lại thành dataset chung để train model base tốt hơn cho mọi máy.

class DatasetUpload(BaseModel):
    device_hash  : str           # hash ẩn danh (client tự băm machine_id, không gửi gốc)
    device_class : str = ""      # vd "i7-11800H+RTX3050"
    rows         : list          # danh sách transition (mỗi cái là dict theo schema)

@app.post("/api/dataset/upload")
async def dataset_upload(req: DatasetUpload, request: Request):
    import json as _json
    rate_limit(request, "dataset")   # [BUG-03] chong spam lam phinh DB
    # An toàn: chỉ nhận tối đa N dòng mỗi lần để tránh payload khổng lồ
    rows = req.rows[:5000]
    # Lọc ẩn danh: loại bỏ mọi trường có thể định danh (fg_app -> chỉ giữ is_game)
    clean = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rr = dict(r)
        rr.pop("fg_app", None)        # tên app có thể lộ thói quen -> bỏ
        rr.pop("session_id", None)
        clean.append(rr)
    c = db()
    c.execute(
        "INSERT INTO dataset (device_hash, device_class, n_rows, payload, ts) "
        "VALUES (?,?,?,?,?)",
        (req.device_hash[:64], req.device_class[:64], len(clean),
         _json.dumps(clean, ensure_ascii=False), now()))
    c.commit(); c.close()
    return {"ok": True, "received": len(clean)}

@app.get("/admin/dataset/stats")
async def dataset_stats(request: Request):
    check_admin(request)
    c = db()
    total_rows = c.execute("SELECT COALESCE(SUM(n_rows),0) FROM dataset").fetchone()[0]
    devices    = c.execute("SELECT COUNT(DISTINCT device_hash) FROM dataset").fetchone()[0]
    classes    = c.execute(
        "SELECT device_class, COUNT(*), COALESCE(SUM(n_rows),0) "
        "FROM dataset GROUP BY device_class").fetchall()
    c.close()
    return {"ok": True, "total_rows": total_rows, "devices": devices,
            "by_class": [{"class": r[0], "uploads": r[1], "rows": r[2]}
                         for r in classes]}

@app.get("/admin/dataset/export")
async def dataset_export(request: Request, device_class: str = ""):
    """Gộp toàn bộ transition (tùy chọn lọc theo device_class) -> trả JSON.
    Admin tải về để train model base (Phase 2 mục 2.4)."""
    check_admin(request)
    import json as _json
    c = db()
    if device_class:
        rows = c.execute("SELECT payload FROM dataset WHERE device_class=?",
                         (device_class,)).fetchall()
    else:
        rows = c.execute("SELECT payload FROM dataset").fetchall()
    c.close()
    merged = []
    for (payload,) in rows:
        try:
            merged.extend(_json.loads(payload))
        except Exception:
            continue
    return {"ok": True, "n_rows": len(merged), "rows": merged}

if __name__ == "__main__":
    import uvicorn
    # require_strong_token() + init() da chay trong lifespan -> khong goi lai o day.
    log.info("Khoi dong qua: python server.py")
    log.info("Admin: http://localhost:8000/admin")
    uvicorn.run(app, host="0.0.0.0", port=8000)
