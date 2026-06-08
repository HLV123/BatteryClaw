"""
BatteryClaw — battery_env.py  (SIMULATOR NANG CAP)

Moi truong gia lap pin phong phu de train policy manh. Giu nguyen contract
Phase 1: observation 15 chieu, action 7 chieu, cung thu tu voi rl_brain.state_to_obs.

So voi ban cu, ban nay them RAT NHIEU yeu to thuc te:
  - 12 loai workload (idle, web nhe, web nang, office, video call, xem phim,
    nghe nhac, code/IDE, compile, render, game nhe, game nang).
  - Da dang PHAN CUNG: moi episode boc 1 "may" khac (pin, do chai, co/khong dGPU,
    cpu base, panel 60/120/144Hz).
  - Mo hinh SAC that: cam/rut sac ngau nhien, sac lam pin tang + nong them,
    charge limit 80% bao ve tuoi tho.
  - NHIET DO dong: phu thuoc cong suat + nhiet do phong (18-38C), thermal throttle.
  - MANG & AUDIO that theo workload; RAM pressure that.
  - Chu ky NGAY/DEM: gio anh huong loai workload hay gap.
  - Ca tinh nguoi dung: do nhay cam giat / nhay cam man toi khac nhau moi episode.
  - Su kien ngau nhien: cam/rut sac bat ngo.
"""

import os as _os
import sys as _sys

import numpy as np
import gymnasium as gym
from gymnasium import spaces

try:
    _sys.path.insert(0, _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "commons"))
    from constants import GPU_POWER_MAX_MW, DISCHARGE_MAX_MW
except Exception:
    GPU_POWER_MAX_MW = 38000.0
    DISCHARGE_MAX_MW = 80000.0

STEP_SECONDS = 10

# [F1] Action delay: so step tre truoc khi action co hieu luc (1 step = 10s -> 2 step = 20s)
ACTION_DELAY = 2
# [F2] Spike workload: xac suat moi step kich hoat tac vu ngam, va do dai/cuong do
SPIKE_PROB     = 0.02     # ~2%/step
SPIKE_DUR_MIN  = 3        # 30s
SPIKE_DUR_MAX  = 12       # 120s
SPIKE_CPU_ADD  = 0.55     # cong them vao tai CPU khi spike

PANEL_MAX_HZ       = 144
REFRESH_MODE_TO_HZ = {0: 60, 1: 120, 2: PANEL_MAX_HZ}
REFRESH_EXTRA_FACTOR = {60: 1.00, 120: 1.12, 144: 1.18}

# 12 workload: (name, cpu, gpu, needs_dgpu, lag_tol, wifi, audio, ram)
WORKLOADS = [
    ("idle",         0.04, 0.00, False, 0.20, 0.05, 0.0, 0.20),
    ("web_light",    0.18, 0.05, False, 0.40, 0.30, 0.0, 0.35),
    ("web_heavy",    0.40, 0.15, False, 0.50, 0.55, 0.2, 0.60),
    ("office",       0.45, 0.05, False, 0.50, 0.25, 0.0, 0.50),
    ("video_call",   0.55, 0.25, False, 0.55, 0.90, 1.0, 0.65),
    ("video_play",   0.30, 0.30, False, 0.45, 0.70, 1.0, 0.45),
    ("music",        0.12, 0.02, False, 0.30, 0.40, 1.0, 0.30),
    ("code_ide",     0.50, 0.10, False, 0.60, 0.30, 0.0, 0.70),
    ("compile",      0.92, 0.15, False, 0.85, 0.20, 0.0, 0.85),
    ("render",       0.85, 0.95, True,  0.80, 0.15, 0.0, 0.90),
    ("game_light",   0.60, 0.65, True,  0.75, 0.30, 1.0, 0.70),
    ("game_heavy",   0.95, 0.98, True,  0.95, 0.40, 1.0, 0.85),
]
WORKLOAD_NAMES = [w[0] for w in WORKLOADS]
N_WL = len(WORKLOADS)

