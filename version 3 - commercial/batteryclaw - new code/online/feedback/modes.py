"""
BatteryClaw — feedback/modes.py  (PHASE 3 — mục 3.4)

Chế độ tạm thời do người dùng bật, GHI ĐÈ policy trong N phút:
  • "Họp quan trọng"  -> tắt mọi tiết kiệm: throttle cao, brightness cao,
                          không tắt dGPU, không hạ refresh. Trong N phút.
  • "Pin yếu, cần lâu" -> tiết kiệm tối đa: throttle thấp, brightness thấp,
                          tắt dGPU (nếu an toàn), 60Hz, wifi power save.

Mode hết hạn tự quay về policy bình thường. File chỉ lo logic mode + thời hạn.
"""

import time

MEETING      = "meeting"      # họp quan trọng
SAVE_MAX     = "save_max"     # pin yếu, tiết kiệm tối đa
NONE         = "none"

DEFAULT_MINUTES = 30


class ModeManager:
    def __init__(self):
        self.mode = NONE
        self.until = 0.0      # epoch giây; 0 = không có mode

    def set_mode(self, mode, minutes=DEFAULT_MINUTES):
        self.mode = mode
        self.until = time.time() + minutes * 60 if mode != NONE else 0.0

    def clear(self):
        self.mode = NONE
        self.until = 0.0

    def active(self):
        """Mode hiện đang hiệu lực (tự hết hạn)."""
        if self.mode != NONE and time.time() > self.until:
            self.clear()
        return self.mode

    def remaining_sec(self):
        return max(0, int(self.until - time.time())) if self.mode != NONE else 0

    def apply(self, action: dict, state: dict):
        """Ghi đè action theo mode đang hiệu lực. Trả action mới."""
        m = self.active()
        if m == NONE:
            return action
        a = dict(action)
        if m == MEETING:
            a["cpu_throttle_max"] = max(a.get("cpu_throttle_max", 0.5), 0.95)
            a["brightness_act"]   = max(a.get("brightness_act", 0.5), 0.80)
            a["gpu_switch"]       = 1     # giữ dGPU
            a["refresh_mode"]     = 2     # giữ refresh cao
            a["defer_tasks"]      = 0
        elif m == SAVE_MAX:
            a["cpu_throttle_max"] = min(a.get("cpu_throttle_max", 0.5), 0.40)
            a["brightness_act"]   = min(a.get("brightness_act", 0.5), 0.35)
            # chỉ tắt dGPU khi KHÔNG game (constraints sẽ chặn nếu game)
            a["gpu_switch"]       = 0 if not state.get("is_game") else 1
            a["refresh_mode"]     = 0     # 60Hz
            a["wifi_power_save"]  = 1
            a["defer_tasks"]      = 1
        return a


if __name__ == "__main__":
    print("BatteryClaw 3.4 — ModeManager self-test")
    mm = ModeManager()

    base = {"cpu_throttle_max": 0.5, "brightness_act": 0.5,
            "gpu_switch": 0, "refresh_mode": 0}

    # không mode -> giữ nguyên
    assert mm.apply(dict(base), {}) == base

    # họp quan trọng -> nâng hiệu năng, giữ dGPU
    mm.set_mode(MEETING, minutes=10)
    a = mm.apply(dict(base), {})
    print("  meeting:", a)
    assert a["cpu_throttle_max"] == 0.95 and a["gpu_switch"] == 1 and a["refresh_mode"] == 2
    assert mm.remaining_sec() > 0

    # pin yếu -> tiết kiệm tối đa (không game)
    mm.set_mode(SAVE_MAX)
    a = mm.apply(dict(base), {"is_game": 0})
    print("  save_max:", a)
    assert a["cpu_throttle_max"] == 0.40 and a["gpu_switch"] == 0 and a["wifi_power_save"] == 1

    # save_max nhưng đang game -> KHÔNG tắt dGPU
    a = mm.apply(dict(base), {"is_game": 1})
    assert a["gpu_switch"] == 1

    # hết hạn -> tự về none
    mm.set_mode(MEETING, minutes=0)
    time.sleep(0.01)
    assert mm.active() == NONE
    print("PASS ✓")
