"""
BatteryClaw — buy_business.py

Customer-facing GUI với đầy đủ kiểm tra license.
Gộp từ:
  - UI đẹp dark mode của batteryclaw_app.py
  - Hệ thống kích hoạt API Key của setup_wizard.py

Luồng hoạt động:
  - Lần đầu  → Nhập Server URL + Email → Nhập API Key → Kích hoạt → Dùng
  - Lần sau  → Tự verify với server → Vào thẳng (hoặc offline grace nếu mất mạng)
  - Key hết hạn / bị thu hồi → Quay về màn hình nhập lại

Đóng gói: build_business.ps1 → BatteryClaw.exe (PyInstaller, --uac-admin)
"""

import os
import sys
import threading
import subprocess
import time
import hashlib
import platform
import json
import datetime
import re
import requests
import tkinter as tk
from tkinter import ttk, messagebox

# ── Resolve paths (source hoặc PyInstaller frozen) ────────────────────────────
def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE = _base_dir()

def _find(*candidates):
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None

ENGINE_EXE = _find(
    os.path.join(BASE, "engine", "BatteryClawEngine.exe"),
    os.path.join(BASE, "engine_dotnet", "bin", "Release",
                 "net8.0-windows10.0.19041.0", "BatteryClawEngine.exe"),
)
MODEL_PATH = _find(
    os.path.join(BASE, "models", "batteryclaw_policy.onnx"),
    os.path.join(BASE, "simulator", "models", "batteryclaw_policy.onnx"),
)

sys.path.insert(0, os.path.join(BASE, "brain"))

# ── Config & License helpers ──────────────────────────────────────────────────
# QUAN TRONG: state (online learning, dashboard, license) phai ghi vao thu muc
#  GHI DUOC. Neu khach cai app vao C:\Program Files\, thu muc canh exe bi Windows
#  chan ghi -> online learning that bai am tham. Vi vay dung %APPDATA%\BatteryClaw\.
APP_DATA  = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                         "BatteryClaw")
STATE_DIR = os.path.join(APP_DATA, "state")
os.makedirs(STATE_DIR, exist_ok=True)
CFG_FILE = os.path.join(APP_DATA, "config.json")
os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)

def machine_id():
    import uuid
    raw = str(uuid.getnode()) + platform.processor() + platform.node()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def load_cfg():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(d):
    os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)
    with open(CFG_FILE, "w") as f:
        json.dump(d, f, indent=2)

def api_post(url, path, data):
    r = requests.post(url.rstrip("/") + path, json=data, timeout=10)
    return r.json()

# ── Bảng màu dark mode (Windows 11 vibe) ─────────────────────────────────────
BG       = "#202020"
CARD     = "#2b2b2b"
ACCENT   = "#4cc2ff"
TEXT     = "#ffffff"
MUTED    = "#9b9b9b"
GOOD     = "#6ccb5f"
WARN     = "#e6a23c"
ERR      = "#ff5555"
INPUT_BG = "#303030"
INPUT_BD = "#505050"


