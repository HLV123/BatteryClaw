"""
BatteryClaw — data_collector.py  (PHASE 2 — mục 2.1: Data Collector)

Chế độ thu thập dữ liệu THỤ ĐỘNG:
  - Kết nối engine batteryclaw.exe qua Named Pipe (giống rl_brain) NHƯNG
    không gửi action điều khiển — chỉ QUAN SÁT và GHI LẠI.
  - Mỗi chu kỳ ghi một transition (state_t, action_t, next_state_{t+1}) kèm
    các trường thô (discharge_mw, gpu_power_mw...) để sau train world model
    và tính reward thật.
  - Lưu rolling ra parquet: YYYYMMDD_HHMMSS_state.parquet (mỗi ~N dòng flush).

Có 2 nguồn action khi thu thập:
  (a) Quan sát thuần: action = trạng thái điều khiển hiện tại của máy
      (throttle/brightness/refresh/gpu đang đặt). Đây là hành vi mặc định —
      "chạy ngầm, không can thiệp" đúng như phase.txt mô tả.
  (b) Nếu chạy kèm rl_brain, có thể nhận action thực tế model gửi (qua tham số).

Chạy:
  python data_collector.py --minutes 60         # thu 60 phút rồi dừng
  python data_collector.py --session demo        # đặt tên session
  python data_collector.py --interval 10         # chu kỳ giây (mặc định 10)

Cần: batteryclaw.exe đang chạy. Nếu không có engine, dùng --simulate để sinh
dữ liệu giả từ battery_env (hữu ích để test pipeline Phase 2 mà không cần Windows).
"""

import argparse
import json
import time
import os
import sys
import datetime
import logging

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import (
    STATE_COLUMNS, ACTION_COLUMNS, RAW_COLUMNS, NEXT_STATE_COLUMNS,
    ALL_COLUMNS, empty_row, is_game_process, classify_workload,
)

# [MINOR-A] dung hang so chuan hoa tu commons/constants.py (single source).
#  Neu doi GPU_POWER_MAX_MW/DISCHARGE_MAX_MW thi du lieu thu thap phai theo,
#  neu khong world model se train tren scale lech.
try:
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "commons"))
    from constants import GPU_POWER_MAX_MW, DISCHARGE_MAX_MW
except Exception:
    GPU_POWER_MAX_MW = 38000.0
    DISCHARGE_MAX_MW = 80000.0

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [DC] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("data_collector")

PIPE_NAME     = r'\\.\pipe\BatteryClaw'
DEFAULT_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FLUSH_EVERY   = 60          # ghi ra đĩa mỗi 60 dòng


# ── chuyển JSON state (từ engine) -> 15 obs + raw, tái dùng logic rl_brain ──
def state_json_to_obs_and_raw(s: dict):
    """Trả (obs_dict 15 trường, raw_dict). Khớp rl_brain.state_to_obs."""
    cpu_load_raw = s.get("cpu_load", 30)
    gpu_power   = s.get("gpu_power_mw", 0.0)
    # [DESIGN-06] phan loai workload ket hop CPU + GPU (nguon chung schema.py)
    wl = classify_workload(cpu_load_raw, gpu_power, s.get("fg_app", ""))

    battery_pct = s.get("batt_pct", 50) / 100.0
    gpu_type    = s.get("gpu_type", 0)
    gpu_type_n  = {0: 0.0, 1: 0.5, 2: 1.0}.get(gpu_type, 0.5)
    discharge   = s.get("discharge_mw", 0.0)
    refresh_hz  = s.get("refresh_hz", 60)

    obs = {
        "battery_pct"     : battery_pct,
        "cpu_load"        : s.get("cpu_load", 30) / 100.0,
        "cpu_temp_norm"   : float(np.clip((s.get("temp_c", 45.0) - 30.0) / 70.0, 0, 1)),
        "workload_id"     : float(wl),
        "brightness"      : s.get("brightness", 80) / 100.0,
        "throttle_max"    : s.get("cpu_max", 100) / 100.0,
        "time_norm"       : 1.0 - battery_pct,
        "gpu_type_norm"   : gpu_type_n,
        "gpu_power_norm"  : float(np.clip(gpu_power / GPU_POWER_MAX_MW, 0, 1)),
        "discharge_norm"  : float(np.clip(discharge / DISCHARGE_MAX_MW, 0, 1)),
        "refresh_norm"    : float(np.clip((refresh_hz - 60) / (165 - 60), 0, 1)),
        "wifi_active"     : 1.0 if s.get("wifi", False) else 0.0,
        "audio_active"    : 1.0 if s.get("audio", False) else 0.0,
        "ram_pressure"    : float(np.clip(s.get("ram_pct", 50.0) / 100.0, 0, 1)),
        "time_of_day_norm": float(np.clip(s.get("tod", 0.5), 0, 1)),
    }
    fg = s.get("fg_app", "")
    raw = {
        "discharge_mw" : discharge,
        "gpu_power_mw" : gpu_power,
        "gpu_type"     : float(gpu_type),
        "refresh_hz"   : float(refresh_hz),
        "cpu_temp_c"   : float(s.get("temp_c", 45.0)),
        "battery_mwh"  : float(s.get("batt_mwh", 0)),
        "plugged"      : 1.0 if s.get("plugged", False) else 0.0,
        "charging"     : 1.0 if s.get("charging", False) else 0.0,
        "fg_app"       : fg,
        "is_game"      : 1.0 if is_game_process(fg) else 0.0,
    }
    return obs, raw


