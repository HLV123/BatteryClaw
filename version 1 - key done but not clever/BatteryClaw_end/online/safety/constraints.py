"""
BatteryClaw — safety/constraints.py  (PHASE 3 — mục 3.5)

Ràng buộc CỨNG: dù model học gì, action cuối cùng phải qua bộ lọc này.
Đây là lớp bảo vệ không thể vượt qua, đứng độc lập với policy.

  • Không bao giờ để CPU > 95°C  -> nếu nóng, ép throttle xuống
  • Không tắt dGPU khi đang game
  • Không giảm brightness < 20% một cách tự động
  • (Pin < 10% vẫn cho tiết kiệm mạnh — đó là mong muốn, không phải vi phạm)

clamp_action() nhận action dict + state dict, trả action đã ép an toàn + log lý do.
"""

MAX_CPU_TEMP_C   = 95.0
MIN_BRIGHTNESS   = 0.20   # 20%
HOT_THROTTLE_MAX = 0.60   # khi quá nóng, giới hạn throttle ở mức này


def clamp_action(action: dict, state: dict):
    """Trả (action_an_toàn, danh_sách_lý_do_đã_chỉnh)."""
    a = dict(action)
    reasons = []

    # 1) Nhiệt độ: nếu CPU sắp chạm trần -> hạ throttle ngay
    temp = float(state.get("cpu_temp_c", state.get("temp_c", 0.0)))
    if temp >= MAX_CPU_TEMP_C:
        if a.get("cpu_throttle_max", 1.0) > HOT_THROTTLE_MAX:
            a["cpu_throttle_max"] = HOT_THROTTLE_MAX
            reasons.append(f"CPU {temp:.0f}°C >= {MAX_CPU_TEMP_C:.0f}°C -> ép throttle {HOT_THROTTLE_MAX}")

    # 2) Game đang chạy -> không tắt dGPU
    if bool(state.get("is_game", 0)) and int(round(a.get("gpu_switch", 2))) == 0:
        a["gpu_switch"] = 1
        reasons.append("đang game -> không tắt dGPU (giữ gpu_switch=1)")

    # 3) Không tự hạ brightness dưới ngưỡng (trừ khi user chủ động — không xử ở đây)
    if a.get("brightness_act", 1.0) < MIN_BRIGHTNESS:
        a["brightness_act"] = MIN_BRIGHTNESS
        reasons.append(f"brightness < {MIN_BRIGHTNESS} -> nâng lên ngưỡng tối thiểu")

    return a, reasons


def is_state_anomalous(state: dict):
    """Phát hiện anomaly để cân nhắc rollback (3.2/3.5)."""
    temp = float(state.get("cpu_temp_c", state.get("temp_c", 0.0)))
    if temp >= MAX_CPU_TEMP_C + 3:        # vượt trần rõ rệt
        return True, f"CPU quá nóng: {temp:.0f}°C"
    discharge = float(state.get("discharge_mw", 0.0))
    if discharge > 120000:                # xả bất thường cao
        return True, f"discharge bất thường: {discharge:.0f} mW"
    return False, ""


if __name__ == "__main__":
    print("BatteryClaw 3.5 — constraints self-test")

    # nóng -> ép throttle
    a, r = clamp_action({"cpu_throttle_max": 1.0}, {"cpu_temp_c": 97})
    print("  hot:", a["cpu_throttle_max"], r)
    assert a["cpu_throttle_max"] == HOT_THROTTLE_MAX

    # game -> không tắt dGPU
    a, r = clamp_action({"gpu_switch": 0}, {"is_game": 1})
    print("  game:", a["gpu_switch"], r)
    assert a["gpu_switch"] == 1

    # brightness quá thấp -> nâng
    a, r = clamp_action({"brightness_act": 0.05}, {})
    assert a["brightness_act"] == MIN_BRIGHTNESS

    # bình thường -> không đổi
    a, r = clamp_action({"cpu_throttle_max": 0.8, "gpu_switch": 1}, {"cpu_temp_c": 50})
    assert r == []

    bad, why = is_state_anomalous({"cpu_temp_c": 99})
    assert bad
    print("PASS ✓")
