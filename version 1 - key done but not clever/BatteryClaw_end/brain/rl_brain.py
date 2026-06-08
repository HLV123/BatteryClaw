"""
BatteryClaw — rl_brain.py  (PHASE 1)
RL Brain chay tren laptop:
- Load model ONNX (nhe, khong can GPU)
- Ket noi voi engine batteryclaw.exe qua Named Pipe
- Thuc day moi 10 giay, ra quyet dinh, ngu lai

PHASE 1 — thay doi:
  state_to_obs    : 7 -> 15 chieu (GPU, refresh, wifi, audio, ram, time, discharge)
  action_to_command: 3 -> 7 chieu (them gpu_switch, refresh_rate, wifi_save, charge_limit)
  reward log       : dung discharge_rate_mw THAT (ACPI) thay baseline ao 12000mW

Chay: python rl_brain.py --model ../simulator/models/batteryclaw_policy.onnx
Can: batteryclaw.exe dang chay (Admin) truoc
"""

import argparse
import json
import time
import ctypes
import ctypes.wintypes as wt
import numpy as np
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RL] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("rl_brain.log", encoding="utf-8")
    ]
)
log = logging.getLogger("rl_brain")

# [REMAIN-02] Dung hang so chuan hoa tu commons/constants.py (single source).
#  Neu doi GPU_POWER_MAX_MW / DISCHARGE_MAX_MW de tune normalization thi doi
#  o constants.py, ca env lan brain deu theo -> tranh lech scale train/deploy.
try:
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "commons"))
    from constants import (GPU_POWER_MAX_MW, DISCHARGE_MAX_MW,
                           BATTERY_FULL_FALLBACK_MWH)
except Exception:
    GPU_POWER_MAX_MW = 38000.0
    DISCHARGE_MAX_MW = 80000.0
    BATTERY_FULL_FALLBACK_MWH = 50000

PIPE_NAME      = r'\\.\pipe\BatteryClaw'
WAKE_INTERVAL  = 10.0    # giay — thuc day moi 10 giay
# [BUG-05] KHONG hardcode dung luong pin theo 1 may. Day chi la FALLBACK khi
#  chua doc duoc tu may that. Engine gui 'batt_full' (FullChargeCapacity WMI)
#  trong state JSON;
#  neu khong co, rl_brain tu hoc bang gia tri batt_mwh lon nhat quan sat duoc.
BATTERY_FULL_FALLBACK = BATTERY_FULL_FALLBACK_MWH   # [REMAIN-02] tu constants
OBS_DIM        = 15      # [P1] 7 -> 15
ACT_DIM        = 7       # [P1] 3 -> 7


# ── Named Pipe client (Windows) ─────────────────────────────────────────────