def observed_action_from_state(s: dict):
    """Hành động 'quan sát' = cấu hình điều khiển hiện tại của máy.
    Khi thu thụ động, đây là action gắn với transition."""
    refresh_hz = s.get("refresh_hz", 60)
    refresh_mode = 0 if refresh_hz <= 60 else (1 if refresh_hz <= 120 else 2)
    gpu_type = s.get("gpu_type", 0)
    # gpu_switch quan sát: nếu chỉ iGPU coi như "đã ép iGPU"(0), có dGPU thì (1)
    gpu_switch = 0 if gpu_type == 0 else 1
    return {
        "cpu_throttle_max": s.get("cpu_max", 100) / 100.0,
        "brightness_act"  : s.get("brightness", 80) / 100.0,
        "defer_tasks"     : 0.0,
        "gpu_switch"      : float(gpu_switch),
        "refresh_mode"    : float(refresh_mode),
        "wifi_power_save" : 0.0,
        "charge_limit_on" : 0.0,
    }


class ParquetWriter:
    """Ghi transition ra parquet theo session. Flush mỗi FLUSH_EVERY dòng."""
    def __init__(self, out_dir, session_id):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(out_dir, f"{stamp}_{session_id}_state.parquet")
        self.rows = []
        self.total = 0

    def add(self, row: dict):
        self.rows.append(row)
        if len(self.rows) >= FLUSH_EVERY:
            self.flush()

    def flush(self):
        if not self.rows:
            return
        try:
            import pandas as pd
            df_new = pd.DataFrame(self.rows, columns=ALL_COLUMNS)
            if os.path.exists(self.path):
                old = pd.read_parquet(self.path)
                df = pd.concat([old, df_new], ignore_index=True)
            else:
                df = df_new
            df.to_parquet(self.path, index=False)
            self.total += len(self.rows)
            log.info(f"Đã ghi {len(self.rows)} dòng (tổng {self.total}) -> "
                     f"{os.path.basename(self.path)}")
            self.rows = []
        except ImportError:
            # Không có pandas/pyarrow -> fallback ghi JSONL để không mất dữ liệu
            jpath = self.path.replace(".parquet", ".jsonl")
            with open(jpath, "a", encoding="utf-8") as f:
                for r in self.rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            self.total += len(self.rows)
            log.info(f"(pandas thiếu) ghi JSONL {len(self.rows)} dòng -> "
                     f"{os.path.basename(jpath)}")
            self.rows = []


def run_with_engine(args, writer):
    """Thu thập từ engine thật qua Named Pipe."""
    import ctypes
    GENERIC_RW = 0xC0000000
    while True:
        try:
            h = ctypes.windll.kernel32.CreateFileW(
                PIPE_NAME, GENERIC_RW, 0, None, 3, 0, None)
            if h == -1:
                log.info("Chưa kết nối được engine, thử lại sau 3s...")
                time.sleep(3); continue
            break
        except Exception as e:
            log.error(f"Lỗi pipe: {e}"); time.sleep(3)

    log.info("Đã kết nối engine. Bắt đầu thu thập THỤ ĐỘNG (không can thiệp).")
    prev_obs = prev_action = prev_raw = None
    deadline = time.time() + args.minutes * 60 if args.minutes else None
    session = writer  # alias

    buf = b""
    while True:
        if deadline and time.time() > deadline:
            log.info("Hết thời gian thu thập."); break
        # đọc một dòng JSON state từ pipe
        nread = ctypes.c_ulong(0)
        chunk = ctypes.create_string_buffer(8192)
        ok = ctypes.windll.kernel32.ReadFile(
            h, chunk, 8192, ctypes.byref(nread), None)
        if not ok or nread.value == 0:
            time.sleep(0.2); continue
        buf += chunk.raw[:nread.value]
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                s = json.loads(line.decode("utf-8", "ignore"))
            except Exception:
                continue
            if s.get("type") != "state":
                continue
            obs, raw = state_json_to_obs_and_raw(s)
            action = observed_action_from_state(s)
            _record(session, prev_obs, prev_action, prev_raw, obs, args.session)
            prev_obs, prev_action, prev_raw = obs, action, raw
        time.sleep(args.interval)
    writer.flush()


