"""
BatteryClaw — advanced/planning/mpc_planner.py  (PHASE 4 — mục 4.4)

Model-Based Planning: trước khi thực thi, MÔ PHỎNG vài bước tới "trong đầu"
bằng world model (Phase 2), rồi chọn chuỗi hành động cho tổng reward cao nhất.

Trả lời được câu: "nếu tắt dGPU ngay bây giờ, vài bước nữa pin/độ mượt ra sao?
có đáng không?"

Dùng random-shooting MPC (một dạng MCTS đơn giản, không cây):
  • Sinh K chuỗi action ngẫu nhiên dài H bước.
  • Với mỗi chuỗi: dùng world model rollout, cộng reward (reward.py).
  • Chọn chuỗi tốt nhất, trả action ĐẦU TIÊN của nó (receding horizon).

Phụ thuộc: world model (callable s,a->s') + hàm reward. Cả hai truyền vào,
nên planner không bị buộc vào file cụ thể -> dễ test.
"""

import os
import sys

import numpy as np

# [FIND-03] hang so chuan hoa dung chung tu commons/constants.py (single source).
try:
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "commons"))
    from constants import DISCHARGE_MAX_MW
except Exception:
    DISCHARGE_MAX_MW = 80000.0


class MPCPlanner:
    def __init__(self, world_model_fn, reward_fn,
                 horizon=5, n_candidates=64, action_dim=7, seed=0):
        """
        world_model_fn(state_vec15, action_vec7) -> next_state_vec15
        reward_fn(state_dict) -> float
        horizon: số bước mô phỏng tới (phase.txt gợi ý ~5)
        n_candidates: số chuỗi action thử
        """
        self.wm = world_model_fn
        self.reward_fn = reward_fn
        self.H = horizon
        self.K = n_candidates
        self.action_dim = action_dim
        self.rng = np.random.default_rng(seed)

    def _sample_action(self):
        """Sinh action thô trong [-1,1] (sẽ rời rạc hóa khi tính reward)."""
        return self.rng.uniform(-1, 1, self.action_dim).astype(np.float32)

    def _action_to_reward_row(self, state_vec, action_vec):
        """Dựng row cho reward_fn từ state vector + action thô."""
        sc = lambda x, lo, hi: lo + (x + 1) / 2 * (hi - lo)
        wl = int(round(float(state_vec[3]) * 4))
        gpu_switch = 0 if sc(action_vec[3], 0, 1) < 0.5 else 1
        return {
            "workload_id": wl,
            "discharge_mw": float(state_vec[9] * DISCHARGE_MAX_MW),
            "cpu_throttle_max": float(np.clip(sc(action_vec[0], 0.2, 1.0), 0.2, 1.0)),
            "gpu_switch": gpu_switch,
            "is_game": 1 if wl == 4 else 0,
            "plugged": 0,
            "charge_limit_on": float(sc(action_vec[6], 0, 1) > 0.5),
            "battery_pct": float(state_vec[0]),
        }

    def plan(self, state_vec15):
        """Trả (action thô tốt nhất cho bước hiện tại, reward kỳ vọng)."""
        best_return = -1e9
        best_first_action = None

        for _ in range(self.K):
            s = np.asarray(state_vec15, dtype=np.float32).copy()
            total = 0.0
            first_action = None
            for t in range(self.H):
                a = self._sample_action()
                if t == 0:
                    first_action = a
                row = self._action_to_reward_row(s, a)
                total += self.reward_fn(row)
                s = np.clip(self.wm(s, a), 0.0, 1.0)
            if total > best_return:
                best_return = total
                best_first_action = first_action

        return best_first_action, best_return


if __name__ == "__main__":
    print("BatteryClaw 4.4 — MPC planner self-test")

    # world model giả: tắt dGPU (action[3]<0) -> discharge (chiều 9) giảm
    def fake_wm(s, a):
        s2 = s.copy()
        if a[3] < 0:                       # ép iGPU
            s2[9] = max(0.0, s2[9] - 0.15)  # discharge giảm
        else:
            s2[9] = min(1.0, s2[9] + 0.05)
        return s2

    # reward: thưởng discharge thấp (đơn giản hóa)
    def fake_reward(row):
        return -row["discharge_mw"] / DISCHARGE_MAX_MW

    state = np.full(15, 0.5, dtype=np.float32)
    state[3] = 0.25   # workload browse (không cần dGPU)
    state[9] = 0.5    # discharge_norm hiện tại

    planner = MPCPlanner(fake_wm, fake_reward, horizon=5, n_candidates=128)
    best_a, exp_ret = planner.plan(state)
    print("  action đầu tốt nhất (gpu dim):", round(float(best_a[3]), 3),
          "| return kỳ vọng:", round(exp_ret, 3))
    # vì tắt dGPU giảm discharge -> planner nên chọn action[3] < 0 (ép iGPU)
    assert best_a[3] < 0, "planner phải ưu tiên tắt dGPU khi nó giảm discharge"
    print("  -> planner chọn TẮT dGPU vì giảm xả (đúng kỳ vọng)")
    print("PASS ✓")
