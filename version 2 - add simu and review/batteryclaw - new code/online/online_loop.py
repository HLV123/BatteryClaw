"""
BatteryClaw — online_loop.py  (PHASE 3 — điều phối)

Ghép các mảnh Phase 3 thành một vòng online learning:

  transition đến (s, a, r, s')
        │
        ├─ feedback.remember(...)            # 3.4 nhớ để user có thể chấm điểm
        ├─ pattern.update(giờ, workload, xả) # 3.3 học thói quen
        ├─ buffer.add(...)                   # 3.1 tích lũy trải nghiệm
        │
   (khi máy nhàn > IDLE_MIN phút)
        └─ finetuner.step(...)               # 3.2 fine-tune + validate + rollback (3.5)

  Quyết định action mỗi bước:
        policy -> modes.apply (3.4) -> constraints.clamp (3.5) -> action an toàn

File này KHÔNG tự đọc pipe/đọc máy — nó nhận dữ liệu từ bên ngoài (rl_brain
hoặc test) để dễ kiểm thử. Cách nối với rl_brain ghi trong PHASE3_NOTES.md.
"""

import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "buffer"))
sys.path.insert(0, os.path.join(_HERE, "safety"))
sys.path.insert(0, os.path.join(_HERE, "finetune"))
sys.path.insert(0, os.path.join(_HERE, "personalize"))
sys.path.insert(0, os.path.join(_HERE, "feedback"))

from replay_buffer import ReplayBuffer
from constraints import clamp_action, is_state_anomalous
from pattern_tracker import PatternTracker
from feedback_store import FeedbackStore
from modes import ModeManager

IDLE_MINUTES_FOR_FINETUNE = 5     # máy nhàn >5 phút mới fine-tune (mục 3.2)
FINETUNE_EVERY_SEC        = 600   # tối thiểu 10 phút giữa 2 lần fine-tune


class OnlineLearner:
    def __init__(self, state_dir, policy=None, model_path=None):
        os.makedirs(state_dir, exist_ok=True)
        self.buffer = ReplayBuffer(
            capacity=10000, path=os.path.join(state_dir, "replay.npz"))
        self.pattern = PatternTracker(
            path=os.path.join(state_dir, "pattern.json"))
        self.feedback = FeedbackStore()
        self.modes = ModeManager()

        self.policy = policy
        self.model_path = model_path
        self.finetuner = None
        self._last_finetune = 0.0
        self._last_activity = time.time()

        # chỉ bật fine-tuner nếu có policy + checkpoint
        if policy is not None and model_path is not None:
            sys.path.insert(0, os.path.join(_HERE, "finetune"))
            from finetuner import FineTuner
            from checkpoint import CheckpointManager
            cm = CheckpointManager(os.path.join(state_dir, "ckpt"))
            self.finetuner = FineTuner(policy, self.buffer, cm)

    # ── mỗi bước: ghi nhận transition ───────────────────────────────────────
    def observe(self, s, a, r, s2, hour=None, workload_id=None, discharge_mw=0.0):
        self.feedback.remember(s, a, r, s2)
        self.buffer.add(s, a, r, s2)
        if hour is not None and workload_id is not None:
            self.pattern.update(hour, workload_id, discharge_mw)

    # ── quyết định action an toàn (mode -> constraints) ─────────────────────
    def finalize_action(self, action: dict, state: dict):
        a = self.modes.apply(action, state)          # 3.4 ghi đè mode (nếu có)
        a, reasons = clamp_action(a, state)          # 3.5 ràng buộc cứng
        return a, reasons

    # ── user feedback (3.4) ─────────────────────────────────────────────────
    def user_feedback(self, kind):
        t = self.feedback.feedback(kind)
        if t is not None:
            self.buffer.add(*t)      # đẩy transition đã chỉnh reward vào buffer
        return t is not None

    def set_mode(self, mode, minutes=30):
        self.modes.set_mode(mode, minutes)

    # ── đánh dấu hoạt động (để biết khi nào máy nhàn) ───────────────────────
    def mark_activity(self):
        self._last_activity = time.time()

    def idle_seconds(self):
        return time.time() - self._last_activity

    # ── fine-tune khi đủ điều kiện (gọi định kỳ từ vòng ngoài) ──────────────
    def maybe_finetune(self):
        if self.finetuner is None:
            return None
        now = time.time()
        if self.idle_seconds() < IDLE_MINUTES_FOR_FINETUNE * 60:
            return None
        if now - self._last_finetune < FINETUNE_EVERY_SEC:
            return None
        if len(self.buffer) < 32:
            return None
        res = self.finetuner.step(self.model_path)
        if res.get("ok") and res.get("improved"):
            self.finetuner.export(self.model_path)   # deploy bản tốt hơn
        self._last_finetune = now
        return res

    # ── lưu trạng thái xuống đĩa (gọi khi thoát) ────────────────────────────
    def save(self):
        self.buffer.save()
        self.pattern.save()


if __name__ == "__main__":
    import tempfile
    import torch
    import torch.nn as nn

    print("BatteryClaw Phase 3 — OnlineLearner integration test")

    policy = nn.Sequential(nn.Linear(15, 32), nn.ReLU(), nn.Linear(32, 7), nn.Tanh())
    d = tempfile.mkdtemp()
    mp = os.path.join(d, "policy.pt")
    torch.save(policy.state_dict(), mp)

    ol = OnlineLearner(os.path.join(d, "state"), policy=policy, model_path=mp)
    rng = np.random.default_rng(0)

    # nạp 200 transition giả
    for i in range(200):
        s  = rng.random(15).astype(np.float32)
        a  = rng.random(7).astype(np.float32)
        a[0] = 0.2 + a[0] * 0.8; a[1] = 0.3 + a[1] * 0.7
        a[3] = rng.integers(0, 3); a[4] = rng.integers(0, 3)
        s2 = rng.random(15).astype(np.float32)
        ol.observe(s, a, float(rng.normal()), s2,
                   hour=9, workload_id=3, discharge_mw=55000)
    print("  buffer size:", len(ol.buffer))
    assert len(ol.buffer) == 200

    # action an toàn: nóng + game -> bị ép
    act = {"cpu_throttle_max": 1.0, "brightness_act": 0.9, "gpu_switch": 0,
           "refresh_mode": 2}
    safe, reasons = ol.finalize_action(act, {"cpu_temp_c": 97, "is_game": 1})
    print("  safe action:", safe)
    print("  lý do chỉnh:", reasons)
    assert safe["cpu_throttle_max"] <= 0.6 and safe["gpu_switch"] == 1

    # mode họp quan trọng ghi đè
    ol.set_mode("meeting", minutes=10)
    safe, _ = ol.finalize_action({"cpu_throttle_max": 0.3}, {"cpu_temp_c": 50})
    assert safe["cpu_throttle_max"] == 0.95

    # user feedback đẩy vào buffer
    n_before = len(ol.buffer)
    assert ol.user_feedback("save")
    assert len(ol.buffer) == n_before + 1

    # fine-tune: chưa idle đủ -> None
    ol.mark_activity()
    assert ol.maybe_finetune() is None

    # giả lập đã idle đủ lâu -> chạy fine-tune
    ol._last_activity = time.time() - IDLE_MINUTES_FOR_FINETUNE * 60 - 1
    res = ol.maybe_finetune()
    print("  fine-tune khi idle:", res)
    assert res is not None and res["ok"]

    ol.save()
    print("PASS ✓")
