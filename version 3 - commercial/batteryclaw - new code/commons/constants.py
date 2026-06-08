"""
BatteryClaw — commons/constants.py  (TODO-04)

Tap trung cac "magic number" quan trong vao MOT noi, de tune va de doc.
Day la cac hang so CHUAN HOA phai khop giua battery_env, rl_brain, schema,
world_model... — neu doi thi doi o day.

KHONG dat dung luong pin theo may cu the o day (xem BUG-05: tu hoc tu may that).
"""

# ── Hằng số chuẩn hóa observation (mW, Hz) ──────────────────────────────────
GPU_POWER_MAX_MW   = 38000.0    # mW — chia de chuan hoa gpu_power_norm (obs[8])
DISCHARGE_MAX_MW   = 80000.0    # mW — chia de chuan hoa discharge_norm (obs[9])
REFRESH_MIN_HZ     = 60         # Hz — moc duoi de chuan hoa refresh_norm (obs[10])
REFRESH_MAX_HZ     = 165        # Hz — moc tren de chuan hoa refresh_norm
CPU_TEMP_MIN_C     = 30.0       # °C — moc duoi chuan hoa cpu_temp_norm (obs[2])
CPU_TEMP_RANGE_C   = 70.0       # °C — bien do chuan hoa nhiet do

# ── Ngưỡng phát hiện workload (xem schema.classify_workload) ────────────────
GPU_HEAVY_MW       = 8000.0     # GPU >= 8W -> coi la tai nang (render/game)
CPU_IDLE_PCT       = 10         # < 10%  -> idle
CPU_BROWSE_PCT     = 30         # < 30%  -> browse
CPU_OFFICE_PCT     = 55         # < 55%  -> office
CPU_COMPILE_PCT    = 80         # < 80%  -> compile, >= -> tai nang

# ── Guard điều khiển (rl_brain) ─────────────────────────────────────────────
THROTTLE_PLUGGED_MIN = 0.85     # cam sac -> noi long throttle toi thieu nay
THROTTLE_MIN         = 0.20     # san throttle tuyet doi
BRIGHTNESS_MIN       = 0.30     # san brightness

# ── Action discretization (refresh mode -> Hz) ──────────────────────────────
#  Panel max doi theo may; mac dinh 144 (panel MSI gaming pho bien).
PANEL_MAX_HZ        = 144
REFRESH_MODE_TO_HZ  = {0: 60, 1: 120, 2: PANEL_MAX_HZ}

# ── Pin (fallback trung tinh, KHONG theo may cu the) ────────────────────────
BATTERY_FULL_FALLBACK_MWH = 50000   # chi dung khi chua doc duoc tu may that


if __name__ == "__main__":
    print("BatteryClaw — constants.py")
    print(f"  GPU_POWER_MAX_MW = {GPU_POWER_MAX_MW}")
    print(f"  DISCHARGE_MAX_MW = {DISCHARGE_MAX_MW}")
    print(f"  GPU_HEAVY_MW     = {GPU_HEAVY_MW}")
    print(f"  REFRESH_MODE_TO_HZ = {REFRESH_MODE_TO_HZ}")
    # bat bien: nguong workload tang dan
    assert CPU_IDLE_PCT < CPU_BROWSE_PCT < CPU_OFFICE_PCT < CPU_COMPILE_PCT
    print("PASS ✓")
