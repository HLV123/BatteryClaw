"""
BatteryClaw — advanced/hierarchy/manager.py  (PHASE 4 — mục 4.3)

Tầng CAO của Hierarchical RL. Quyết định mỗi ~5 phút:
  • Chế độ chiến lược: SAVE_MAX / BALANCED / PERFORMANCE
  • Suy ra MỤC TIÊU discharge rate (mW) mà worker (tầng thấp) phải đạt

Manager nhìn bức tranh lớn: mức pin, giờ trong ngày, gợi ý pattern (Phase 3).
Nó KHÔNG chọn throttle/brightness cụ thể — đó là việc của worker.

Để nhẹ và minh bạch, manager ở đây là policy theo luật (rule-based) có tham số,
dễ giải thích cho người dùng. Có thể thay bằng RL sau mà không đổi giao diện.
"""

SAVE_MAX    = "save_max"
BALANCED    = "balanced"
PERFORMANCE = "performance"

# Mục tiêu discharge (mW) cho mỗi chế độ — worker cố bám theo.
TARGET_DISCHARGE_MW = {
    SAVE_MAX:    9000,
    BALANCED:    18000,
    PERFORMANCE: 40000,
}

DECISION_PERIOD_SEC = 300    # quyết định mỗi 5 phút


class Manager:
    def __init__(self):
        self.mode = BALANCED
        self.target_discharge_mw = TARGET_DISCHARGE_MW[BALANCED]

    def decide(self, battery_pct, hour, pattern_hint=None, plugged=False):
        """Chọn chế độ + mục tiêu discharge. Trả dict quyết định.
        battery_pct: 0..100. pattern_hint: 'save'/'perform'/'neutral' (Phase 3)."""
        # 1) Pin rất thấp -> luôn tiết kiệm tối đa, bất kể gì khác
        if battery_pct <= 15:
            mode = SAVE_MAX
        # 2) Cắm sạc -> ưu tiên hiệu năng (không cần dè sẻn)
        elif plugged:
            mode = PERFORMANCE
        # 3) Theo gợi ý pattern (thói quen giờ này)
        elif pattern_hint == "perform":
            mode = PERFORMANCE
        elif pattern_hint == "save":
            mode = SAVE_MAX
        # 4) Pin trung bình -> cân bằng; pin cao -> hơi thoải mái
        else:
            mode = BALANCED if battery_pct < 60 else BALANCED

        self.mode = mode
        self.target_discharge_mw = TARGET_DISCHARGE_MW[mode]
        return {
            "mode": mode,
            "target_discharge_mw": self.target_discharge_mw,
            "reason": self._reason(battery_pct, hour, pattern_hint, plugged),
        }

    def _reason(self, batt, hour, hint, plugged):
        if batt <= 15:
            return f"pin thấp ({batt}%) -> tiết kiệm tối đa"
        if plugged:
            return "đang cắm sạc -> ưu tiên hiệu năng"
        if hint in ("perform", "save"):
            return f"thói quen giờ {hour}h gợi ý: {hint}"
        return f"pin {batt}% -> cân bằng"


if __name__ == "__main__":
    print("BatteryClaw 4.3 — Manager self-test")
    m = Manager()

    d = m.decide(battery_pct=10, hour=14)
    print("  pin 10%:", d["mode"], d["target_discharge_mw"], "|", d["reason"])
    assert d["mode"] == SAVE_MAX

    d = m.decide(battery_pct=70, hour=10, plugged=True)
    print("  cắm sạc:", d["mode"], "|", d["reason"])
    assert d["mode"] == PERFORMANCE

    d = m.decide(battery_pct=50, hour=9, pattern_hint="perform")
    print("  pattern perform:", d["mode"], "|", d["reason"])
    assert d["mode"] == PERFORMANCE

    d = m.decide(battery_pct=50, hour=21, pattern_hint="save")
    assert d["mode"] == SAVE_MAX

    d = m.decide(battery_pct=50, hour=15)
    assert d["mode"] == BALANCED
    print("  mục tiêu discharge các chế độ:", TARGET_DISCHARGE_MW)
    print("PASS ✓")