WL_TO_GROUP = {
    "idle":0, "web_light":1, "music":1, "web_heavy":1,
    "office":2, "video_call":2, "video_play":2,
    "code_ide":3, "compile":3,
    "render":4, "game_light":4, "game_heavy":4,
}

def _wl_weights_by_hour(hour):
    w = np.ones(N_WL)
    idx = {n:i for i,n in enumerate(WORKLOAD_NAMES)}
    if 8 <= hour < 18:
        for n in ("office","code_ide","compile","web_heavy","video_call"): w[idx[n]] *= 3
    elif 18 <= hour < 24:
        for n in ("game_heavy","game_light","video_play","music","web_light"): w[idx[n]] *= 3
    else:
        for n in ("idle","music","web_light","video_play"): w[idx[n]] *= 3
    return w / w.sum()

# [F5] Lich trinh sac theo THOI QUEN (khong ngau nhien thuan). Moi profile tra ve
#  may CO cam sac o gio do khong -> ket hop chu ky ngay/dem giup AI doan truoc:
#  "10h sang thuong dang sac -> bat charge limit som".
CHARGE_PROFILES = {
    # dan van phong: cam sac gio hanh chinh (8-18h) + toi o nha (20-24h), rut khi di lai
    "office":  lambda h: (8 <= h < 12) or (13 <= h < 18) or (20 <= h < 24),
    # sinh vien / di chuyen nhieu: chi cam dem muon (23-7h), ban ngay chay pin
    "student": lambda h: (h >= 23 or h < 7),
    # lam viec tu do: cam that thuong, phan lon chieu toi
    "freelance": lambda h: (15 <= h < 23),
    # luon cam (may ban / dung co dinh)
    "desktop": lambda h: True,
}
CHARGE_PROFILE_NAMES = list(CHARGE_PROFILES.keys())

# (full mWh, dgpu, cpu_base mW, dgpu_full mW, panel Hz, screen_base mW)
# (full mWh, dgpu, cpu_base mW, dgpu_full mW, panel Hz, screen_base mW, heat, cool)
#  [F6] heat = toc do nong len (may mong cao), cool = he so tan nhiet (may day cao).
#   Temp_{t+1} = Temp_t + (target - Temp_t)*heat - cool*(Temp_t - room) ... (xem _update_temp)
MACHINE_TYPES = [
    dict(full=45000, dgpu=False, cpu_base=2500, dgpu_full=0,     panel=60,  screen=6000, heat=0.32, cool=0.05),  # ultrabook mong: nong gat, tan kem
    dict(full=54000, dgpu=False, cpu_base=3000, dgpu_full=0,     panel=60,  screen=7000, heat=0.24, cool=0.07),  # vp mong vua
    dict(full=50000, dgpu=True,  cpu_base=3200, dgpu_full=18000, panel=120, screen=7500, heat=0.20, cool=0.09),
    dict(full=52000, dgpu=True,  cpu_base=3500, dgpu_full=35000, panel=144, screen=8000, heat=0.16, cool=0.11),  # gaming: nong cham, tan tot
    dict(full=62000, dgpu=True,  cpu_base=4000, dgpu_full=55000, panel=144, screen=9000, heat=0.14, cool=0.13),  # gaming day: tan rat tot (panel 144 khop PANEL_MAX_HZ, tranh dead zone obs[10])
    dict(full=38000, dgpu=True,  cpu_base=3300, dgpu_full=30000, panel=60,  screen=7000, heat=0.22, cool=0.08),  # may cu
]


