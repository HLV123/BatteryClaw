"""
BatteryClaw — feedback/feedback_store.py  (PHASE 3 — mục 3.4)

Người dùng dạy model bằng nút bấm:
  • "Nhanh hơn"      -> hành động vừa làm BỊ phạt (reward âm) — đừng tiết kiệm kiểu đó
  • "Tiết kiệm hơn"  -> hành động vừa làm ĐƯỢC thưởng (reward dương)

Cơ chế: khi user bấm, ta lấy transition GẦN NHẤT, điều chỉnh reward của nó
rồi đẩy (lại) vào replay buffer để fine-tune học theo. Đơn giản, hiệu quả.

File này chỉ lo: nhận feedback -> tạo transition có reward điều chỉnh.
Việc đẩy vào buffer do online_loop điều phối.
"""

FASTER_PENALTY = -1.0    # "Nhanh hơn": phạt hành động tiết kiệm vừa rồi
SAVE_BONUS     = +1.0    # "Tiết kiệm hơn": thưởng


class FeedbackStore:
    def __init__(self):
        self.last_transition = None    # (s, a, r, s2)
        self.events = []               # lịch sử feedback (cho thống kê)

    def remember(self, s, a, r, s2):
        """Vòng chính gọi mỗi bước để nhớ transition gần nhất."""
        self.last_transition = (s, a, r, s2)

    def feedback(self, kind):
        """kind: 'faster' | 'save'. Trả transition đã chỉnh reward, hoặc None."""
        if self.last_transition is None:
            return None
        s, a, r, s2 = self.last_transition
        if kind == "faster":
            new_r = FASTER_PENALTY
        elif kind == "save":
            new_r = SAVE_BONUS
        else:
            return None
        self.events.append(kind)
        return (s, a, float(new_r), s2)

    def stats(self):
        return {"faster": self.events.count("faster"),
                "save":   self.events.count("save"),
                "total":  len(self.events)}


if __name__ == "__main__":
    import numpy as np
    print("BatteryClaw 3.4 — FeedbackStore self-test")
    fs = FeedbackStore()

    # chưa có transition -> feedback trả None
    assert fs.feedback("faster") is None

    s  = np.zeros(15, dtype=np.float32)
    a  = np.zeros(7,  dtype=np.float32)
    s2 = np.zeros(15, dtype=np.float32)
    fs.remember(s, a, 0.2, s2)

    t = fs.feedback("faster")
    print("  'Nhanh hơn' -> reward:", t[2])
    assert t[2] == FASTER_PENALTY

    t = fs.feedback("save")
    print("  'Tiết kiệm hơn' -> reward:", t[2])
    assert t[2] == SAVE_BONUS

    print("  stats:", fs.stats())
    assert fs.stats()["total"] == 2
    print("PASS ✓")
