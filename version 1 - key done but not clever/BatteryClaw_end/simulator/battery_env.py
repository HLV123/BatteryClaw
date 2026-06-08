"""
BatteryClaw — battery_env.py  (PHASE 1)
Gymnasium environment giả lập máy MSI i7-11800H + RTX 3050.
Dùng để train RL agent trên PC có card đồ họa — KHÔNG chạy trực tiếp trên laptop pin.

PHASE 1 — mở rộng so với bản gốc:
  Observation 7 -> 15 chiều (thêm GPU, refresh, wifi, audio, process, ram, time, discharge)
  Action      3 -> 7 chiều  (thêm gpu_switch, refresh_rate, wifi_power_save, charge_limit)
  Mô hình hóa: dGPU ngốn 3-8W nền -> tắt dGPU là đòn bẩy tiết kiệm lớn nhất.

LƯU Ý: các con số power vẫn là ƯỚC TÍNH (simulator). Phase 2 sẽ thay bằng
world-model học từ dữ liệu đo thật. Mục tiêu Phase 1: contract obs/action khớp
hoàn toàn với engine C++ và rl_brain để train + deploy thông suốt.

Thông số thực tế từ máy:
  - Pin design  : 52007 mWh
  - Pin full    : 33026 mWh  (health = 64%)
  - CPU         : i7-11800H, 8 cores, 16 threads, base 2304 MHz
  - dGPU        : RTX 3050 Laptop (idle-on ~3W, full ~35W)
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
import os as _os
import sys as _sys

# [REMAIN-02] Hang so chuan hoa dung chung tu commons/constants.py (single source).
#  Phai khop voi rl_brain de scale obs train == scale obs deploy.
try:
    _sys.path.insert(0, _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "commons"))
    from constants import GPU_POWER_MAX_MW, DISCHARGE_MAX_MW
except Exception:
    GPU_POWER_MAX_MW = 38000.0
    DISCHARGE_MAX_MW = 80000.0


# ── Hằng số vật lý của máy MSI ──────────────────────────────────────────────
# Luu y: BATTERY_FULL_MWH o day chi dung cho SIMULATOR (mo phong may MSI cu the).
#  KHONG dung lam gia tri production — rl_brain tu hoc batt_full tu may that (BUG-05).
BATTERY_FULL_MWH   = 33026
BATTERY_DESIGN_MWH = 52007
CPU_BASE_MHZ       = 2304
STEP_SECONDS       = 10

# Công suất CPU+nền theo workload và mức throttle (mW) — chưa gồm GPU & màn hình
POWER_PROFILE = {
    "idle_100":    3500,  "idle_70":    2800,  "idle_50":    2200,
    "browse_100": 12000,  "browse_70":  8500,  "browse_50":  6000,
    "office_100": 18000,  "office_70": 12000,  "office_50":  8000,
    "compile_100":45000,  "compile_70":30000,  "compile_50": 20000,
    "game_100":   65000,  "game_70":   50000,  "game_50":    40000,
}

WORKLOAD_NAMES = ["idle", "browse", "office", "compile", "game"]

LAG_THRESHOLD = {
    "idle": 20, "browse": 40, "office": 50, "compile": 80, "game": 95,
}

# Workload nào THỰC SỰ cần dGPU. Tắt dGPU ở các workload khác là an toàn.
WORKLOAD_NEEDS_DGPU = {
    "idle": False, "browse": False, "office": False,
    "compile": False, "game": True,
}

# Công suất dGPU (mW)
DGPU_IDLE_ON_MW = 3000     # bật nhưng không tải vẫn tốn ~3W
DGPU_FULL_MW    = 35000    # tải tối đa (game)
IGPU_IDLE_MW    = 200
IGPU_FULL_MW    = 3000

# Màn hình: công suất theo brightness và refresh
SCREEN_BASE_MW       = 8000      # ở 100% brightness, 60Hz
REFRESH_EXTRA_FACTOR = {60: 1.0, 120: 1.12, 144: 1.18, 165: 1.22}

# [BUG-06] refresh_mode (0/1/2) -> Hz. Mode 2 ("max") = tan so cao nhat cua panel.
#  Phai khop ngu nghia voi rl_brain (gui MODE chu khong gui Hz cu the).
#  Panel khac nhau co max khac nhau; mac dinh 144 (panel MSI gaming pho bien),
#  doi PANEL_MAX_HZ neu panel la 60/120/165...
PANEL_MAX_HZ         = 144
REFRESH_MODE_TO_HZ   = {0: 60, 1: 120, 2: PANEL_MAX_HZ}


class BatteryClawEnv(gym.Env):
    """
    Observation (15 giá trị, normalize [0,1]):
        0.  battery_pct        % pin còn lại
        1.  cpu_load_pct       % CPU đang dùng
        2.  cpu_temp_norm      nhiệt độ (0=30C, 1=100C)
        3.  workload_id        loại công việc (0-4, /4)
        4.  brightness_norm    độ sáng màn hình
        5.  throttle_max_norm  throttle max hiện tại
        6.  time_norm          thời gian trong episode
        7.  gpu_type_norm      0=iGPU, 0.5=dGPU, 1=both  (/2)         [P1]
        8.  gpu_power_norm     công suất GPU / 38000mW                [P1]
        9.  discharge_norm     tốc độ xả / 80000mW (ground-truth proxy)[P1]
        10. refresh_norm       (hz-60)/(165-60)                       [P1]
        11. wifi_active        0/1                                    [P1]
        12. audio_active       0/1                                    [P1]
        13. ram_pressure       0..1                                   [P1]
        14. time_of_day_norm   0..1 trong ngày                        [P1]

    Action (7 chiều liên tục, threshold cho phần rời rạc):
        0. cpu_throttle_max   [0.2, 1.0]
        1. brightness         [0.3, 1.0]
        2. defer_tasks        [0,1] -> >0.5
        3. gpu_switch         [0,1] -> <0.5: ép iGPU(tắt dGPU), >=0.5: cho phép dGPU  [P1]
        4. refresh_mode       [0,1] -> 0..0.4:60Hz, 0.4..0.7:120Hz, >0.7:max          [P1]
        5. wifi_power_save     [0,1] -> >0.5 bật                                        [P1]
        6. charge_limit_on     [0,1] -> >0.5 bật giới hạn sạc 80%                       [P1]

    Reward = A*(pin_saved) - B*(lag) - C*(annoyance) + D*(longevity)
    """

    metadata = {"render_modes": ["human"], "render_fps": 1}

    OBS_DIM = 15
    ACT_DIM = 7

    def __init__(self, render_mode=None, A=1.0, B=2.0, C=0.5, D=0.3,
                 episode_steps=360):
        super().__init__()
        self.A = A
        self.B = B
        self.C = C
        self.D = D                      # [P1] trọng số bảo vệ tuổi thọ pin
        self.episode_steps = episode_steps
        self.render_mode   = render_mode

        self.observation_space = spaces.Box(
            low=np.zeros(self.OBS_DIM, dtype=np.float32),
            high=np.ones(self.OBS_DIM, dtype=np.float32),
            dtype=np.float32
        )
        # action lo/hi — 7 chiều
        self.action_space = spaces.Box(
            low =np.array([0.20, 0.30, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([1.00, 1.00, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32),
            dtype=np.float32
        )

        self._init_state()

    # ── khởi tạo state nội bộ ───────────────────────────────────────────────
    def _init_state(self):
        self.battery_mwh     = BATTERY_FULL_MWH * 0.7
        self.cpu_temp        = 40.0
        self.throttle_max    = 1.0
        self.brightness      = 0.99
        self.prev_brightness = 0.99
        self.refresh_hz      = PANEL_MAX_HZ   # màn gaming thường ở tần số cao
        self.dgpu_on         = True        # mặc định dGPU đang bật
        self.wifi_save       = False
        self.charge_limit_on = False
        self.step_count      = 0
        self._last_cpu_load  = 0.1
        self.current_workload = 0
        self._workload_schedule = [0] * self.episode_steps
        self._plugged        = False       # giả lập có lúc cắm sạc

    def _gen_workload_schedule(self, rng):
        weights = [0.20, 0.40, 0.30, 0.08, 0.02]
        schedule = []
        t = 0
        while t < self.episode_steps:
            wl  = int(rng.choice(len(WORKLOAD_NAMES), p=weights))
            dur = int(rng.integers(3, 21))
            for _ in range(min(dur, self.episode_steps - t)):
                schedule.append(wl)
            t += dur
        return schedule[:self.episode_steps]

    # ── thành phần công suất ────────────────────────────────────────────────
    def _cpu_power_mw(self, workload_id, throttle_max, rng):
        wl = WORKLOAD_NAMES[workload_id]
        suffix = "100" if throttle_max >= 0.9 else "70" if throttle_max >= 0.6 else "50"
        base  = POWER_PROFILE.get(f"{wl}_{suffix}", 10000)
        noise = float(rng.uniform(0.9, 1.1))
        return base * noise

    def _gpu_power_mw(self, workload_id):
        """dGPU on/off là đòn bẩy lớn. iGPU luôn có nhưng rẻ."""
        wl = WORKLOAD_NAMES[workload_id]
        load = {"idle": 0.0, "browse": 0.1, "office": 0.15,
                "compile": 0.2, "game": 0.9}[wl]
        if self.dgpu_on:
            return DGPU_IDLE_ON_MW + load * (DGPU_FULL_MW - DGPU_IDLE_ON_MW)
        else:
            # chỉ iGPU gánh -> rẻ hơn nhiều
            return IGPU_IDLE_MW + load * (IGPU_FULL_MW - IGPU_IDLE_MW)

    def _screen_power_mw(self):
        factor = REFRESH_EXTRA_FACTOR.get(self.refresh_hz, 1.0)
        return self.brightness * SCREEN_BASE_MW * factor

    def _wifi_power_mw(self):
        # WiFi ~ 800mW khi hoạt động; power-save giảm còn ~300mW
        return 300.0 if self.wifi_save else 800.0

    def _total_power_mw(self, workload_id, throttle_max, defer, rng):
        p  = self._cpu_power_mw(workload_id, throttle_max, rng)
        p += self._gpu_power_mw(workload_id)
        p += self._screen_power_mw()
        p += self._wifi_power_mw()
        if defer:
            p *= 0.95
        return p

    # ── penalties ───────────────────────────────────────────────────────────
    def _lag_penalty(self, workload_id, throttle_max, forced_igpu):
        threshold = LAG_THRESHOLD[WORKLOAD_NAMES[workload_id]] / 100.0
        pen = 0.0
        if throttle_max < threshold:
            pen += (threshold - throttle_max) / threshold * 5.0
        # phạt NẶNG nếu tắt dGPU đúng lúc game cần -> lag/giật
        if forced_igpu and WORKLOAD_NEEDS_DGPU[WORKLOAD_NAMES[workload_id]]:
            pen += 8.0
        return pen

    def _annoyance_penalty(self, new_brightness):
        delta = abs(new_brightness - self.prev_brightness)
        return (delta - 0.15) * 3.0 if delta > 0.15 else 0.0

    def _update_temp(self, power_mw):
        target = 35.0 + (power_mw / 65000.0) * 60.0
        self.cpu_temp += (target - self.cpu_temp) * 0.15

    # ── observation ─────────────────────────────────────────────────────────
    def _gpu_type_value(self, forced_igpu):
        if not self.dgpu_on or forced_igpu:
            return 0.0          # iGPU only
        return 0.5              # dGPU active (đơn giản hóa; "both" hiếm)

    def _get_obs(self, discharge_mw=0.0, forced_igpu=False):
        gpu_power = self._gpu_power_mw(self.current_workload)
        return np.array([
            self.battery_mwh / BATTERY_FULL_MWH,
            self._last_cpu_load,
            float(np.clip((self.cpu_temp - 30.0) / 70.0, 0.0, 1.0)),
            self.current_workload / 4.0,
            self.brightness,
            self.throttle_max,
            self.step_count / self.episode_steps,
            # ── Phase 1 ──
            self._gpu_type_value(forced_igpu) / 1.0,        # 0 hoặc 0.5
            float(np.clip(gpu_power / GPU_POWER_MAX_MW, 0.0, 1.0)),
            float(np.clip(discharge_mw / DISCHARGE_MAX_MW, 0.0, 1.0)),
            float(np.clip((self.refresh_hz - 60) / (165 - 60), 0.0, 1.0)),
            1.0,                                            # wifi_active (giả lập luôn bật)
            float(self.current_workload in (1, 4)),         # audio_active ~ browse/game
            float(np.clip(0.4 + self._last_cpu_load * 0.4, 0.0, 1.0)),  # ram_pressure proxy
            float((self.step_count * STEP_SECONDS % 86400) / 86400.0),  # time_of_day
        ], dtype=np.float32)

    # ── gym API ─────────────────────────────────────────────────────────────
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._init_state()
        self.battery_mwh = float(self.np_random.uniform(0.4, 0.9)) * BATTERY_FULL_MWH
        self._workload_schedule = self._gen_workload_schedule(self.np_random)
        self.current_workload   = self._workload_schedule[0]
        return self._get_obs(), {}

    def step(self, action):
        # ── giải mã action 7 chiều ──────────────────────────────
        new_throttle   = float(np.clip(action[0], 0.20, 1.00))
        new_brightness = float(np.clip(action[1], 0.30, 1.00))
        defer_tasks    = bool(action[2] > 0.5)
        force_igpu     = bool(action[3] < 0.5)     # <0.5 = ép iGPU (tắt dGPU)
        refresh_a      = float(action[4])
        wifi_save      = bool(action[5] > 0.5)
        charge_lim     = bool(action[6] > 0.5)

        # áp refresh mode (0=60, 1=120, 2=max của panel) — khớp rl_brain
        if   refresh_a <= 0.4: self.refresh_hz = REFRESH_MODE_TO_HZ[0]
        elif refresh_a <= 0.7: self.refresh_hz = REFRESH_MODE_TO_HZ[1]
        else:                  self.refresh_hz = REFRESH_MODE_TO_HZ[2]

        annoyance            = self._annoyance_penalty(new_brightness)
        self.throttle_max    = new_throttle
        self.brightness      = new_brightness
        self.prev_brightness = new_brightness
        self.wifi_save       = wifi_save
        self.charge_limit_on = charge_lim

        # workload hiện tại
        self.current_workload = self._workload_schedule[
            min(self.step_count, len(self._workload_schedule) - 1)
        ]
        needs_dgpu = WORKLOAD_NEEDS_DGPU[WORKLOAD_NAMES[self.current_workload]]

        # quyết định dGPU: chỉ tắt khi action ép VÀ workload không cần
        # (mô phỏng lớp bảo vệ canDisableDgpu trong engine C++)
        if force_igpu and not needs_dgpu:
            self.dgpu_on = False
        elif force_igpu and needs_dgpu:
            self.dgpu_on = True            # guard chặn: không tắt khi game
        else:
            self.dgpu_on = True

        # CPU load
        intensity = [0.05, 0.25, 0.45, 0.85, 0.95]
        noise_cpu = float(self.np_random.uniform(-0.05, 0.05))
        self._last_cpu_load = float(np.clip(
            self.throttle_max * intensity[self.current_workload] + noise_cpu, 0.0, 1.0))

        # công suất & tiêu thụ
        power_mw     = self._total_power_mw(
            self.current_workload, self.throttle_max, defer_tasks, self.np_random)
        mwh_consumed = power_mw * (STEP_SECONDS / 3600.0)
        baseline_mwh = self._baseline_mwh(self.current_workload)
        pin_saved    = max(0.0, baseline_mwh - mwh_consumed)

        self.battery_mwh = max(0.0, self.battery_mwh - mwh_consumed)
        self._update_temp(power_mw)

        lag_penalty = self._lag_penalty(
            self.current_workload, self.throttle_max, force_igpu)

        # [P1] phần thưởng bảo vệ tuổi thọ: bật charge limit khi đang "cắm sạc"
        longevity = 0.0
        if charge_lim and self.battery_mwh / BATTERY_FULL_MWH > 0.8:
            longevity = 1.0

        reward = (
            self.A * (pin_saved / 10.0)
          - self.B * lag_penalty
          - self.C * annoyance
          + self.D * longevity
        )

        self.step_count += 1
        terminated = self.battery_mwh <= 0.0
        truncated  = self.step_count >= self.episode_steps
        if truncated and not terminated:
            reward += (self.battery_mwh / BATTERY_FULL_MWH) * 10.0

        # discharge_mw cho observation (ground-truth proxy trong sim)
        discharge_mw = power_mw

        info = {
            "battery_pct" : self.battery_mwh / BATTERY_FULL_MWH * 100,
            "power_mw"    : power_mw,
            "gpu_power_mw": self._gpu_power_mw(self.current_workload),
            "dgpu_on"     : self.dgpu_on,
            "refresh_hz"  : self.refresh_hz,
            "workload"    : WORKLOAD_NAMES[self.current_workload],
            "lag_penalty" : lag_penalty,
            "annoyance"   : annoyance,
            "longevity"   : longevity,
            "cpu_temp"    : self.cpu_temp,
            "throttle_max": self.throttle_max * 100,
            "brightness"  : self.brightness * 100,
        }

        if self.render_mode == "human":
            print(f"  Step {self.step_count:3d} | "
                  f"Batt:{info['battery_pct']:5.1f}% | "
                  f"Thr:{info['throttle_max']:5.1f}% | "
                  f"Br:{info['brightness']:5.0f}% | "
                  f"dGPU:{'ON ' if self.dgpu_on else 'off'} | "
                  f"{self.refresh_hz}Hz | "
                  f"WL:{info['workload']:7s} | "
                  f"Pwr:{power_mw:6.0f}mW | R:{reward:+.2f}")

        return self._get_obs(discharge_mw, force_igpu), reward, terminated, truncated, info

    def render(self):
        if self.render_mode == "human":
            print(f"  [render] Batt:{self.battery_mwh/BATTERY_FULL_MWH*100:.1f}% | "
                  f"dGPU:{'ON' if self.dgpu_on else 'off'} | "
                  f"WL:{WORKLOAD_NAMES[self.current_workload]}")
        return None

    def _baseline_mwh(self, workload_id):
        """Baseline KHÔNG có BatteryClaw: throttle=100%, bright=99%, dGPU luôn bật, 144Hz."""
        base   = POWER_PROFILE.get(f"{WORKLOAD_NAMES[workload_id]}_100", 10000)
        gpu    = DGPU_IDLE_ON_MW + {"idle":0,"browse":0.1,"office":0.15,
                                    "compile":0.2,"game":0.9}[WORKLOAD_NAMES[workload_id]] \
                                   * (DGPU_FULL_MW - DGPU_IDLE_ON_MW)
        screen = 0.99 * SCREEN_BASE_MW * REFRESH_EXTRA_FACTOR[144]
        wifi   = 800.0
        return (base + gpu + screen + wifi) * (STEP_SECONDS / 3600.0)


if __name__ == "__main__":
    from gymnasium.utils.env_checker import check_env
    import time

    print("BatteryClaw Phase 1 — Kiểm tra môi trường Gymnasium")
    print("=" * 60)

    env = BatteryClawEnv(render_mode="human")

    print(f"[1] obs_dim={env.OBS_DIM}, act_dim={env.ACT_DIM}")
    print("[2] Chạy env_checker...")
    check_env(env)
    print("    env_checker: PASS\n")

    print("[3] Random policy test (20 steps)...")
    obs, _ = env.reset(seed=42)
    assert obs.shape == (env.OBS_DIM,), f"obs shape sai: {obs.shape}"
    total_reward = 0.0
    t0 = time.time()
    for i in range(20):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        if terminated or truncated:
            obs, _ = env.reset()
    elapsed = time.time() - t0
    print(f"\n    Total reward (random): {total_reward:.3f}")
    print(f"    Speed: {20/elapsed:.0f} steps/sec")
    print("\nMôi trường Phase 1 sẵn sàng để train!")