# ══════════════════════════════════════════════════════════════════════════════
#  LICENSE GATE — màn hình kích hoạt, hiện TRƯỚC khi vào app chính
# ══════════════════════════════════════════════════════════════════════════════
class LicenseGate:
    """
    Kiểm tra license trước khi mở app chính.
    Gọi on_success(cfg) khi license hợp lệ.
    """

    def __init__(self, root, on_success):
        self.root       = root
        self.on_success = on_success
        self.cfg        = load_cfg()
        self.mid        = machine_id()

        self.frame = tk.Frame(root, bg=BG)
        self.frame.pack(fill="both", expand=True, padx=28)

        self._check_existing()

    # ── Helpers UI ────────────────────────────────────────────────────────────
    def _lbl(self, parent, text, size=10, fg=None, bold=False, anchor="w"):
        font = ("Segoe UI Semibold" if bold else "Segoe UI", size)
        return tk.Label(parent, text=text, bg=BG,
                        fg=fg or MUTED, font=font, anchor=anchor)

    def _entry(self, parent, var=None, show=None):
        """Input có viền mỏng, dark background."""
        wrap = tk.Frame(parent, bg=INPUT_BD, padx=1, pady=1)
        kw = dict(font=("Segoe UI", 11), bg=INPUT_BG, fg=TEXT,
                  relief="flat", insertbackground=TEXT, bd=0)
        if var:  kw["textvariable"] = var
        if show: kw["show"] = show
        e = tk.Entry(wrap, **kw)
        e.pack(fill="x", ipady=7, ipadx=10)
        return wrap, e

    def _btn(self, parent, text, cmd, accent=True, full=True):
        bg  = ACCENT   if accent else CARD
        fg  = "#001018" if accent else TEXT
        abg = "#3aa9e0" if accent else "#3a3a3a"
        b = tk.Button(parent, text=text, command=cmd,
                      bg=bg, fg=fg, relief="flat",
                      font=("Segoe UI Semibold", 11), height=2,
                      activebackground=abg, cursor="hand2", bd=0)
        if full:
            b.pack(fill="x")
        return b

    def _err_label(self, parent, var):
        return tk.Label(parent, textvariable=var, bg=BG, fg=ERR,
                        font=("Segoe UI", 9), anchor="w", wraplength=360)

    def _spacer(self, parent, h=10):
        tk.Frame(parent, bg=BG, height=h).pack()

    def _clear(self):
        for w in self.frame.winfo_children():
            w.destroy()

    # ── Flow ──────────────────────────────────────────────────────────────────
    def _check_existing(self):
        """Có config cũ không? → verify; không → setup."""
        if (self.cfg.get("key") and self.cfg.get("server_url")
                and self.cfg.get("machine_id") == self.mid):
            self._show_verifying()
            threading.Thread(target=self._verify_online, daemon=True).start()
        else:
            self._show_setup()

    def _verify_online(self):
        try:
            r = api_post(self.cfg["server_url"], "/api/verify",
                         {"key": self.cfg["key"], "machine_id": self.mid})
            if r.get("ok"):
                if r.get("expires_at"):
                    self.cfg["expires_at"] = r["expires_at"]
                self.cfg["days_left"] = r.get("days_left", 0)
                save_cfg(self.cfg)
                self.root.after(0, lambda: self.on_success(self.cfg))
                return
            # Server từ chối (thu hồi / hết hạn)
            self.root.after(0, self._show_setup)
        except Exception:
            # Mất mạng → offline grace
            if self._offline_ok():
                self.root.after(0, lambda: self.on_success(self.cfg))
            else:
                self.root.after(0, self._show_setup)

    def _offline_ok(self):
        exp = self.cfg.get("expires_at")
        if not exp:
            return False
        try:
            return datetime.datetime.utcnow() <= datetime.datetime.fromisoformat(exp)
        except Exception:
            return False

    def destroy(self):
        self.frame.destroy()

    # ── Trang: Đang xác thực ─────────────────────────────────────────────────
    def _show_verifying(self):
        self._clear()
        self.root.geometry("440x560")
        f = tk.Frame(self.frame, bg=BG)
        f.pack(expand=True, pady=40)
        self._lbl(f, "Đang xác thực license...", size=12, fg=MUTED,
                  anchor="center").pack()

    # ── Trang 0: Server URL + Email ───────────────────────────────────────────
    def _show_setup(self):
        self._clear()
        self.root.geometry("440x390")

        self._lbl(self.frame, "Kết nối Server", size=14, fg=TEXT, bold=True).pack(
            anchor="w", pady=(4, 18))

        self._lbl(self.frame, "Server URL").pack(anchor="w")
        self.v_srv = tk.StringVar(value=self.cfg.get("server_url", ""))
        frm, _ = self._entry(self.frame, self.v_srv)
        frm.pack(fill="x", pady=(3, 2))
        self._lbl(self.frame, "Ví dụ: http://123.45.67.89:8000").pack(anchor="w")

        self._spacer(self.frame, 12)

        self._lbl(self.frame, "Email của bạn").pack(anchor="w")
        self.v_email = tk.StringVar(value=self.cfg.get("email", ""))
        frm2, _ = self._entry(self.frame, self.v_email)
        frm2.pack(fill="x", pady=(3, 2))

        self._spacer(self.frame, 14)

        self.v_err0 = tk.StringVar()
        self._err_label(self.frame, self.v_err0).pack(anchor="w", pady=(0, 6))
        self._btn(self.frame, "Tiếp theo →", self._do_setup)

    def _do_setup(self):
        url   = self.v_srv.get().strip().rstrip("/")
        if url.endswith("/admin"):
            url = url[:-6].rstrip("/")
        email = self.v_email.get().strip()
        if not url:
            self.v_err0.set("Vui lòng nhập Server URL"); return
        if not email or "@" not in email:
            self.v_err0.set("Email không hợp lệ"); return
        self.v_err0.set("Đang kiểm tra kết nối...")
        def _check():
            try:
                r = requests.get(url + "/health", timeout=6)
                if r.status_code == 200:
                    self.cfg["server_url"] = url
                    self.cfg["email"]      = email
                    save_cfg(self.cfg)
                    self.root.after(0, self._show_key)
                else:
                    self.root.after(0, lambda: self.v_err0.set(
                        f"Server trả lỗi HTTP {r.status_code}"))
            except Exception:
                self.root.after(0, lambda: self.v_err0.set(
                    "Không kết nối được server. Kiểm tra URL và thử lại."))
        threading.Thread(target=_check, daemon=True).start()

    # ── Trang 1: Nhập API Key ─────────────────────────────────────────────────
    def _show_key(self):
        self._clear()
        self.root.geometry("440x370")

        self._lbl(self.frame, "Nhập API Key", size=14, fg=TEXT, bold=True).pack(
            anchor="w", pady=(4, 18))

        self._lbl(self.frame, "API Key").pack(anchor="w")
        self.v_key = tk.StringVar()
        frm, entry = self._entry(self.frame, self.v_key)
        frm.pack(fill="x", pady=(3, 4))
        entry.bind("<Return>", lambda _: self._do_activate())
        self._lbl(self.frame, "Định dạng: BC-XXXX-XXXX-XXXX").pack(anchor="w")

        self._spacer(self.frame, 10)

        # Cảnh báo
        warn = tk.Frame(self.frame, bg="#2a2000", padx=12, pady=9)
        warn.pack(fill="x")
        tk.Label(warn, text="⚠  Key chỉ kích hoạt được 1 lần trên 1 máy",
                 bg="#2a2000", fg=WARN,
                 font=("Segoe UI", 9), anchor="w").pack(anchor="w")

        self._spacer(self.frame, 12)

        self.v_err1 = tk.StringVar()
        self._err_label(self.frame, self.v_err1).pack(anchor="w", pady=(0, 8))

        row = tk.Frame(self.frame, bg=BG)
        row.pack(fill="x")
        self._btn(row, "← Quay lại", self._show_setup, accent=False, full=False)\
            .pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._btn(row, "Kích hoạt", self._do_activate, accent=True, full=False)\
            .pack(side="left", fill="x", expand=True)

    def _do_activate(self):
        key = self.v_key.get().strip().upper()
        if not key:
            self.v_err1.set("Vui lòng nhập API Key"); return
        self.v_err1.set("Đang kích hoạt...")
        def _act():
            try:
                r = api_post(self.cfg["server_url"], "/api/activate",
                             {"key": key,
                              "email": self.cfg.get("email", ""),
                              "machine_id": self.mid})
                if r.get("ok"):
                    self.cfg.update({
                        "key":        key,
                        "machine_id": self.mid,
                        "days_left":  r.get("days_left", 0),
                        "expires_at": r.get("expires_at", ""),
                    })
                    save_cfg(self.cfg)
                    self.root.after(0, lambda: self.on_success(self.cfg))
                else:
                    msg = r.get("msg", "Lỗi kích hoạt")
                    self.root.after(0, lambda: self.v_err1.set(msg))
            except Exception:
                self.root.after(0, lambda: self.v_err1.set(
                    "Lỗi kết nối server. Kiểm tra mạng và thử lại."))
        threading.Thread(target=_act, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP — UI chính sau khi license hợp lệ
# ══════════════════════════════════════════════════════════════════════════════
class BatteryClawApp:
    def __init__(self, root, cfg):
        self.root         = root
        self.cfg          = cfg
        self.engine_proc  = None
        self.brain        = None
        self.brain_thread = None
        self.running      = False

        self._build_ui()
        self._refresh_status_loop()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        days  = self.cfg.get("days_left", 0)
        email = self.cfg.get("email", "")
        info  = f"{email}  •  Còn {days} ngày" if email else f"Còn {days} ngày"
        tk.Label(self.root, text=info, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(pady=(0, 10))

        # Status card
        self.card = tk.Frame(self.root, bg=CARD)
        self.card.pack(fill="x", padx=20, pady=8)
        self.status_dot = tk.Label(self.card, text="●", bg=CARD, fg=MUTED,
                                   font=("Segoe UI", 16))
        self.status_dot.grid(row=0, column=0, padx=(16, 8), pady=16)
        self.status_text = tk.Label(self.card, text="Đã dừng", bg=CARD, fg=TEXT,
                                    font=("Segoe UI Semibold", 13))
        self.status_text.grid(row=0, column=1, sticky="w", pady=16)

        # Live metrics
        self.metrics = tk.Frame(self.root, bg=BG)
        self.metrics.pack(fill="x", padx=20, pady=4)
        self.m_batt  = self._metric("Pin",            "--%")
        self.m_cpu   = self._metric("CPU",            "--%")
        self.m_app   = self._metric("Ứng dụng",      "--")
        self.m_saved = self._metric("Đã tiết kiệm",  "0 mWh")

        # Profile selector
        prow = tk.Frame(self.root, bg=BG)
        prow.pack(fill="x", padx=20, pady=(14, 6))
        tk.Label(prow, text="Hồ sơ", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left")
        self.profile = ttk.Combobox(prow, state="readonly", width=22,
                                    values=["Cân bằng", "Tiết kiệm pin", "Hiệu năng cao"])
        self.profile.set("Cân bằng")
        self.profile.pack(side="right")

        # Nút Bắt đầu / Dừng
        self.start_btn = tk.Button(
            self.root, text="Bắt đầu", command=self.toggle,
            bg=ACCENT, fg="#001018", relief="flat",
            font=("Segoe UI Semibold", 13), height=2,
            activebackground="#3aa9e0", cursor="hand2", bd=0)
        self.start_btn.pack(fill="x", padx=20, pady=(18, 6))

        # Nút Dashboard
        self.dash_btn = tk.Button(
            self.root, text="Mở Dashboard",
            command=self.open_dashboard,
            bg=CARD, fg=TEXT, relief="flat",
            font=("Segoe UI", 11), height=1,
            activebackground="#3a3a3a", cursor="hand2", bd=0)
        self.dash_btn.pack(fill="x", padx=20, pady=4)

        self.note = tk.Label(self.root, text="", bg=BG, fg=MUTED,
                             font=("Segoe UI", 9), wraplength=400, justify="center")
        self.note.pack(pady=(10, 0))

        if not ENGINE_EXE:
            self.note.config(text="Không tìm thấy engine. Vui lòng cài đặt lại.", fg=WARN)
        elif not MODEL_PATH:
            self.note.config(text="Không tìm thấy model. Vui lòng cài đặt lại.", fg=WARN)

    def _metric(self, label, value="--"):
        row = tk.Frame(self.metrics, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left")
        v = tk.Label(row, text=value, bg=BG, fg=TEXT,
                     font=("Segoe UI Semibold", 11))
        v.pack(side="right")
        return v

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def toggle(self):
        if self.running: self.stop()
        else:            self.start()

    def start(self):
        if not ENGINE_EXE or not MODEL_PATH:
            return
        self.status_text.config(text="Đang khởi động...")
        self.status_dot.config(fg=WARN)
        self.root.update()

        # 1) Khởi động engine ẩn (không cửa sổ)
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            env   = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
            self.engine_proc = subprocess.Popen(
                [ENGINE_EXE, "--serve"],
                creationflags=flags, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.note.config(text=f"Không thể khởi động engine: {e}", fg=WARN)
            return

        # 2) Chạy RL brain trong thread nền
        time.sleep(1.5)
        try:
            from rl_brain import RLBrain
            online_dir = STATE_DIR
            self.brain  = RLBrain(MODEL_PATH, online_dir=online_dir)
            self.running = True
            self.brain_thread = threading.Thread(target=self._brain_run, daemon=True)
            self.brain_thread.start()
        except Exception as e:
            self.note.config(text=f"Không thể khởi động brain: {e}", fg=WARN)
            self._kill_engine()
            return

        self.start_btn.config(text="Dừng lại", bg="#3a3a3a", fg=TEXT)
        self.status_text.config(text="Đang chạy")
        self.status_dot.config(fg=GOOD)
        self.note.config(text="Đang tối ưu pin. Bạn có thể thu nhỏ cửa sổ.", fg=MUTED)

    def _brain_run(self):
        try:
            self.brain.connect_and_run()
        except Exception:
            pass

    def stop(self):
        self.running = False
        if self.brain:
            try: self.brain.running = False
            except Exception: pass
        self._kill_engine()
        self.brain = None
        self.start_btn.config(text="Bắt đầu", bg=ACCENT, fg="#001018")
        self.status_text.config(text="Đã dừng")
        self.status_dot.config(fg=MUTED)
        self.note.config(text="", fg=MUTED)
        for m in (self.m_batt, self.m_cpu, self.m_app):
            m.config(text="--")

    def _kill_engine(self):
        if self.engine_proc:
            try: self.engine_proc.terminate()
            except Exception: pass
            self.engine_proc = None
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "BatteryClawEngine.exe"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception: pass

    # ── Live status ───────────────────────────────────────────────────────────
    def _refresh_status_loop(self):
        if self.running and self.brain:
            st    = getattr(self.brain, "last_state", None) or {}
            batt  = st.get("batt_pct")
            cpu   = st.get("cpu_load")
            app   = st.get("fg_app", "--")
            saved = getattr(self.brain, "total_saved_mwh", 0)
            if batt is not None: self.m_batt.config(text=f"{batt:.0f}%")
            if cpu  is not None: self.m_cpu.config(text=f"{cpu:.0f}%")
            self.m_app.config(text=(app or "--")[:18])
            self.m_saved.config(text=f"{saved:.0f} mWh")
        self.root.after(1500, self._refresh_status_loop)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    def open_dashboard(self):
        import webbrowser
        port = 8777
        if not getattr(self, "_dash_started", False):
            try:
                sys.path.insert(0, os.path.join(BASE, "dashboard"))
                import server as dash_server
                state_dir = STATE_DIR
                os.makedirs(state_dir, exist_ok=True)
                data  = dash_server.DashboardData(state_dir)
                from http.server import ThreadingHTTPServer
                httpd = ThreadingHTTPServer(("127.0.0.1", port),
                                            dash_server.make_handler(data))
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                self._dash_started = True
                self._dash_httpd   = httpd
            except Exception as e:
                self.note.config(text=f"Dashboard lỗi: {e}", fg=WARN)
                return
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()

    def on_close(self):
        self.stop()
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.title("BatteryClaw")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.geometry("440x560")

    # Header luôn hiển thị
    tk.Label(root, text="BatteryClaw", bg=BG, fg=TEXT,
             font=("Segoe UI Semibold", 22)).pack(pady=(22, 2))
    tk.Label(root, text="Smart battery optimizer", bg=BG, fg=MUTED,
             font=("Segoe UI", 10)).pack(pady=(0, 12))

    gate_ref = [None]

    def on_license_ok(cfg):
        """License hợp lệ → phá gate, hiện app chính."""
        if gate_ref[0]:
            gate_ref[0].destroy()
            gate_ref[0] = None
        root.geometry("440x560")
        app = BatteryClawApp(root, cfg)
        root.protocol("WM_DELETE_WINDOW", app.on_close)

    gate = LicenseGate(root, on_license_ok)
    gate_ref[0] = gate

    root.mainloop()


if __name__ == "__main__":
    main()
