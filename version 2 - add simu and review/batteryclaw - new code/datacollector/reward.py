"""
BatteryClaw — reward.py  (PHASE 2 — mục 2.3: Reward Function Thực)

Reward không còn là ước tính. Tính trực tiếp từ dữ liệu đo thật:

    R = α·R_primary + β·R_comfort + γ·R_longevity + δ·R_context

  R_primary   = -discharge_rate_mw / baseline_discharge_mw
                (tỉ lệ tiết kiệm thực tế, đo bằng ACPI; xả càng thấp reward càng cao)
  R_comfort   = -max(0, latency_penalty)
                (phạt khi throttle quá thấp so với nhu cầu workload -> lag)
  R_longevity = +bonus nếu charge_level < 80% khi đang cắm sạc
                (bảo vệ tuổi thọ pin dài hạn)
  R_context   = +bonus nếu hành động phù hợp ngữ cảnh
                (vd: KHÔNG tắt dGPU khi đang chạy game; tắt dGPU khi không cần)

α, β, γ, δ chỉnh được qua UI (slider) — ở đây là tham số hàm.

Dùng:
    from reward import compute_reward, RewardWeights
    r, parts = compute_reward(row, RewardWeights())
"""

from dataclasses import dataclass


@dataclass
class RewardWeights:
    alpha: float = 1.0    # R_primary  — tiết kiệm điện (chính)
    beta:  float = 2.0    # R_comfort  — phạt lag
    gamma: float = 0.5    # R_longevity— bảo vệ pin
    delta: float = 0.5    # R_context  — phù hợp ngữ cảnh


# Baseline discharge (mW) khi KHÔNG có BatteryClaw, theo workload.
# Lấy từ profile máy MSI (CPU full + dGPU on + màn sáng 144Hz). Phase 2 sẽ
# thay bằng baseline đo thật cho từng máy (lưu trong cấu hình thiết bị).
BASELINE_DISCHARGE_MW = {
    0: 18000,   # idle
    1: 30000,   # browse
    2: 38000,   # office
    3: 62000,   # compile
    4: 90000,   # game
}

# Ngưỡng throttle tối thiểu mỗi workload mới không gây lag (0..1).
LAG_THRESHOLD = {0: 0.20, 1: 0.40, 2: 0.50, 3: 0.80, 4: 0.95}


def _workload_id(row):
    wl = row.get("workload_id", 1)
    try:
        return int(round(float(wl)))
    except Exception:
        return 1


def r_primary(row):
    """-discharge/baseline. Trả [-~1, 0]; xả thấp -> gần 0 (tốt)."""
    wl = _workload_id(row)
    baseline = BASELINE_DISCHARGE_MW.get(wl, 30000)
    discharge = float(row.get("discharge_mw", 0.0))
    if baseline <= 0:
        return 0.0
    # nếu đang sạc (discharge=0) -> không phạt xả
    if discharge <= 0:
        return 0.0
    return -discharge / baseline


def r_comfort(row):
    """-max(0, latency_penalty). throttle dưới ngưỡng workload -> phạt."""
    wl = _workload_id(row)
    thr = float(row.get("cpu_throttle_max", row.get("throttle_max", 1.0)))
    need = LAG_THRESHOLD.get(wl, 0.5)
    if thr >= need:
        return 0.0
    # thiếu bao nhiêu so với nhu cầu -> phạt tỉ lệ
    return -((need - thr) / max(need, 1e-6))


def r_longevity(row):
    """+1 nếu đang cắm sạc và giữ mức pin < 80% (bảo vệ pin)."""
    plugged = bool(row.get("plugged", 0))
    charge_limit_on = bool(row.get("charge_limit_on", 0))
    batt_pct = float(row.get("battery_pct", 0.5))  # đã chuẩn hóa 0..1
    if plugged and charge_limit_on and batt_pct <= 0.80:
        return 1.0
    # cắm sạc mà để sạc đầy 100% liên tục -> phạt nhẹ
    if plugged and batt_pct >= 0.98:
        return -0.5
    return 0.0


def r_context(row):
    """Thưởng/phạt theo ngữ cảnh GPU.
      + nếu đang game mà GIỮ dGPU (gpu_switch != 0)
      + nếu KHÔNG game mà tắt dGPU (gpu_switch == 0) -> tiết kiệm đúng lúc
      - nếu đang game mà tắt dGPU -> sai ngữ cảnh (gây giật)
    """
    is_game    = bool(row.get("is_game", 0))
    gpu_switch = int(round(float(row.get("gpu_switch", 2))))

    if is_game:
        if gpu_switch == 0:    # tắt dGPU khi game -> rất sai
            return -1.0
        return 0.5             # giữ dGPU khi game -> đúng
    else:
        if gpu_switch == 0:    # tắt dGPU khi không cần -> tiết kiệm đúng
            return 0.5
        return 0.0


def compute_reward(row: dict, w: "RewardWeights | None" = None) -> "tuple[float, dict]":
    """Trả (reward_tổng, dict các thành phần)."""
    if w is None:
        w = RewardWeights()
    rp = r_primary(row)
    rc = r_comfort(row)
    rl = r_longevity(row)
    rx = r_context(row)
    total = w.alpha * rp + w.beta * rc + w.gamma * rl + w.delta * rx
    parts = {
        "r_primary":   rp,
        "r_comfort":   rc,
        "r_longevity": rl,
        "r_context":   rx,
        "reward":      total,
    }
    return total, parts


def fill_rewards(df, w: RewardWeights = None):
    """Điền các cột reward cho cả DataFrame (dùng khi build dataset)."""
    cols = {"reward": [], "r_primary": [], "r_comfort": [],
            "r_longevity": [], "r_context": []}
    for _, row in df.iterrows():
        _, parts = compute_reward(row.to_dict(), w)
        for k in cols:
            cols[k].append(parts[k])
    for k, v in cols.items():
        df[k] = v
    return df


if __name__ == "__main__":
    # Test nhanh các thành phần reward
    print("BatteryClaw Phase 2 — reward.py self-test\n")
    w = RewardWeights()

    cases = [
        ("Browse, tắt dGPU, throttle đủ, xả thấp",
         {"workload_id": 1, "discharge_mw": 12000, "cpu_throttle_max": 0.6,
          "gpu_switch": 0, "is_game": 0, "plugged": 0, "battery_pct": 0.6}),
        ("Game, GIỮ dGPU, throttle cao, xả cao (đúng ngữ cảnh)",
         {"workload_id": 4, "discharge_mw": 70000, "cpu_throttle_max": 0.95,
          "gpu_switch": 1, "is_game": 1, "plugged": 0, "battery_pct": 0.5}),
        ("Game nhưng TẮT dGPU (sai) + throttle thấp gây lag",
         {"workload_id": 4, "discharge_mw": 40000, "cpu_throttle_max": 0.5,
          "gpu_switch": 0, "is_game": 1, "plugged": 0, "battery_pct": 0.5}),
        ("Cắm sạc, giữ pin 75% có charge limit (bảo vệ pin)",
         {"workload_id": 2, "discharge_mw": 0, "cpu_throttle_max": 0.8,
          "gpu_switch": 1, "is_game": 0, "plugged": 1, "charge_limit_on": 1,
          "battery_pct": 0.75}),
    ]
    for name, row in cases:
        total, parts = compute_reward(row, w)
        print(f"{name}")
        print(f"  R={total:+.3f}  | primary={parts['r_primary']:+.3f} "
              f"comfort={parts['r_comfort']:+.3f} "
              f"longevity={parts['r_longevity']:+.3f} "
              f"context={parts['r_context']:+.3f}\n")
