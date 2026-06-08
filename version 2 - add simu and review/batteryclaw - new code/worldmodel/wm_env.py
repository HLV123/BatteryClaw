"""
BatteryClaw — wm_env.py  (PHASE 2 — kết nối 2.2 + 2.3)

Gymnasium env BỌC quanh world model đã học (world_model.pt) thay cho simulator
viết tay. Điểm khác cốt lõi so với battery_env.py (Phase 1):
  • Chuyển trạng thái next_state = WorldModel(state, action)  ← học từ data thật
  • Reward = reward.compute_reward(...)                       ← công thức thật 2.3

Nhờ vậy policy được train trên ĐỘNG HỌC THẬT của máy, không phải số ước tính.
Đây chính là "Simulator Thực" mà Phase 2 hướng tới.

Dùng để train:
  python train_on_wm.py   (xem file kèm) — hoặc nạp env này vào SB3 PPO/SAC.
"""

import os
import sys

import numpy as np
import gymnasium as gym
from gymnasium import spaces

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datacollector"))

from schema import STATE_COLUMNS, ACTION_COLUMNS
from reward import compute_reward, RewardWeights

# [MINOR-B] denorm discharge dung hang so chung (single source).
try:
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "commons"))
    from constants import DISCHARGE_MAX_MW
except Exception:
    DISCHARGE_MAX_MW = 80000.0

STATE_DIM  = len(STATE_COLUMNS)   # 15
ACTION_DIM = len(ACTION_COLUMNS)  # 7


class WorldModelEnv(gym.Env):
    """Env dùng world model học được làm hàm chuyển trạng thái.

    Observation: 15 chiều (giống Phase 1, đã chuẩn hóa [0,1]).
    Action: 7 chiều liên tục (giống Phase 1).
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, model_path="models/world_model.pt",
                 weights: RewardWeights = None, episode_steps=360,
                 render_mode=None):
        super().__init__()
        import torch
        from world_model import build_model

        self.model = build_model()
        self.model.load_state_dict(torch.load(model_path))
        self.model.eval()
        self.torch = torch

        self.weights = weights or RewardWeights()
        self.episode_steps = episode_steps
        self.render_mode = render_mode

        self.observation_space = spaces.Box(
            low=np.zeros(STATE_DIM, dtype=np.float32),
            high=np.ones(STATE_DIM, dtype=np.float32), dtype=np.float32)
        self.action_space = spaces.Box(
            low =np.array([0.20, 0.30, 0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([1.00, 1.00, 1, 1, 1, 1, 1], dtype=np.float32),
            dtype=np.float32)

        self.state = None
        self.step_count = 0

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # khởi tạo state ngẫu nhiên hợp lý
        s = self.np_random.uniform(0, 1, STATE_DIM).astype(np.float32)
        s[0] = self.np_random.uniform(0.4, 0.9)   # battery_pct
        self.state = s
        self.step_count = 0
        return self.state.copy(), {}

    def _action_for_model(self, action):
        """Chuẩn hóa action giống lúc train world model (gpu/refresh /2)."""
        a = np.array(action, dtype=np.float32).copy()
        # rời rạc hóa các chiều quyết định để khớp dữ liệu thu thập
        gpu_switch   = 0.0 if a[3] < 0.5 else 1.0
        refresh_mode = 0.0 if a[4] <= 0.4 else (1.0 if a[4] <= 0.7 else 2.0)
        a_model = a.copy()
        a_model[3] = gpu_switch / 2.0
        a_model[4] = refresh_mode / 2.0
        return a_model, gpu_switch, refresh_mode

    def step(self, action):
        a_model, gpu_switch, refresh_mode = self._action_for_model(action)

        with self.torch.no_grad():
            s_t = self.torch.tensor(self.state.reshape(1, -1))
            a_t = self.torch.tensor(a_model.reshape(1, -1))
            next_state = self.model(s_t, a_t).numpy()[0]
        next_state = np.clip(next_state, 0.0, 1.0).astype(np.float32)

        # dựng "row" để tính reward thật (2.3)
        wl_id = int(round(self.state[3] * 4))          # workload_id (0..4)
        discharge_mw = float(next_state[9] * DISCHARGE_MAX_MW)  # discharge_norm -> mW
        row = {
            "workload_id"     : wl_id,
            "discharge_mw"    : discharge_mw,
            "cpu_throttle_max": float(np.clip(action[0], 0.2, 1.0)),
            "gpu_switch"      : gpu_switch,
            "is_game"         : 1.0 if wl_id == 4 else 0.0,
            "plugged"         : 0.0,
            "charge_limit_on" : float(action[6] > 0.5),
            "battery_pct"     : float(next_state[0]),
        }
        reward, parts = compute_reward(row, self.weights)

        self.state = next_state
        self.step_count += 1
        terminated = bool(next_state[0] <= 0.02)        # gần hết pin
        truncated  = self.step_count >= self.episode_steps

        info = {"discharge_mw": discharge_mw, "gpu_switch": gpu_switch,
                "refresh_mode": refresh_mode, **parts}

        if self.render_mode == "human":
            print(f"  step {self.step_count:3d} | batt={next_state[0]*100:5.1f}% "
                  f"| disch={discharge_mw:6.0f}mW | gpu_sw={int(gpu_switch)} "
                  f"| R={reward:+.3f}")

        return self.state.copy(), float(reward), terminated, truncated, info

    def render(self):
        if self.render_mode == "human" and self.state is not None:
            print(f"  [render] batt={self.state[0]*100:.1f}% "
                  f"discharge_norm={self.state[9]:.3f}")
        return None


if __name__ == "__main__":
    from gymnasium.utils.env_checker import check_env
    print("BatteryClaw Phase 2 — WorldModelEnv test")
    mp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "models", "world_model.pt")
    if not os.path.exists(mp):
        print(f"Chưa có {mp}. Hãy chạy world_model.py trước.")
        sys.exit(0)

    env = WorldModelEnv(model_path=mp, render_mode="human")
    check_env(env)
    print("env_checker: PASS\n")
    obs, _ = env.reset(seed=1)
    total = 0.0
    for _ in range(15):
        a = env.action_space.sample()
        obs, r, term, trunc, info = env.step(a)
        total += r
        if term or trunc:
            break
    print(f"\nTotal reward (random, world-model rollout): {total:.3f}")