class BatteryClawEnv(gym.Env):
    metadata = {"render_modes": ["human"]}
    OBS_DIM = 15
    ACT_DIM = 7

    def __init__(self, render_mode=None, A=1.0, B=2.0, C=0.5, D=0.4,
                 episode_steps=180, randomize=True, difficulty=3, force_profile=None):
        super().__init__()
        self.A, self.B, self.C, self.D = A, B, C, D
        self.episode_steps = episode_steps
        self.render_mode   = render_mode
        self.randomize     = randomize
        self.difficulty = difficulty
        # [1.1] force_profile: neu dat ("battery_saver"/"balanced"/"performance"),
        #  MOI episode dung dung profile do (de train 3 model rieng cho 3 che do UI),
        #  thay vi boc ngau nhien 3 profile (chinh sach thoa hiep).
        self.force_profile = force_profile

        self.observation_space = spaces.Box(
            low=np.zeros(self.OBS_DIM, dtype=np.float32),
            high=np.ones(self.OBS_DIM, dtype=np.float32), dtype=np.float32)
        self.action_space = spaces.Box(
            low =np.array([0.20, 0.30, 0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([1.00, 1.00, 1, 1, 1, 1, 1], dtype=np.float32),
            dtype=np.float32)

        self._init_machine(np.random.default_rng())
        self._init_state()

    def _init_machine(self, rng):
        # [F4] difficulty 1: may co dinh ultrabook (de nhat, giong ban goc don gian)
        if self.difficulty <= 1:
            m = MACHINE_TYPES[0]
        elif self.randomize:
            m = MACHINE_TYPES[int(rng.integers(len(MACHINE_TYPES)))]
        else:
            m = MACHINE_TYPES[3]
        self.m_full      = m["full"]
        self.has_dgpu    = m["dgpu"]
        self.cpu_base_mw = m["cpu_base"]
        self.dgpu_full   = m["dgpu_full"]
        self.panel_hz    = m["panel"]
        self.screen_base = m["screen"]
        self.heat_rate   = m["heat"]   # [F6] toc do nong len
        self.cool_rate   = m["cool"]   # [F6] he so tan nhiet
        if self.difficulty <= 1:
            # de: pin tot, phong mat, nguoi dung de tinh, gio co dinh
            self.health = 0.95; self.room_temp = 24.0
            self.user_lag_sens = 1.0; self.user_dark_sens = 1.0
            self.start_hour = 14
            self.reward_profile = "balanced"
            self.rw_save = 1.0; self.rw_lag = 1.0
        else:
            self.health      = float(rng.uniform(0.60, 1.00)) if self.randomize else 0.85
            # [F8] difficulty 4 (stress test): ep pin chai nang hon de mai sac policy
            if self.difficulty >= 4 and self.randomize:
                self.health = float(rng.uniform(0.62, 0.85))
            self.room_temp   = float(rng.uniform(18, 38)) if self.randomize else 26.0
            self.start_hour  = int(rng.integers(0, 24)) if self.randomize else 14
            # [F7] Bốc reward profile, GẮN CHẶT voi do nhay nguoi dung de AI suy ra
            #  profile qua tin hieu no THAY (do nhay giat), tranh tin hieu mau thuan.
            #  - battery_saver: thuong tiet kiem x2, phat giat x0.5  <-> nguoi IT nhay giat
            #  - performance  : thuong tiet kiem x0.5, phat giat x3  <-> nguoi RAT nhay giat
            #  - balanced     : giu nguyen                           <-> trung binh
            if self.force_profile in ("battery_saver","balanced","performance"):
                self.reward_profile = self.force_profile   # [1.1] ep 1 profile co dinh
            elif self.randomize:
                self.reward_profile = ("battery_saver","balanced","performance")[
                    int(rng.integers(3))]
            else:
                self.reward_profile = "balanced"
            if self.reward_profile == "battery_saver":
                self.rw_save = 2.0; self.rw_lag = 0.5
                self.user_lag_sens  = float(rng.uniform(0.6, 0.9))   # it nhay giat
                self.user_dark_sens = float(rng.uniform(0.4, 0.8))
            elif self.reward_profile == "performance":
                self.rw_save = 0.5; self.rw_lag = 3.0
                self.user_lag_sens  = float(rng.uniform(1.4, 1.8))   # rat nhay giat
                self.user_dark_sens = float(rng.uniform(1.1, 1.5))
            else:  # balanced
                self.rw_save = 1.0; self.rw_lag = 1.0
                self.user_lag_sens  = float(rng.uniform(0.9, 1.2))
                self.user_dark_sens = float(rng.uniform(0.8, 1.2))
        self.full_mwh    = self.m_full * self.health
        # [F5] bốc thói quen sạc cho episode này
        if self.difficulty <= 1:
            self.charge_profile = "desktop"     # de: luon co dien
        elif self.randomize:
            self.charge_profile = CHARGE_PROFILE_NAMES[
                int(rng.integers(len(CHARGE_PROFILE_NAMES)))]
        else:
            self.charge_profile = "office"

    def _init_state(self):
        self.battery_mwh     = self.full_mwh * 0.7
        self.cpu_temp        = self.room_temp + 8.0
        self.throttle_max    = 1.0
        self.brightness      = 0.9
        self.prev_brightness = 0.9
        self.refresh_hz      = self.panel_hz
        self.dgpu_on         = self.has_dgpu
        self.wifi_save       = False
        self.charge_limit_on = False
        self.step_count      = 0
        self._last_cpu_load  = 0.1
        self.cur_wl          = 0
        self.plugged         = False
        self._wl_schedule    = [0] * self.episode_steps
        # [F1] Action delay: lenh AI gui bi tre ACTION_DELAY step moi co hieu luc
        #  (mo phong HDH can ~1-2s thuc thi). Hang doi chua cac action cho ap dung.
        self._action_queue   = []
        # [F2] Spike workload: tac vu ngam (Update/Antivirus/OneDrive) vot CPU bat ngo
        self._spike_left     = 0     # so step con lai cua spike hien tai
        self._spike_cpu      = 0.0   # luong CPU cong them khi spike

    def _gen_schedule(self, rng):
        sched = []; t = 0
        while t < self.episode_steps:
            hour = (self.start_hour + (t * STEP_SECONDS) // 3600) % 24
            wl = int(rng.choice(N_WL, p=_wl_weights_by_hour(hour)))
            dur = int(rng.integers(3, 15))
            for _ in range(min(dur, self.episode_steps - t)):
                sched.append(wl)
            t += dur
        return sched[:self.episode_steps]

    def _cpu_power(self, wl_i, throttle, rng):
        cpu = WORKLOADS[wl_i][1]
        load = float(np.clip(cpu * throttle + float(rng.uniform(-0.03, 0.03)), 0, 1))
        dyn = (self.cpu_base_mw * 14.0) * (load ** 1.5)
        return self.cpu_base_mw + dyn, load

    def _gpu_power(self, wl_i):
        gpu = WORKLOADS[wl_i][2]
        if self.dgpu_on and self.has_dgpu:
            return 2500 + gpu * (self.dgpu_full - 2500)
        return 200 + gpu * 2800

    def _screen_power(self):
        return self.brightness * self.screen_base * REFRESH_EXTRA_FACTOR.get(self.refresh_hz, 1.0)

    def _wifi_power(self, wl_i):
        use = WORKLOADS[wl_i][5]
        if self.wifi_save: use *= 0.4
        return 150 + use * 1200

    def _misc_power(self, wl_i):
        return 300 + WORKLOADS[wl_i][6] * 400

    def _total_power(self, wl_i, throttle, defer, rng):
        cpu, load = self._cpu_power(wl_i, throttle, rng)
        if defer: cpu *= 0.92
        p = cpu + self._gpu_power(wl_i) + self._screen_power() \
            + self._wifi_power(wl_i) + self._misc_power(wl_i)
        return p, load

    def _update_temp(self, power_mw):
        # [F6] Quan tinh nhiet theo dong may: may mong nong nhanh (heat cao), tan
        #  cham (cool thap); may gaming day nguoc lai. Mo hinh nhiet bac 1:
        #    Temp += (target - Temp) * heat_rate  - cool_rate * (Temp - room)
        #  -> AI hoc "tren ultrabook phai ha xung som, dung doi cham nguong throttle".
        target = self.room_temp + power_mw / 1100.0
        if self.plugged:
            target += 4.0
        self.cpu_temp += (target - self.cpu_temp) * self.heat_rate \
                         - self.cool_rate * (self.cpu_temp - self.room_temp)

    def _get_obs(self, discharge_mw=0.0):
        wl_i = self.cur_wl
        gpu_power = self._gpu_power(wl_i)
        group = WL_TO_GROUP[WORKLOAD_NAMES[wl_i]]
        hour = (self.start_hour + (self.step_count * STEP_SECONDS) // 3600) % 24
        gpu_type = 0.5 if (self.dgpu_on and self.has_dgpu) else 0.0
        return np.array([
            self.battery_mwh / self.full_mwh,
            self._last_cpu_load,
            float(np.clip((self.cpu_temp - 30.0) / 70.0, 0, 1)),
            group / 4.0,
            self.brightness,
            self.throttle_max,
            self.step_count / self.episode_steps,
            gpu_type,
            float(np.clip(gpu_power / GPU_POWER_MAX_MW, 0, 1)),
            float(np.clip(discharge_mw / DISCHARGE_MAX_MW, 0, 1)),
            float(np.clip((self.refresh_hz - 60) / (PANEL_MAX_HZ - 60), 0, 1)),
            1.0 if WORKLOADS[wl_i][5] > 0.1 else 0.5,
            float(WORKLOADS[wl_i][6]),
            float(np.clip(WORKLOADS[wl_i][7], 0, 1)),
            (hour * 3600 + (self.step_count * STEP_SECONDS) % 3600) / 86400.0,
        ], dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if self.randomize:
            self._init_machine(self.np_random)
        self._init_state()
        self.battery_mwh = float(self.np_random.uniform(0.30, 0.95)) * self.full_mwh
        # [F5] trang thai sac ban dau theo profile + gio bat dau
        if self.difficulty >= 2:
            self.plugged = bool(CHARGE_PROFILES[self.charge_profile](self.start_hour))
        else:
            self.plugged = True
        self._wl_schedule = self._gen_schedule(self.np_random)
        self.cur_wl       = self._wl_schedule[0]
        return self._get_obs(), {}

    def step(self, action):
        rng = self.np_random

        # [F1] ACTION DELAY: action AI gui bay gio chua co hieu luc ngay. Day vao
        #  hang doi; thuc thi action da "chin" (gui tu ACTION_DELAY step truoc).
        #  Mo phong HDH can thoi gian ap dung -> AI hoc tinh kien nhan, tranh
        #  ra lenh dao dong lien tuc (action oscillation).
        # [F1+F4] ACTION DELAY chi bat o difficulty 3 (full). De/Vua: hieu luc ngay.
        # [F8] action delay tang theo do kho: diff 3 = tre 1 step, diff 4 = tre 2 step
        if   self.difficulty >= 4: delay = 2
        elif self.difficulty >= 3: delay = 1
        else:                      delay = 0
        self._action_queue.append(np.array(action, dtype=np.float32))
        if delay == 0:
            eff = self._action_queue.pop(0)
        elif len(self._action_queue) > delay:
            eff = self._action_queue.pop(0)        # action chin -> ap dung
        else:
            # [BUG-02 fix] Warmup: chua du item trong hang doi (delay buoc dau
            #  episode). Dung action MAC DINH trung tinh thay vi lap lai action dau
            #  nhieu lan (truoc day peek queue[0] khien action_0 chay 2-3 lan).
            eff = np.array([0.85, 0.80, 0, 1, 0.5, 0, 0], dtype=np.float32)

        new_throttle   = float(np.clip(eff[0], 0.20, 1.00))
        new_brightness = float(np.clip(eff[1], 0.30, 1.00))
        defer_tasks    = bool(eff[2] > 0.5)
        force_igpu     = bool(eff[3] < 0.5)
        refresh_a      = float(eff[4])
        wifi_save      = bool(eff[5] > 0.5)
        charge_lim     = bool(eff[6] > 0.5)

        if   refresh_a <= 0.4: self.refresh_hz = REFRESH_MODE_TO_HZ[0]
        elif refresh_a <= 0.7: self.refresh_hz = REFRESH_MODE_TO_HZ[1]
        else:                  self.refresh_hz = min(REFRESH_MODE_TO_HZ[2], self.panel_hz)

        annoyance = abs(new_brightness - self.prev_brightness) * self.user_dark_sens
        annoyance += max(0.0, 0.55 - new_brightness) * 0.5 * self.user_dark_sens
        self.throttle_max    = new_throttle
        self.brightness      = new_brightness
        self.prev_brightness = new_brightness
        self.wifi_save       = wifi_save
        self.charge_limit_on = charge_lim

        # [F5] Sac theo THOI QUEN (profile ngay) thay vi ngau nhien thuan.
        #  difficulty 1: luon co dien (desktop). difficulty>=2: theo lich gio cua
        #  profile, co them ~2% nhieu (quen cam / cam tre) cho thuc te.
        if self.difficulty >= 2:
            hour = (self.start_hour + (self.step_count * STEP_SECONDS) // 3600) % 24
            should_plug = CHARGE_PROFILES[self.charge_profile](hour)
            if rng.random() < 0.02:          # nhieu nho: lech thoi quen
                should_plug = not should_plug
            self.plugged = should_plug
        else:
            self.plugged = True

        self.cur_wl = self._wl_schedule[min(self.step_count, self.episode_steps - 1)]
        wl_name = WORKLOAD_NAMES[self.cur_wl]
        needs_dgpu = WORKLOADS[self.cur_wl][3]

        # [F2] SPIKE WORKLOAD: tac vu ngam bat ngo (Windows Update / antivirus /
        #  OneDrive sync) vot CPU len trong vai phut roi tat. AI phai hoc "chiu dung"
        #  thay vi hoang loan ha xung lam may lag them.
        # [F8] spike: diff 3 tan suat thuong, diff 4 day len gap doi (lien tuc hon)
        spike_prob = SPIKE_PROB * (1.5 if self.difficulty >= 4 else 1.0)
        if self.difficulty >= 3 and self._spike_left <= 0 and rng.random() < spike_prob:
            self._spike_left = int(rng.integers(SPIKE_DUR_MIN, SPIKE_DUR_MAX))
            self._spike_cpu  = SPIKE_CPU_ADD
        spike_active = self._spike_left > 0
        if spike_active:
            self._spike_left -= 1

        if not self.has_dgpu:
            self.dgpu_on = False
        elif force_igpu and not needs_dgpu:
            self.dgpu_on = False
        else:
            self.dgpu_on = True

        power_mw, load = self._total_power(self.cur_wl, self.throttle_max, defer_tasks, rng)
        # spike cong them tai CPU + dien nang (khong giam duoc bang throttle cua AABnen
        #  AI khong the "tat" no, chi co the bu bang cach khac)
        if spike_active:
            extra_load = self._spike_cpu
            load = float(np.clip(load + extra_load, 0, 1))
            power_mw += extra_load * (self.cpu_base_mw * 12.0)
        self._last_cpu_load = load
        self._update_temp(power_mw)

        thermal_lag = 0.0
        if self.cpu_temp > 90:
            thermal_lag = (self.cpu_temp - 90) / 20.0

        mwh_step = power_mw * (STEP_SECONDS / 3600.0)
        if self.plugged:
            pct = self.battery_mwh / self.full_mwh
            charge_in = 0.0 if (charge_lim and pct >= 0.80) else (self.full_mwh * 0.012)
            self.battery_mwh = min(self.full_mwh,
                                   self.battery_mwh + charge_in - mwh_step * 0.3)
            discharge_mw = 0.0
        else:
            # [F3] DUONG CONG XA PHI TUYEN: pin Li-ion tu 100%->20% tut deu, nhung
            #  duoi 20% tut nhanh hon (dien ap sut, pin chai cang ro). He so xa tang
            #  khi pin thap -> AI hoc "cang ve cuoi cang phai chat chiu".
            pct_now = self.battery_mwh / self.full_mwh
            if self.difficulty >= 3 and pct_now < 0.20:
                steep = 1.0 + (0.20 - pct_now) / 0.20 * (0.8 + (1.0 - self.health) * 0.6)
            else:
                steep = 1.0
            self.battery_mwh = max(0.0, self.battery_mwh - mwh_step * steep)
            discharge_mw = power_mw * steep
            # sap nguon ao chi o difficulty 3
            if self.difficulty >= 3:
                brownout_pct = (1.0 - self.health) * 0.06
                if self.battery_mwh / self.full_mwh <= brownout_pct:
                    self.battery_mwh = 0.0

        baseline_mw = self._baseline_power(self.cur_wl)
        saved_mw = max(0.0, baseline_mw - power_mw)
        r_save = saved_mw / 8000.0

        need = WORKLOADS[self.cur_wl][1]
        lag = max(0.0, need - self.throttle_max) + thermal_lag
        if force_igpu and needs_dgpu and self.has_dgpu:
            lag += 1.0
        r_lag = lag * self.user_lag_sens

        r_annoy = annoyance

        r_long = 0.0
        pct = self.battery_mwh / self.full_mwh
        if self.plugged and charge_lim and pct >= 0.78:
            r_long = 1.0
        if self.plugged and not charge_lim and pct > 0.95:
            r_long -= 0.5

        # [F7] nhan trong so theo reward profile (battery_saver/performance/balanced)
        reward = (self.A * self.rw_save * r_save - self.B * self.rw_lag * r_lag
                  - self.C * r_annoy + self.D * r_long)

        self.step_count += 1
        terminated = self.battery_mwh <= 0.0
        truncated  = self.step_count >= self.episode_steps
        if terminated:
            reward -= 5.0
        if truncated and not terminated:
            reward += (self.battery_mwh / self.full_mwh) * 8.0

        info = {
            "battery_pct": pct * 100, "power_mw": power_mw,
            "workload": wl_name, "plugged": self.plugged,
            "cpu_temp": self.cpu_temp, "dgpu_on": self.dgpu_on,
            "saved_mw": saved_mw, "lag": lag,
        }
        if self.render_mode == "human":
            print(f"  s{self.step_count:3d} | {pct*100:5.1f}% | "
                  f"{'PLUG' if self.plugged else 'BATT'} | {wl_name:10s} | "
                  f"thr{self.throttle_max:4.2f} br{self.brightness:4.2f} | "
                  f"{self.refresh_hz}Hz | dG:{'1' if self.dgpu_on else '0'} | "
                  f"{power_mw:6.0f}mW {self.cpu_temp:4.1f}C | R{reward:+.2f}")

        return self._get_obs(discharge_mw), reward, terminated, truncated, info

    def _baseline_power(self, wl_i):
        cpu = self.cpu_base_mw + (self.cpu_base_mw * 14.0) * (WORKLOADS[wl_i][1] ** 1.5)
        gpu = (2500 + WORKLOADS[wl_i][2] * (self.dgpu_full - 2500)) if self.has_dgpu \
              else (200 + WORKLOADS[wl_i][2] * 2800)
        screen = 1.0 * self.screen_base * REFRESH_EXTRA_FACTOR.get(self.panel_hz, 1.18)
        wifi = 150 + WORKLOADS[wl_i][5] * 1200
        misc = 300 + WORKLOADS[wl_i][6] * 400
        return cpu + gpu + screen + wifi + misc

    def render(self):
        return None


if __name__ == "__main__":
    from gymnasium.utils.env_checker import check_env
    import time
    print("BatteryClaw — Simulator NANG CAP")
    print("=" * 60)
    env = BatteryClawEnv(render_mode=None)
    print(f"[1] obs={env.OBS_DIM} act={env.ACT_DIM} | {N_WL} workloads | "
          f"{len(MACHINE_TYPES)} machines")
    print("[2] env_checker...")
    check_env(env)
    print("    PASS")
    print("[3] Random 300 steps qua nhieu may...")
    obs, _ = env.reset(seed=0)
    assert obs.shape == (15,)
    tot = 0.0; t0 = time.time()
    for i in range(300):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        tot += r
        assert obs.min() >= -0.01 and obs.max() <= 1.01, f"obs out of range: {obs}"
        if term or trunc: obs, _ = env.reset()
    print(f"    obs trong [0,1] OK | reward random tong: {tot:.1f} | "
          f"{300/(time.time()-t0):.0f} steps/s")
    print("\nSimulator nang cap san sang train!")