class PipeClient:
    def __init__(self):
        self.handle  = None
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        # [FIX PIPE] Khai bao dung kieu tra ve/tham so. Truoc day CreateFileW
        #  tra HANDLE 64-bit nhung ctypes mac dinh coi la int 32-bit -> handle
        #  bi cat/sai dau -> so sanh INVALID_HANDLE sai -> "thanh cong gia" roi
        #  ReadFile/WriteFile fail ngay -> pipe dong/mo lap lien tuc.
        self.kernel32.CreateFileW.restype  = wt.HANDLE
        self.kernel32.CreateFileW.argtypes = [
            wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
            wt.DWORD, wt.DWORD, ctypes.c_void_p]
        self.kernel32.ReadFile.restype  = wt.BOOL
        self.kernel32.ReadFile.argtypes = [
            wt.HANDLE, ctypes.c_void_p, wt.DWORD,
            ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
        self.kernel32.WriteFile.restype  = wt.BOOL
        self.kernel32.WriteFile.argtypes = [
            wt.HANDLE, ctypes.c_void_p, wt.DWORD,
            ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
        self.kernel32.CloseHandle.restype  = wt.BOOL
        self.kernel32.CloseHandle.argtypes = [wt.HANDLE]
        self._INVALID = wt.HANDLE(-1).value

    def connect(self, retries=10):
        GENERIC_READ  = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80

        # [DESIGN-07] exponential backoff + jitter
        import random
        BASE_DELAY = 1.0
        MAX_DELAY  = 30.0

        for i in range(retries):
            handle = self.kernel32.CreateFileW(
                PIPE_NAME,
                GENERIC_READ | GENERIC_WRITE,
                0, None, OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL, None
            )
            # handle hop le -> ket noi thanh cong
            if handle and handle != self._INVALID:
                self.handle = handle
                log.info(f"Pipe connected (attempt {i+1})")
                return True

            err = ctypes.get_last_error()
            delay = min(BASE_DELAY * (2 ** i), MAX_DELAY)
            delay += random.uniform(0, delay * 0.2)   # jitter +-20%
            if err == 2:   # ERROR_FILE_NOT_FOUND
                log.warning(f"  Waiting for engine... ({i+1}/{retries}, retry in {delay:.1f}s)")
            else:
                log.error(f"  Pipe error: {err} (retry in {delay:.1f}s)")
            time.sleep(delay)

        return False

    def read(self, bufsize=4096):
        if not self.handle:
            return None
        buf   = ctypes.create_string_buffer(bufsize)
        nread = ctypes.c_ulong(0)
        ok = self.kernel32.ReadFile(
            self.handle, buf, bufsize,
            ctypes.byref(nread), None
        )
        if not ok or nread.value == 0:
            return None
        return buf.raw[:nread.value].decode('utf-8', errors='replace').strip()

    def write(self, data: str):
        if not self.handle:
            return False
        b       = data.encode('utf-8')
        written = ctypes.c_ulong(0)
        ok = self.kernel32.WriteFile(
            self.handle, b, len(b),
            ctypes.byref(written), None
        )
        return bool(ok)

    def close(self):
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


# ── ONNX Policy ─────────────────────────────────────────────────────────────

class OnnxPolicy:
    def __init__(self, model_path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(
            model_path,
            providers=['CPUExecutionProvider']  # CPU — khong can GPU
        )
        self.input_name  = self.sess.get_inputs()[0].name
        self.output_name = self.sess.get_outputs()[0].name
        log.info(f"ONNX model loaded: {model_path}")
        log.info(f"  Input : {self.sess.get_inputs()[0].shape}")
        log.info(f"  Output: {self.sess.get_outputs()[0].shape}")

    def predict(self, obs: np.ndarray) -> np.ndarray:
        """
        obs: (15,) float32   [P1]
        returns: (7,) float32 — raw tanh action
                 [throttle, brightness, defer, gpu_switch,
                  refresh, wifi_save, charge_limit]
        """
        inp = obs.reshape(1, OBS_DIM).astype(np.float32)
        out = self.sess.run([self.output_name], {self.input_name: inp})
        return out[0][0]   # (7,)


# ── State parser ─────────────────────────────────────────────────────────────

def parse_state(json_str: str) -> dict | None:
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None

def state_to_obs(s: dict) -> np.ndarray:
    """
    Chuyen JSON state tu C++ sang observation vector (15,) — KHOP voi battery_env._get_obs.
    Thu tu phai giong het env, neu khong model se hieu sai input.
    """
    battery_pct  = s.get("batt_pct", 50) / 100.0
    cpu_load     = s.get("cpu_load", 30) / 100.0
    temp_c       = s.get("temp_c", 45.0)
    # temp_c <= 0 means "no reading" (engine returns -1 when WMI blocks thermal
    # zone, common on MSI laptops). Use a neutral 45C so obs is not skewed.
    if temp_c is None or temp_c <= 0:
        temp_c = 45.0
    temp_norm    = float(np.clip((temp_c - 30.0) / 70.0, 0.0, 1.0))
    brightness   = s.get("brightness", 80) / 100.0
    throttle_max = s.get("cpu_max", 100) / 100.0

    # Uoc luong workload tu CPU load (giu nguyen logic cu).
    # [MINOR-02] CO Y giu CPU-only o day, KHONG dung classify_workload (GPU-aware).
    #  Ly do: obs vector nay la INPUT cho model da train (battery_env._get_obs
    #  dung workload tu simulator). Doi sang GPU-aware se lech input -> phai
    #  retrain model. classify_workload() chi dung cho REWARD signal (Phase 3),
    #  khong dung cho obs. Khi nao retrain voi env GPU-aware thi moi doi cho nay.
    cpu_load_raw = s.get("cpu_load", 30)
    if   cpu_load_raw < 10: workload_id = 0   # idle
    elif cpu_load_raw < 30: workload_id = 1   # browse
    elif cpu_load_raw < 55: workload_id = 2   # office
    elif cpu_load_raw < 80: workload_id = 3   # compile
    else:                   workload_id = 4   # game

    time_norm = 1.0 - battery_pct   # proxy thoi gian trong episode

    # ── Phase 1 — truong moi tu engine C++ ──────────────────────
    gpu_type     = s.get("gpu_type", 0)             # 0=iGPU,1=dGPU,2=both
    gpu_type_n   = {0: 0.0, 1: 0.5, 2: 1.0}.get(gpu_type, 0.5)
    gpu_power    = s.get("gpu_power_mw", 0.0)
    discharge_mw = s.get("discharge_mw", 0.0)
    refresh_hz   = s.get("refresh_hz", 60)
    wifi         = 1.0 if s.get("wifi", False) else 0.0
    audio        = 1.0 if s.get("audio", False) else 0.0
    ram_pct      = s.get("ram_pct", 50.0) / 100.0
    tod          = s.get("tod", 0.5)

    return np.array([
        battery_pct,
        cpu_load,
        temp_norm,
        workload_id / 4.0,
        brightness,
        throttle_max,
        time_norm,
        # ── Phase 1 ──
        gpu_type_n,
        float(np.clip(gpu_power   / GPU_POWER_MAX_MW, 0.0, 1.0)),
        float(np.clip(discharge_mw / DISCHARGE_MAX_MW, 0.0, 1.0)),
        float(np.clip((refresh_hz - 60) / (165 - 60), 0.0, 1.0)),
        wifi,
        audio,
        float(np.clip(ram_pct, 0.0, 1.0)),
        float(np.clip(tod, 0.0, 1.0)),
    ], dtype=np.float32)

def action_to_command(raw_action: np.ndarray, state: dict) -> dict:
    """
    Chuyen raw action tu ONNX (tanh, [-1,1]) sang lenh JSON cho engine C++.
    raw_action (7,): [throttle, brightness, defer, gpu_switch, refresh, wifi_save, charge_limit]
    """
    def scale(x, lo, hi):
        return float(lo + (x + 1.0) / 2.0 * (hi - lo))

    # ── continuous ──────────────────────────────────────────────
    throttle_max = float(np.clip(scale(raw_action[0], 0.20, 1.00), 0.20, 1.00))
    brightness   = float(np.clip(scale(raw_action[1], 0.30, 1.00), 0.30, 1.00))
    defer        = bool(scale(raw_action[2], 0.0, 1.0) > 0.5)

    # ── Phase 1 discrete (tanh -> [0,1] -> nguong) ──────────────
    gpu_raw      = scale(raw_action[3], 0.0, 1.0)
    refresh_raw  = scale(raw_action[4], 0.0, 1.0)
    wifi_raw     = scale(raw_action[5], 0.0, 1.0)
    charge_raw   = scale(raw_action[6], 0.0, 1.0)

    # gpu_switch: <0.5 ep iGPU (tat dGPU) = 0 ; >=0.5 cho phep dGPU = 1
    gpu_switch   = 0 if gpu_raw < 0.5 else 1
    # refresh: 0..0.4=60Hz(0), 0.4..0.7=120Hz(1), >0.7=max(2)
    refresh_mode = 0 if refresh_raw <= 0.4 else (1 if refresh_raw <= 0.7 else 2)
    wifi_save    = bool(wifi_raw > 0.5)
    charge_limit = 80 if charge_raw > 0.5 else -1

    # ── lop bao ve (giong canDisableDgpu phia C++, them tang an toan o day) ──
    fg = str(state.get("fg_app", "")).lower()
    GAME_HINTS = ("game", "valorant", "csgo", "cs2", "dota", "genshin",
                  "league", "fortnite", "apex", "eldenring", "cyberpunk")
    if any(h in fg for h in GAME_HINTS):
        gpu_switch   = 1     # dang choi game -> KHONG tat dGPU
        refresh_mode = 2     # giu refresh cao cho muot
        throttle_max = max(throttle_max, 0.85)

    # Dang sac dien -> noi long tiet kiem
    if state.get("plugged", False):
        throttle_max = max(throttle_max, 0.80)
        brightness   = max(brightness,   0.70)
        defer        = False
        gpu_switch   = 2     # khong dong cham GPU khi cam dien

    # Pin < 10% -> ep tiet kiem toi da
    batt_pct = state.get("batt_pct", 50)
    if batt_pct < 10:
        throttle_max = min(throttle_max, 0.50)
        brightness   = min(brightness,   0.40)
        defer        = True
        gpu_switch   = 0     # tat dGPU (neu guard C++ cho phep)
        refresh_mode = 0     # ha 60Hz
        wifi_save    = True

    return {
        "type"        : "action",
        "cpu_max"     : int(round(throttle_max * 100)),
        "cpu_min"     : 5,
        "brightness"  : int(round(brightness * 100)),
        "defer"       : defer,
        "no_boost"    : throttle_max < 0.85,
        # ── Phase 1 ──
        "gpu_switch"  : gpu_switch,      # 0=iGPU,1=dGPU,2=giu nguyen
        "refresh_rate": refresh_mode,    # 0=60,1=120,2=max
        "wifi_save"   : wifi_save,
        "charge_limit": charge_limit,    # 80 hoac -1
    }


# ── Main loop ────────────────────────────────────────────────────────────────

class RLBrain:
    def __init__(self, model_path: str, online_dir: str = None):
        self.policy = OnnxPolicy(model_path)
        self.pipe   = PipeClient()
        self.step   = 0
        self.running = True
        self.last_state = None   # snapshot moi nhat (cho app GUI)

        # Theo doi de log
        self.total_saved_mwh = 0.0
        self.prev_batt_mwh   = None
        # [BUG-05] dung luong pin day: tu hoc tu may that, khong hardcode.
        self.battery_full = BATTERY_FULL_FALLBACK

        # [Phase 3] Online learning (tuy chon). Bat bang --online.
        #  Adapter lo: refine action an toan (mode+constraints), tich buffer,
        #  fine-tune khi may nhan. Khong bat thi rl_brain chay y het Phase 1/2.
        self.online = None
        self._prev_obs = None
        self._prev_action = None
        # [DESIGN-02] cache compute_reward 1 lan o __init__, khong import trong loop
        self._compute_reward = None
        self._classify_workload = None
        if online_dir:
            try:
                import sys as _sys, os as _os
                _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                _sys.path.insert(0, _os.path.join(_root, "online"))
                _sys.path.insert(0, _os.path.join(_root, "datacollector"))
                from brain_online_adapter import BrainOnlineAdapter
                self.online = BrainOnlineAdapter(online_dir)
                try:
                    from reward import compute_reward
                    self._compute_reward = compute_reward
                except Exception:
                    self._compute_reward = None
                try:
                    from schema import classify_workload
                    self._classify_workload = classify_workload
                except Exception:
                    self._classify_workload = None
                log.info(f"[Phase 3] Online learning ON (state: {online_dir})")
            except Exception as e:
                log.warning(f"[Phase 3] Could not enable online learning: {e}")

    def connect_and_run(self):
        """Alias cho app GUI goi trong thread. Giong run()."""
        return self.run()

    def run(self):
        log.info("BatteryClaw RL Brain starting")
        log.info(f"Wake interval: {WAKE_INTERVAL}s")

        if not self.pipe.connect():
            log.error("Cannot connect to engine! Start the engine (--serve) first.")
            return

        log.info("Ready. Controlling...")
        log.info("-" * 60)

        try:
            while self.running:
                t_start = time.time()

                # 1. Doc state tu C++
                raw = self.pipe.read()
                if raw is None:
                    log.warning("Pipe closed. Reconnecting...")
                    self.pipe.close()
                    time.sleep(2)
                    if not self.pipe.connect(retries=5):
                        break
                    continue

                state = parse_state(raw)
                if not state or state.get("type") != "state":
                    continue
                self.last_state = state   # cho app GUI doc trang thai live

                # [BUG-01 fix] Lay cac truong state SOM, ngay sau khi parse,
                # vi block Phase 3 (tinh reward) can cpu_load/batt_pct truoc khi
                # toi phan log. Tranh dung bien truoc khi gan (NameError).
                cpu_load = state.get("cpu_load", 0)
                batt_pct = state.get("batt_pct", 0)
                temp_c   = state.get("temp_c", 0)

                # [BUG-05] cap nhat dung luong pin day tu may THAT:
                #  uu tien gia tri engine gui (batt_full = FullChargeCapacity WMI),
                #  neu khong co thi hoc dan bang batt_mwh lon nhat quan sat duoc.
                # [DETAIL-01] engine gui key "batt_full" (FullChargeCapacity WMI).
                _full = state.get("batt_full", 0)
                if _full and _full > 0:
                    self.battery_full = float(_full)
                else:
                    _bm = state.get("batt_mwh", 0)
                    if _bm and _bm > self.battery_full:
                        self.battery_full = float(_bm)

                # 2. Chuyen state sang observation vector
                obs = state_to_obs(state)

                # 3. ONNX inference — cuc nhanh (<1ms)
                t_infer = time.time()
                raw_action = self.policy.predict(obs)
                infer_ms = (time.time() - t_infer) * 1000

                # 4. Chuyen action sang lenh thuc te
                command = action_to_command(raw_action, state)

                # [Phase 3] tinh chinh an toan (mode + constraints) truoc khi gui
                if self.online is not None:
                    command = self.online.refine(command, state)

                # 5. Gui lenh xuong C++
                msg = json.dumps(command) + "\n"
                self.pipe.write(msg)

                # 6. Tinh pin tiet kiem — [P1] dung discharge_rate THAT (ACPI)
                batt_mwh     = state.get("batt_mwh", 0)
                discharge_mw = state.get("discharge_mw", 0.0)
                if self.prev_batt_mwh is not None and not state.get("charging"):
                    consumed = self.prev_batt_mwh - batt_mwh
                    # Baseline dong: uu tien discharge that; neu chua co thi fallback 12000mW.
                    # discharge_mw la muc XA HIEN TAI (da co BatteryClaw); de uoc tinh
                    # phan tiet kiem can baseline khong-BatteryClaw -> Phase 2 se hoc that.
                    # Tam thoi: neu dGPU da tat ma van do duoc discharge thap -> ghi nhan.
                    baseline_consumed = (discharge_mw if discharge_mw > 0 else 12000) \
                                        * (WAKE_INTERVAL / 3600.0)
                    saved = max(0, baseline_consumed - consumed)
                    self.total_saved_mwh += saved
                self.prev_batt_mwh = batt_mwh

                # [Phase 3] tich transition + fine-tune khi may nhan
                if self.online is not None:
                    # reward thuc: dung compute_reward da cache (DESIGN-02),
                    # fallback -discharge neu khong co.
                    # [DESIGN-06] workload dua CPU + GPU power, khong chi CPU.
                    gpu_pw = state.get("gpu_power_mw", 0.0)
                    fg = state.get("fg_app", "")
                    if self._classify_workload is not None:
                        _wl = self._classify_workload(cpu_load, gpu_pw, fg)
                    else:
                        _wl = 0 if cpu_load < 10 else 1 if cpu_load < 30 else \
                              2 if cpu_load < 55 else 3 if cpu_load < 80 else 4
                    if self._compute_reward is not None:
                        rrow = {"workload_id": _wl, "discharge_mw": discharge_mw,
                                "cpu_throttle_max": command["cpu_max"] / 100.0,
                                "gpu_switch": command.get("gpu_switch", 2),
                                "is_game": 1 if state.get("gpu_type") == 1 and _wl == 4 else 0,
                                "plugged": 1 if state.get("plugged") else 0,
                                "charge_limit_on": 1 if command.get("charge_limit", -1) >= 0 else 0,
                                "battery_pct": batt_pct / 100.0}
                        reward, _ = self._compute_reward(rrow)
                    else:
                        reward = -discharge_mw / DISCHARGE_MAX_MW
                    if self._prev_obs is not None:
                        self.online.observe(self._prev_obs, raw_action, reward,
                                            obs, state)
                    self._prev_obs = obs
                    # nguoi dung dang dung may -> danh dau hoat dong
                    if cpu_load > 15:
                        self.online.mark_activity()
                    self.online.tick()

                self.step += 1
                # 7. Log moi buoc (cac bien da lay som o tren)
                fg_app    = state.get("fg_app", "?")
                plugged   = "PLUGGED" if state.get("plugged") else "BATTERY"
                gpu_names = {0: "iGPU", 1: "dGPU", 2: "BOTH"}
                gpu_now   = gpu_names.get(state.get("gpu_type", -1), "?")
                refresh   = state.get("refresh_hz", 0)

                temp_str = f"{temp_c:.0f}C" if temp_c and temp_c > 0 else "N/A"
                log.info(
                    f"Step {self.step:4d} | "
                    f"Batt:{batt_pct:4.1f}% | "
                    f"CPU:{cpu_load:4.1f}% @{command['cpu_max']}% | "
                    f"Br:{command['brightness']}% | "
                    f"GPU:{gpu_now}->sw{command['gpu_switch']} | "
                    f"{refresh}Hz->m{command['refresh_rate']} | "
                    f"Disch:{discharge_mw:.0f}mW | "
                    f"Temp:{temp_str} | "
                    f"{plugged:7s} | "
                    f"App:{fg_app[:14]:14s} | "
                    f"Saved:{self.total_saved_mwh:.0f}mWh"
                )

                # 8. Ngu den wake interval tiep theo
                elapsed = time.time() - t_start
                sleep_time = max(0.1, WAKE_INTERVAL - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            log.info("\nStopped by user (Ctrl+C)")
        finally:
            self._shutdown()

    def _shutdown(self):
        # Restore ve mac dinh truoc khi thoat
        log.info("Restoring default settings...")
        restore_cmd = {
            "type"      : "action",
            "cpu_max"   : 100,
            "cpu_min"   : 5,
            "brightness": -1,    # khong doi
            "defer"     : False,
            "no_boost"  : False,
            # ── Phase 1: khoi phuc trung lap ──
            "gpu_switch"  : 1,   # cho phep dGPU tro lai
            "refresh_rate": 2,   # giu/max refresh
            "wifi_save"   : False,
            "charge_limit": -1,  # bo gioi han sac
        }
        try:
            self.pipe.write(json.dumps(restore_cmd) + "\n")
            time.sleep(0.5)
        except:
            pass
        self.pipe.close()

        log.info(f"Total estimated battery saved: {self.total_saved_mwh:.0f} mWh")
        log.info(f"Equivalent           : {self.total_saved_mwh/max(1,self.battery_full)*100:.1f}% of battery capacity")
        if self.online is not None:
            self.online.save()
            log.info("[Phase 3] Saved replay buffer + pattern.")
        log.info("RL Brain stopped.")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BatteryClaw RL Brain")
    parser.add_argument(
        "--model",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "simulator", "models", "batteryclaw_policy.onnx"),
        help="Duong dan toi file .onnx"
    )
    parser.add_argument(
        "--online",
        nargs="?", const=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "online", "state"),
        default=None,
        help="[Phase 3] Bat online learning. Tuy chon: thu muc luu trang thai."
    )
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"Model not found: {args.model}")
        print("Train first: python simulator/train.py --steps 300000")
        sys.exit(1)

    brain = RLBrain(args.model, online_dir=args.online)
    brain.run()