def run_simulated(args, writer):
    """Sinh dữ liệu giả từ battery_env để test pipeline Phase 2 (không cần Windows)."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulator"))
    from battery_env import BatteryClawEnv, WORKLOAD_NAMES

    env = BatteryClawEnv()
    obs_vec, _ = env.reset(seed=args.seed)
    n_steps = args.steps
    log.info(f"Chế độ SIMULATE: sinh {n_steps} transition giả lập.")

    prev = None
    for i in range(n_steps):
        action_vec = env.action_space.sample()
        next_vec, reward, term, trunc, info = env.step(action_vec)

        # map vector env -> dict schema
        obs = {c: float(obs_vec[j]) for j, c in enumerate(STATE_COLUMNS)}
        obs["workload_id"] = float(WORKLOAD_NAMES.index(info["workload"]))
        nxt = {c: float(next_vec[j]) for j, c in enumerate(STATE_COLUMNS)}
        action = {
            "cpu_throttle_max": float(np.clip(action_vec[0], 0.2, 1.0)),
            "brightness_act"  : float(np.clip(action_vec[1], 0.3, 1.0)),
            "defer_tasks"     : float(action_vec[2] > 0.5),
            "gpu_switch"      : 0.0 if action_vec[3] < 0.5 else 1.0,
            "refresh_mode"    : 0.0 if action_vec[4] <= 0.4 else (1.0 if action_vec[4] <= 0.7 else 2.0),
            "wifi_power_save" : float(action_vec[5] > 0.5),
            "charge_limit_on" : float(action_vec[6] > 0.5),
        }
        raw = {
            "discharge_mw" : info["power_mw"],
            "gpu_power_mw" : info["gpu_power_mw"],
            "gpu_type"     : 1.0 if info["dgpu_on"] else 0.0,
            "refresh_hz"   : float(info["refresh_hz"]),
            "cpu_temp_c"   : info["cpu_temp"],
            "battery_mwh"  : 0.0,
            "plugged"      : 0.0,
            "charging"     : 0.0,
            "fg_app"       : info["workload"],
            "is_game"      : 1.0 if info["workload"] == "game" else 0.0,
        }

        row = empty_row()
        row["ts_ms"] = time.time() * 1000
        row["session_id"] = args.session
        for c in STATE_COLUMNS:      row[c] = obs[c]
        for c in ACTION_COLUMNS:     row[c] = action[c]
        for c in RAW_COLUMNS:        row[c] = raw[c]
        for c in STATE_COLUMNS:      row["next_" + c] = nxt[c]
        row["reward"] = float(reward)   # sim đã có reward; máy thật sẽ tính sau
        writer.add(row)

        obs_vec = next_vec
        if term or trunc:
            obs_vec, _ = env.reset()
    writer.flush()
    log.info("Hoàn tất sinh dữ liệu giả lập.")


def _record(writer, prev_obs, prev_action, prev_raw, cur_obs, session_id):
    """Ghép (prev_obs, prev_action) với cur_obs làm next_state -> 1 transition."""
    if prev_obs is None or prev_action is None:
        return
    row = empty_row()
    row["ts_ms"] = time.time() * 1000
    row["session_id"] = session_id
    for c in STATE_COLUMNS:  row[c] = prev_obs[c]
    for c in ACTION_COLUMNS: row[c] = prev_action[c]
    for c in RAW_COLUMNS:    row[c] = prev_raw[c] if prev_raw else 0.0
    for c in STATE_COLUMNS:  row["next_" + c] = cur_obs[c]
    # reward để trống (0) — sẽ tính bằng reward.py khi build dataset
    writer.add(row)


def main():
    ap = argparse.ArgumentParser(description="BatteryClaw Phase 2 — Data Collector")
    ap.add_argument("--session",  default="sess", help="tên session")
    ap.add_argument("--minutes",  type=float, default=0, help="thu trong N phút (0=vô hạn)")
    ap.add_argument("--interval", type=float, default=10.0, help="chu kỳ đọc (giây)")
    ap.add_argument("--out",      default=DEFAULT_DIR, help="thư mục lưu parquet")
    ap.add_argument("--simulate", action="store_true", help="sinh dữ liệu giả (không cần engine)")
    ap.add_argument("--steps",    type=int, default=2000, help="số bước khi --simulate")
    ap.add_argument("--seed",     type=int, default=0)
    args = ap.parse_args()

    writer = ParquetWriter(args.out, args.session)
    try:
        if args.simulate:
            run_simulated(args, writer)
        else:
            run_with_engine(args, writer)
    except KeyboardInterrupt:
        log.info("Dừng bởi người dùng, đang flush...")
        writer.flush()


if __name__ == "__main__":
    main()
