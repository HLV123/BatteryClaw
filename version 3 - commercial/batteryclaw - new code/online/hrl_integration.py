"""
BatteryClaw — online/hrl_integration.py  (Tầng 2.3 — nối HRL vào deploy, opt-in)

Cách nối Hierarchical RL vào luồng deploy MÀ KHÔNG phá policy phẳng đang chạy ổn:
Manager (tầng cao, chạy mỗi vài phút) nhìn pin/giờ/sạc/thói quen → quyết CHẾ ĐỘ
(save_max / balanced / performance). Chế độ này map sang PROFILE MODEL (3 model đã
train ở Tầng 1.1) → app tự đổi model cho hợp hoàn cảnh.

Đây là dùng HRL ở mức "chọn chiến lược", thực dụng và an toàn — khác với nối Worker
goal-conditioned vào từng action (phức tạp, đụng contract). App có thể bật tính năng
"tự đổi profile theo hoàn cảnh" bằng cách dùng module này; mặc định tắt.

Dùng:
    from hrl_integration import AutoProfileManager
    apm = AutoProfileManager()
    profile = apm.suggest(battery_pct=45, hour=14, plugged=False, pattern_hint=None)
    # profile in {"battery_saver","balanced","performance"} -> chọn onnx tương ứng
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "advanced", "hierarchy"))

try:
    from manager import Manager
    _HAS_MANAGER = True
except Exception:
    _HAS_MANAGER = False


# map chế độ Manager (save_max/balanced/performance) -> profile model (Tầng 1.1)
_MODE_TO_PROFILE = {
    "save_max":    "battery_saver",
    "balanced":    "balanced",
    "performance": "performance",
}


class AutoProfileManager:
    """Dùng Manager (HRL) để gợi ý profile model theo hoàn cảnh.
    Có hysteresis: chỉ đổi profile khi chế độ ổn định vài lần liên tiếp, tránh
    đổi model xoành xoạch (mỗi lần đổi phải nạp lại ONNX)."""

    def __init__(self, stable_count=3):
        self.manager = Manager() if _HAS_MANAGER else None
        self.cur_profile = "balanced"
        self._pending = None
        self._pending_n = 0
        self._stable_count = stable_count

    def available(self):
        return self.manager is not None

    def suggest(self, battery_pct, hour, plugged=False, pattern_hint=None):
        """Trả profile nên dùng. Nếu Manager không có -> giữ balanced."""
        if self.manager is None:
            return self.cur_profile
        decision = self.manager.decide(battery_pct, hour,
                                       pattern_hint=pattern_hint, plugged=plugged)
        want = _MODE_TO_PROFILE.get(decision["mode"], "balanced")

        # hysteresis: chế độ mới phải lặp đủ stable_count lần mới đổi thật
        if want == self.cur_profile:
            self._pending = None
            self._pending_n = 0
        else:
            if want == self._pending:
                self._pending_n += 1
            else:
                self._pending = want
                self._pending_n = 1
            if self._pending_n >= self._stable_count:
                self.cur_profile = want
                self._pending = None
                self._pending_n = 0
        return self.cur_profile

    def last_reason(self, battery_pct, hour, plugged=False, pattern_hint=None):
        if self.manager is None:
            return "HRL không khả dụng -> giữ balanced"
        return self.manager.decide(battery_pct, hour,
                                   pattern_hint=pattern_hint, plugged=plugged)["reason"]


if __name__ == "__main__":
    print("BatteryClaw — HRL AutoProfileManager self-test")
    apm = AutoProfileManager(stable_count=2)
    print("  Manager khả dụng:", apm.available())
    # pin thấp -> sau vài lần phải thành battery_saver
    seq = [apm.suggest(10, 14) for _ in range(3)]
    print("  pin 10% x3:", seq, "->", apm.cur_profile)
    assert apm.cur_profile == "battery_saver", "pin thấp phải -> battery_saver"
    # cắm sạc -> performance
    apm2 = AutoProfileManager(stable_count=2)
    seq2 = [apm2.suggest(80, 10, plugged=True) for _ in range(3)]
    print("  cắm sạc x3:", seq2, "->", apm2.cur_profile)
    assert apm2.cur_profile == "performance", "cắm sạc phải -> performance"
    print("PASS ✓")
