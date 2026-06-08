"""
BatteryClaw — dashboard/server.py  (PHASE 6 — phục vụ dashboard web)

Server localhost CỰC NHẸ (http.server thuần, không thêm dependency) để hiển thị
dashboard. Đọc các store Phase 6 và trả JSON cho index.html.

  GET /                 -> dashboard HTML (static/index.html)
  GET /static/*         -> file tĩnh (chart.min.js nhúng offline, css...)
  GET /api/dashboard    -> JSON tổng hợp cho dashboard

Chạy:
  python dashboard/server.py --port 8777 --state <thư mục state>
Rồi mở http://127.0.0.1:8777

Triết lý: chỉ phục vụ HIỂN THỊ. Dữ liệu do engine/brain ghi vào state dir.
Chỉ bind 127.0.0.1 (không lộ ra mạng).
"""

import argparse
import json
import os
import sys
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "commercial"))

from stats_store import StatsStore
from profiles import ProfileManager
from tiers import TierGate, TIER_LABELS

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    STATIC_DIR = os.path.join(sys._MEIPASS, "dashboard", "static")
else:
    STATIC_DIR = os.path.join(_HERE, "static")


class DashboardData:
    """Gom dữ liệu từ các store để trả cho dashboard."""
    def __init__(self, state_dir):
        self.state_dir = state_dir
        self.stats   = StatsStore(os.path.join(state_dir, "stats.json"))
        self.profile = ProfileManager(os.path.join(state_dir, "profile.json"))
        # tier + battery health đọc từ file nhỏ nếu engine có ghi
        self.tier = self._read_json("tier.json", {"tier": "free"})
        self.health = self._read_json("battery_health.json", {
            "design_mwh": 52007, "full_mwh": 33026,
            "health_pct": 63.5, "health_in_1y": 50.1, "warning": False,
        })

    def _read_json(self, name, default):
        p = os.path.join(self.state_dir, name)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def build(self):
        # [DESIGN-08] chi reload stats khi file THUC SU doi (so mtime),
        #  thay vi tao lai object moi 15s. Cac file khac (tier/health) cung vay.
        stats_path = os.path.join(self.state_dir, "stats.json")
        try:
            mtime = os.path.getmtime(stats_path)
        except OSError:
            mtime = 0
        if mtime != getattr(self, "_stats_mtime", None):
            self.stats = StatsStore(stats_path)
            self._stats_mtime = mtime
        # tier + battery health cung doc lai khi doi (nhe, it thay doi)
        self.tier = self._read_json("tier.json", self.tier)
        self.health = self._read_json("battery_health.json", self.health)

        t, y, diff = self.stats.today_vs_yesterday()
        hourly = self.stats.hourly_discharge_today()
        avg = [v for v in hourly if v > 0]
        avg_mw = sum(avg) / len(avg) if avg else 0
        rem = self.stats.predict_remaining(self.health.get("full_mwh", 33026))

        gate = TierGate(self.tier.get("tier", "free"))
        prof = self.profile.get()

        # [4.3] Bao cao tom tat dang chu cho nguoi dung doc nhanh.
        saved_30d = self.stats.total_saved_wh()       # Wh tiet kiem 30 ngay
        full_wh   = self.health.get("full_mwh", 33026) / 1000.0
        # uoc so "lan sac" tiet kiem duoc = tong Wh tiet kiem / dung luong pin
        cycles_saved = round(saved_30d / full_wh, 1) if full_wh else 0
        report_text = (
            f"30 ngay qua tiet kiem ~{saved_30d:.1f} Wh "
            f"(~{cycles_saved} lan sac day pin). "
            f"Pin hien o {self.health.get('health_pct', 0)}% suc khoe."
        )

        return {
            "today_sec": t, "diff_sec": diff,
            "remaining_hours": round(rem, 2) if rem else None,
            "avg_discharge_mw": round(avg_mw),
            "saved_total_wh": self.stats.total_saved_wh(),
            "saved_30d_wh": round(saved_30d, 1),
            "cycles_saved": cycles_saved,
            "report_text": report_text,
            "history": self.stats.last_n_days_saved(30),
            "hourly_discharge": hourly,
            "design_mwh": self.health.get("design_mwh", 52007),
            "full_mwh": self.health.get("full_mwh", 33026),
            "health_pct": self.health.get("health_pct", 0),
            "health_in_1y": self.health.get("health_in_1y", 0),
            "health_warning": self.health.get("warning", False),
            "profile": prof.get("label", "—"),
            "tier": TIER_LABELS.get(gate.tier, gate.tier),
        }


def make_handler(data: DashboardData):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # tắt log ồn ào
            pass

        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._file(os.path.join(STATIC_DIR, "index.html"), "text/html")
            if self.path == "/api/dashboard":
                payload = json.dumps(data.build(), ensure_ascii=False).encode("utf-8")
                return self._send(200, payload)
            if self.path.startswith("/static/"):
                rel = self.path[len("/static/"):].split("?")[0]
                safe = os.path.normpath(rel).lstrip("/\\")
                fp = os.path.join(STATIC_DIR, safe)
                if os.path.isfile(fp) and fp.startswith(STATIC_DIR):
                    ctype = ("application/javascript" if fp.endswith(".js")
                             else "text/html" if fp.endswith(".html")
                             else "text/plain")
                    return self._file(fp, ctype)
            self._send(404, b'{"error":"not found"}')

        def _file(self, path, ctype):
            try:
                with open(path, "rb") as f:
                    self._send(200, f.read(), ctype)
            except FileNotFoundError:
                self._send(404, b'{"error":"file not found"}')
    return Handler


def main():
    ap = argparse.ArgumentParser(description="BatteryClaw Phase 6 — Dashboard server")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--state", default=os.path.join(_HERE, "..", "online", "state"))
    args = ap.parse_args()

    os.makedirs(args.state, exist_ok=True)
    data = DashboardData(args.state)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(data))
    print(f"BatteryClaw dashboard: http://127.0.0.1:{args.port}")
    print(f"State dir: {os.path.abspath(args.state)}  (chỉ bind localhost)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng dashboard.")


if __name__ == "__main__":
    main()
