"""
BatteryClaw — commercial/notifications.py  (PHASE 6 — mục 6.4)

Sinh thông báo thông minh từ trạng thái + stats:
  • "Pin còn 20%, đã bật chế độ tiết kiệm khẩn cấp"
  • "Bạn vừa tiết kiệm được 45 phút pin hôm nay"
  • "dGPU đang chạy không cần thiết, tắt để tiết kiệm 3W?"
  • "Pin đã đầy, dừng sạc để bảo vệ pin?"

Có chống spam: mỗi loại notification chỉ nhắc lại sau cooldown (mặc định 30 phút).
File chỉ lo SINH nội dung + chống lặp; việc hiển thị (toast Windows) do app làm.
"""

import time

COOLDOWN_SEC = 1800   # 30 phút giữa 2 lần cùng loại


class NotificationEngine:
    def __init__(self, cooldown=COOLDOWN_SEC):
        self.cooldown = cooldown
        self._last = {}       # loại -> thời điểm gửi cuối

    def _ok(self, kind, now):
        return now - self._last.get(kind, -1e9) >= self.cooldown

    def check(self, state, stats=None, now=None):
        """Trả list notification {kind, title, body, level} nên hiển thị lúc này."""
        now = now or time.time()
        out = []

        batt = state.get("batt_pct", 100)
        plugged = state.get("plugged", False)
        charging = state.get("charging", False)
        gpu_type = state.get("gpu_type", -1)     # 1 = dGPU
        is_game = state.get("is_game", False)

        # 1) Pin yếu -> đã bật tiết kiệm khẩn cấp
        if not plugged and batt <= 20 and self._ok("low_batt", now):
            out.append({
                "kind": "low_batt", "level": "warning",
                "title": "Pin yếu",
                "body": f"Pin còn {batt}%. BatteryClaw đã bật chế độ tiết kiệm khẩn cấp.",
            })
            self._last["low_batt"] = now

        # 2) dGPU chạy không cần thiet (không game) -> gợi ý tắt
        if gpu_type == 1 and not is_game and not plugged \
                and self._ok("dgpu_idle", now):
            out.append({
                "kind": "dgpu_idle", "level": "info",
                "title": "Phát hiện dGPU chạy nền",
                "body": "dGPU đang bật mà không cần thiết — tắt để tiết kiệm ~3W?",
            })
            self._last["dgpu_idle"] = now

        # 3) Pin đầy khi cắm sạc -> bảo vệ pin
        if plugged and batt >= 98 and charging and self._ok("full_charge", now):
            out.append({
                "kind": "full_charge", "level": "info",
                "title": "Pin đã đầy",
                "body": "Pin đã đầy. Cân nhắc dừng sạc ở 80% để bảo vệ tuổi thọ pin.",
            })
            self._last["full_charge"] = now

        # 4) Thành tích tiết kiệm hôm nay (mỗi ngày 1 lần buổi chiều)
        if stats is not None and self._ok("saved_today", now):
            t, y, diff = stats.today_vs_yesterday()
            if diff > 600:    # tiết kiệm hơn hôm qua >10 phút
                mins = diff // 60
                out.append({
                    "kind": "saved_today", "level": "success",
                    "title": "Hôm nay pin trâu hơn",
                    "body": f"Bạn dùng pin lâu hơn hôm qua {mins} phút!",
                })
                self._last["saved_today"] = now

        return out


if __name__ == "__main__":
    print("BatteryClaw 6.4 — NotificationEngine self-test")
    ne = NotificationEngine(cooldown=1800)
    t0 = 10000.0

    # pin yếu
    n = ne.check({"batt_pct": 18, "plugged": False}, now=t0)
    kinds = [x["kind"] for x in n]
    print("  pin 18%:", kinds)
    assert "low_batt" in kinds

    # gọi lại ngay -> bị cooldown chặn
    n2 = ne.check({"batt_pct": 17, "plugged": False}, now=t0 + 60)
    assert "low_batt" not in [x["kind"] for x in n2]

    # sau cooldown -> nhắc lại được
    n3 = ne.check({"batt_pct": 16, "plugged": False}, now=t0 + 2000)
    assert "low_batt" in [x["kind"] for x in n3]

    # dGPU chạy nền (không game)
    n4 = ne.check({"batt_pct": 60, "plugged": False, "gpu_type": 1,
                   "is_game": False}, now=t0 + 5000)
    print("  dGPU nền:", [x["kind"] for x in n4])
    assert "dgpu_idle" in [x["kind"] for x in n4]

    # pin đầy đang sạc
    n5 = ne.check({"batt_pct": 99, "plugged": True, "charging": True}, now=t0 + 8000)
    assert "full_charge" in [x["kind"] for x in n5]
    print("  pin đầy:", n5[0]["body"])
    print("PASS ✓")
