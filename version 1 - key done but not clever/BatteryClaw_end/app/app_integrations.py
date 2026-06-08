"""
BatteryClaw — app/app_integrations.py  (PHASE 6 — cầu nối GUI)

Gom phần tích hợp Phase 6 vào GUI để setup_wizard.py gọn:
  • DashboardLauncher : chạy dashboard server (localhost) + mở trình duyệt
  • ProfileBridge     : đọc/ghi hồ sơ người dùng (commercial/profiles.py)
  • Toaster           : hiển thị toast Windows từ notifications (commercial/notifications.py)

Tách khỏi setup_wizard để mỗi file một nhiệm vụ. Mọi thứ ở đây "an toàn khi
thiếu" — nếu module/exe chưa có thì báo nhẹ, không làm sập app.

State dir dùng chung với online learning: %APPDATA%/BatteryClaw/state
"""

import os
import sys
import subprocess
import threading
import webbrowser

APPDATA   = os.environ.get("APPDATA", ".")
STATE_DIR = os.path.join(APPDATA, "BatteryClaw", "state")
os.makedirs(STATE_DIR, exist_ok=True)

# Đường dẫn tới các thành phần (chạy từ source; bản đóng gói chỉnh BASE tương tự app)
_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD_SERVER = os.path.join(_BASE, "dashboard", "server.py")
COMMERCIAL_DIR   = os.path.join(_BASE, "commercial")

if COMMERCIAL_DIR not in sys.path:
    sys.path.insert(0, COMMERCIAL_DIR)


# ── 6.1/6.2 — Dashboard ─────────────────────────────────────────────────────
class DashboardLauncher:
    """Chạy dashboard server nền + mở trình duyệt. Bấm lại thì chỉ mở tab."""

    def __init__(self, port=8777, state_dir=STATE_DIR):
        self.port = port
        self.state_dir = state_dir
        self._proc = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def is_running(self):
        return self._proc is not None and self._proc.poll() is None

    def open(self):
        """Đảm bảo server chạy rồi mở trình duyệt. Trả (ok, thông điệp)."""
        if not os.path.exists(DASHBOARD_SERVER):
            return False, "Không tìm thấy dashboard server."
        if not self.is_running():
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self._proc = subprocess.Popen(
                    [sys.executable, DASHBOARD_SERVER,
                     "--port", str(self.port), "--state", self.state_dir],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=flags)
            except Exception as e:
                return False, f"Lỗi mở dashboard: {e}"
        # cho server kịp bind rồi mở browser
        threading.Timer(0.8, lambda: webbrowser.open(self.url)).start()
        return True, self.url

    def stop(self):
        if self.is_running():
            self._proc.terminate()
        self._proc = None


# ── 6.3 — Profile ───────────────────────────────────────────────────────────
class ProfileBridge:
    """Bọc ProfileManager cho GUI: liệt kê nhãn, đổi hồ sơ, lưu."""

    def __init__(self, state_dir=STATE_DIR):
        from profiles import ProfileManager
        self.pm = ProfileManager(os.path.join(state_dir, "profile.json"))

    def labels(self):
        """Trả list (key, nhãn) để đổ vào dropdown."""
        return [(k, v["label"]) for k, v in self.pm.list_profiles().items()]

    def active_label(self):
        return self.pm.get()["label"]

    def active_key(self):
        return self.pm.active

    def set_by_label(self, label):
        for k, v in self.pm.list_profiles().items():
            if v["label"] == label:
                self.pm.set_active(k)
                self.pm.save()
                return k
        return None


# ── 6.4 — Toast notifications ───────────────────────────────────────────────
class Toaster:
    """Hiển thị toast Windows. Tự chọn cách khả dụng; thiếu thì im lặng."""

    def __init__(self):
        from notifications import NotificationEngine
        self.engine = NotificationEngine()
        self._method = self._detect()

    def _detect(self):
        # Ưu tiên winotify (nhẹ, toast thật Win10/11). Không có thì thử win10toast.
        try:
            import winotify  # noqa
            return "winotify"
        except Exception:
            pass
        try:
            import win10toast  # noqa
            return "win10toast"
        except Exception:
            return None

    def _show(self, title, body):
        if self._method == "winotify":
            try:
                from winotify import Notification
                Notification(app_id="BatteryClaw", title=title, msg=body).show()
                return
            except Exception:
                pass
        if self._method == "win10toast":
            try:
                from win10toast import ToastNotifier
                ToastNotifier().show_toast(title, body, duration=5, threaded=True)
                return
            except Exception:
                pass
        # fallback: in ra (dev) — không làm phiền người dùng
        print(f"[toast] {title}: {body}")

    def check_and_notify(self, state, stats=None):
        """Sinh notification từ state + đẩy toast cho từng cái. Trả số toast."""
        notes = self.engine.check(state, stats=stats)
        for n in notes:
            self._show(n["title"], n["body"])
        return len(notes)


if __name__ == "__main__":
    print("BatteryClaw Phase 6 — app_integrations self-test")

    # Profile bridge
    pb = ProfileBridge(state_dir="/tmp/bc_test_state")
    labels = pb.labels()
    print("  profiles:", [l for _, l in labels])
    assert any(l == "Gaming" for _, l in labels)
    pb.set_by_label("Gaming")
    assert pb.active_key() == "gaming"
    print("  đổi sang:", pb.active_label())

    # Toaster (không có lib toast trên Linux -> fallback in ra)
    t = Toaster()
    n = t.check_and_notify({"batt_pct": 15, "plugged": False})
    print("  số toast sinh ra:", n)
    assert n >= 1

    # Dashboard launcher (không thực sự mở browser trong test)
    dl = DashboardLauncher(port=8788)
    print("  dashboard url:", dl.url)
    assert dl.url.startswith("http://127.0.0.1")
    print("PASS ✓")
