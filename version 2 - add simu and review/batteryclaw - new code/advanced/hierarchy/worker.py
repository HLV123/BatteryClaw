"""
BatteryClaw — advanced/hierarchy/worker.py  (PHASE 4 — mục 4.3)

Tầng THẤP của Hierarchical RL. Quyết định mỗi ~10 giây:
  • Chọn action cụ thể (throttle, gpu_switch, brightness, refresh...) để đạt
    MỤC TIÊU discharge mà manager (tầng cao) đề ra.

Worker nhận thêm "mục tiêu" vào observation: ghép target_discharge_norm vào
state 15 chiều -> 16 chiều. Nhờ vậy cùng một worker phục vụ được mọi chế độ
manager chọn (goal-conditioned policy).

Ở đây worker bọc quanh một policy (SAC actor hoặc ONNX). Nếu chưa có policy,
dùng controller theo luật để bám mục tiêu — vẫn chạy được ngay, thay sau cũng được.
"""

import os
import sys

import numpy as np

# [FIND-02] hang so chuan hoa dung chung tu commons/constants.py (single source).
try:
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "commons"))
    from constants import DISCHARGE_MAX_MW
except Exception:
    DISCHARGE_MAX_MW = 80000.0


class Worker:
    def __init__(self, policy=None):
        """policy: callable obs(16,) -> action(7,) trong [-1,1]. None -> rule-based."""
        self.policy = policy

    def act(self, state_vec15, target_discharge_mw, cur_discharge_mw):
        """Trả action dict 7 chiều (đã ở thang thực, không phải tanh)."""
        if self.policy is not None:
            obs16 = self._augment(state_vec15, target_discharge_mw)
            raw = np.asarray(self.policy(obs16)).reshape(-1)   # [-1,1]
            return self._raw_to_action(raw)
        # fallback: bộ điều khiển theo luật bám mục tiêu discharge
        return self._rule_based(target_discharge_mw, cur_discharge_mw)

    def _augment(self, state_vec15, target_mw):
        """Ghép mục tiêu (đã chuẩn hóa) vào cuối state -> 16 chiều."""
        s = np.asarray(state_vec15, dtype=np.float32).reshape(-1)
        target_norm = np.float32(np.clip(target_mw / DISCHARGE_MAX_MW, 0, 1))
        return np.concatenate([s, [target_norm]]).astype(np.float32)

    def _raw_to_action(self, raw):
        """tanh [-1,1] -> action thực (giống decode của rl_brain)."""
        sc = lambda x, lo, hi: float(lo + (x + 1) / 2 * (hi - lo))
        return {
            "cpu_throttle_max": float(np.clip(sc(raw[0], 0.2, 1.0), 0.2, 1.0)),
            "brightness_act"  : float(np.clip(sc(raw[1], 0.3, 1.0), 0.3, 1.0)),
            "defer_tasks"     : float(sc(raw[2], 0, 1) > 0.5),
            "gpu_switch"      : 0.0 if sc(raw[3], 0, 1) < 0.5 else 1.0,
            "refresh_mode"    : 0.0 if sc(raw[4], 0, 1) <= 0.4 else
                                (1.0 if sc(raw[4], 0, 1) <= 0.7 else 2.0),
            "wifi_power_save" : float(sc(raw[5], 0, 1) > 0.5),
            "charge_limit_on" : float(sc(raw[6], 0, 1) > 0.5),
        }

    def _rule_based(self, target_mw, cur_mw):
        """Bám mục tiêu: xả đang cao hơn mục tiêu nhiều -> siết mạnh; gần -> nới."""
        gap = cur_mw - target_mw     # >0: đang tốn hơn mục tiêu -> cần tiết kiệm
        if target_mw <= 10000:       # chế độ tiết kiệm tối đa
            return {"cpu_throttle_max": 0.35, "brightness_act": 0.35,
                    "defer_tasks": 1.0, "gpu_switch": 0.0, "refresh_mode": 0.0,
                    "wifi_power_save": 1.0, "charge_limit_on": 0.0}
        if target_mw >= 35000:       # hiệu năng
            return {"cpu_throttle_max": 0.95, "brightness_act": 0.85,
                    "defer_tasks": 0.0, "gpu_switch": 1.0, "refresh_mode": 2.0,
                    "wifi_power_save": 0.0, "charge_limit_on": 0.0}
        # cân bằng: điều chỉnh throttle theo khoảng cách mục tiêu
        if gap > 8000:
            throttle = 0.5
        elif gap > 0:
            throttle = 0.65
        else:
            throttle = 0.8
        return {"cpu_throttle_max": throttle, "brightness_act": 0.6,
                "defer_tasks": 1.0 if gap > 0 else 0.0,
                "gpu_switch": 0.0, "refresh_mode": 1.0,
                "wifi_power_save": 1.0 if gap > 0 else 0.0, "charge_limit_on": 0.0}


if __name__ == "__main__":
    print("BatteryClaw 4.3 — Worker self-test")
    w = Worker()   # rule-based (chưa có policy)
    state = np.zeros(15, dtype=np.float32)

    # tiết kiệm tối đa
    a = w.act(state, target_discharge_mw=9000, cur_discharge_mw=20000)
    print("  save_max:", a)
    assert a["gpu_switch"] == 0.0 and a["cpu_throttle_max"] <= 0.4

    # hiệu năng
    a = w.act(state, target_discharge_mw=40000, cur_discharge_mw=30000)
    assert a["cpu_throttle_max"] >= 0.9 and a["gpu_switch"] == 1.0

    # cân bằng, đang xả cao hơn mục tiêu -> siết
    a = w.act(state, target_discharge_mw=18000, cur_discharge_mw=30000)
    print("  balanced (xả cao):", a["cpu_throttle_max"], "defer", a["defer_tasks"])
    assert a["cpu_throttle_max"] <= 0.65 and a["defer_tasks"] == 1.0

    # với policy giả (trả toàn 0 -> giữa thang)
    w2 = Worker(policy=lambda obs: np.zeros(7, dtype=np.float32))
    a = w2.act(state, 18000, 18000)
    assert set(a.keys()) >= {"cpu_throttle_max", "gpu_switch", "refresh_mode"}
    # obs phải là 16 chiều (15 + mục tiêu)
    obs16 = w2._augment(state, 18000)
    assert obs16.shape == (16,)
    print("  goal-conditioned obs:", obs16.shape)
    print("PASS ✓")
