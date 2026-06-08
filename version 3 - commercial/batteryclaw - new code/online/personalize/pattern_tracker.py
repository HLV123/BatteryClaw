"""
BatteryClaw — personalize/pattern_tracker.py  (PHASE 3 — mục 3.3)

Học thói quen của RIÊNG người dùng này để chủ động (không chỉ phản ứng):
  • "8h-17h thường code Python -> cần CPU cao"
  • "buổi tối thường xem video -> ưu tiên tiết kiệm"
  • "app X xuất hiện -> sắp cần pin lâu"

Cách làm nhẹ, không cần ML nặng: thống kê trực tuyến (online stats) theo
24 khung giờ. Mỗi khung giữ phân bố workload + mức xả trung bình.
Từ đó suy ra "gợi ý ngữ cảnh" để vòng chính nhích policy đúng hướng.

Lưu/nạp JSON để bền qua các phiên.
"""

import json
import os

N_HOURS    = 24
N_WORKLOAD = 5    # idle, browse, office, compile, game


class PatternTracker:
    def __init__(self, path=None):
        self.path = path
        # đếm số lần mỗi (giờ, workload)
        self.counts = [[0] * N_WORKLOAD for _ in range(N_HOURS)]
        # mức xả trung bình theo giờ (EMA)
        self.discharge_ema = [0.0] * N_HOURS
        self.ema_alpha = 0.05
        if path and os.path.exists(path):
            self.load()

    def update(self, hour, workload_id, discharge_mw):
        h = int(hour) % N_HOURS
        w = max(0, min(N_WORKLOAD - 1, int(workload_id)))
        self.counts[h][w] += 1
        if self.discharge_ema[h] == 0.0:
            self.discharge_ema[h] = discharge_mw
        else:
            self.discharge_ema[h] = (
                (1 - self.ema_alpha) * self.discharge_ema[h]
                + self.ema_alpha * discharge_mw)

    def likely_workload(self, hour):
        """Workload hay gặp nhất ở khung giờ này (hoặc None nếu chưa đủ dữ liệu)."""
        h = int(hour) % N_HOURS
        total = sum(self.counts[h])
        if total < 5:
            return None, 0.0
        w = max(range(N_WORKLOAD), key=lambda i: self.counts[h][i])
        conf = self.counts[h][w] / total
        return w, conf

    def context_hint(self, hour):
        """Gợi ý cho vòng chính. Trả dict: nên 'save' (tiết kiệm) hay 'perform'.
        Không ép buộc — chỉ là gợi ý để nhích nhẹ policy (proactive)."""
        w, conf = self.likely_workload(hour)
        if w is None or conf < 0.5:
            return {"hint": "neutral", "confidence": conf}
        # compile/game -> cần hiệu năng; idle/browse/office -> ưu tiên tiết kiệm
        if w in (3, 4):
            return {"hint": "perform", "likely_workload": w, "confidence": conf}
        return {"hint": "save", "likely_workload": w, "confidence": conf}

    def save(self, path=None):
        p = path or self.path
        if not p:
            return
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"counts": self.counts,
                       "discharge_ema": self.discharge_ema}, f)

    def load(self, path=None):
        p = path or self.path
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        self.counts = d.get("counts", self.counts)
        self.discharge_ema = d.get("discharge_ema", self.discharge_ema)


if __name__ == "__main__":
    print("BatteryClaw 3.3 — PatternTracker self-test")
    pt = PatternTracker()

    # giả lập: 9h-11h hay compile (workload 3)
    for _ in range(20):
        pt.update(9, 3, 55000)
        pt.update(10, 3, 60000)
    # 21h hay xem video/browse (workload 1)
    for _ in range(20):
        pt.update(21, 1, 14000)

    w9, c9 = pt.likely_workload(9)
    print(f"  9h: workload hay gặp = {w9} (conf {c9:.2f})")
    assert w9 == 3

    h9 = pt.context_hint(9)
    h21 = pt.context_hint(21)
    print(f"  hint 9h:  {h9}")
    print(f"  hint 21h: {h21}")
    assert h9["hint"] == "perform"   # compile -> cần hiệu năng
    assert h21["hint"] == "save"     # tối xem video -> tiết kiệm

    # khung giờ chưa có dữ liệu -> neutral
    assert pt.context_hint(3)["hint"] == "neutral"

    # save/load
    pt.save("/tmp/_bc_pattern.json")
    pt2 = PatternTracker(path="/tmp/_bc_pattern.json")
    assert pt2.likely_workload(9)[0] == 3
    print("PASS ✓")
