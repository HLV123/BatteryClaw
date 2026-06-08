"""
BatteryClaw — schema.py  (PHASE 2)
Định nghĩa CHUẨN cho một transition (s_t, a_t, r_t, s_{t+1}) thu từ máy thật.

Đây là "hợp đồng dữ liệu" dùng chung cho:
  - datacollector  (ghi transition ra parquet)
  - worldmodel     (train f(state, action) -> next_state)
  - reward         (tính reward thật từ các trường này)
  - simulator      (env mới bọc quanh world model)

Thứ tự 15 chiều observation PHẢI khớp với battery_env._get_obs và
rl_brain.state_to_obs (Phase 1). Đừng đổi thứ tự — chỉ thêm vào cuối nếu cần.
"""

import os as _os
import sys as _sys
# TODO-04: lay nguong tu commons/constants.py (single source). Fallback an toan
#  neu khong import duoc (vd chay schema doc lap).
try:
    _sys.path.insert(0, _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "commons"))
    from constants import (GPU_HEAVY_MW, CPU_IDLE_PCT, CPU_BROWSE_PCT,
                           CPU_OFFICE_PCT, CPU_COMPILE_PCT)
except Exception:
    GPU_HEAVY_MW = 8000.0
    CPU_IDLE_PCT, CPU_BROWSE_PCT, CPU_OFFICE_PCT, CPU_COMPILE_PCT = 10, 30, 55, 80

# ── 15 trường observation (đúng thứ tự Phase 1) ─────────────────────────────
STATE_COLUMNS = [
    "battery_pct",      # 0
    "cpu_load",         # 1
    "cpu_temp_norm",    # 2
    "workload_id",      # 3  (0..4)/4 đã chuẩn hóa khi vào model; ở đây lưu raw 0..4
    "brightness",       # 4
    "throttle_max",     # 5
    "time_norm",        # 6
    "gpu_type_norm",    # 7  (0=iGPU,0.5=dGPU,1=both)
    "gpu_power_norm",   # 8  (/38000mW)
    "discharge_norm",   # 9  (/80000mW)  ← discharge thật đo ACPI, chuẩn hóa
    "refresh_norm",     # 10 ((hz-60)/105)
    "wifi_active",      # 11
    "audio_active",     # 12
    "ram_pressure",     # 13
    "time_of_day_norm", # 14
]

# ── 7 chiều action (đúng thứ tự Phase 1) ────────────────────────────────────
ACTION_COLUMNS = [
    "cpu_throttle_max",  # 0  [0.2,1.0]
    "brightness_act",    # 1  [0.3,1.0]
    "defer_tasks",       # 2  0/1
    "gpu_switch",        # 3  0=iGPU,1=dGPU,2=keep (lưu raw)
    "refresh_mode",      # 4  0=60,1=120,2=max
    "wifi_power_save",   # 5  0/1
    "charge_limit_on",   # 6  0/1
]

# ── Các trường thô (chưa chuẩn hóa) — cần cho reward thật & world model ──────
RAW_COLUMNS = [
    "discharge_mw",      # tốc độ xả thật (mW) — ground truth cho R_primary
    "gpu_power_mw",      # công suất GPU thật (mW)
    "gpu_type",          # 0/1/2
    "refresh_hz",        # 60/120/144/165
    "cpu_temp_c",        # °C — cho ràng buộc an toàn (CPU>95°C)
    "battery_mwh",       # mWh còn lại
    "plugged",           # cắm sạc?
    "charging",          # đang sạc?
    "fg_app",            # tên app foreground (cho R_context)
    "is_game",           # foreground có phải game không (0/1)
]

# ── Trường reward (điền sau khi tính, hoặc để trống khi thu thụ động) ────────
REWARD_COLUMNS = [
    "reward",            # tổng reward (nếu đã tính)
    "r_primary",
    "r_comfort",
    "r_longevity",
    "r_context",
]

# ── Metadata mỗi dòng ───────────────────────────────────────────────────────
META_COLUMNS = [
    "ts_ms",             # timestamp ms (GetTickCount64 phía engine, hoặc time.time())
    "session_id",        # id phiên thu thập
    "is_next",           # 0 = state hiện tại, 1 = đây là next_state (xem ghi chú)
]

# Một transition lưu phẳng: state_t (15) + action (7) + raw (10) + reward (5)
#  + next_state_t+1 (15, tiền tố "next_"). next_state để train world model.
NEXT_STATE_COLUMNS = ["next_" + c for c in STATE_COLUMNS]

ALL_COLUMNS = (
    META_COLUMNS
    + STATE_COLUMNS
    + ACTION_COLUMNS
    + RAW_COLUMNS
    + REWARD_COLUMNS
    + NEXT_STATE_COLUMNS
)

# Danh sách tên process game (để gán is_game / R_context). Khớp app_detector.cpp.
GAME_HINTS = [
    "valorant", "csgo", "cs2", "dota2", "dota", "genshinimpact", "genshin",
    "leagueoflegends", "league", "pubg", "fortnite", "apexlegends", "apex",
    "overwatch", "eldenring", "cyberpunk2077", "cyberpunk", "minecraft",
    "robloxplayerbeta",
]

def is_game_process(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in GAME_HINTS)


# [DESIGN-06 + BUG-04] Phat hien workload — NGUON DUY NHAT, dung chung cho
#  rl_brain, data_collector, reward. Khong chi dua CPU load (CPU 5% nhung GPU
#  100% render se bi nham la "idle"); ket hop GPU power de chinh xac hon.
#  Tra workload_id: 0=idle 1=browse 2=office 3=compile 4=game/render
def classify_workload(cpu_load_pct, gpu_power_mw=0.0, fg_app=""):
    # GPU dang tai nang -> game/render bat ke CPU (vd dung video, choi game)
    if gpu_power_mw is not None and gpu_power_mw >= GPU_HEAVY_MW:
        return 4
    if is_game_process(fg_app):
        return 4
    cl = cpu_load_pct or 0
    if   cl < CPU_IDLE_PCT:    return 0    # idle
    elif cl < CPU_BROWSE_PCT:  return 1    # browse
    elif cl < CPU_OFFICE_PCT:  return 2    # office
    elif cl < CPU_COMPILE_PCT: return 3    # compile
    return 4                               # tai nang


def empty_row():
    """Tạo một dòng rỗng (dict) với đủ cột, giá trị mặc định 0/''. """
    row = {c: 0.0 for c in ALL_COLUMNS}
    row["fg_app"] = ""
    row["session_id"] = ""
    return row
