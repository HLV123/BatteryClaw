"""
BatteryClaw — tests/test_core.py  (QUALITY-02)

Unit test cho cac ham core va BAT BIEN quan trong nhat — chay khong can
Windows/engine. Muc tieu: bat loi hoi quy khi refactor (vd doi thu tu obs vector).

Chay:
    python tests/test_core.py
    (hoac: pytest tests/ neu da cai pytest)
"""

import os
import sys
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("datacollector", "simulator", "online/safety", "online/buffer"):
    sys.path.insert(0, os.path.join(_ROOT, sub))


def test_obs_schema_15_dim():
    from schema import STATE_COLUMNS, ACTION_COLUMNS
    assert len(STATE_COLUMNS) == 15, "obs phai 15 chieu"
    assert len(ACTION_COLUMNS) == 7, "action phai 7 chieu"
    # thu tu battery_pct dau, discharge o index 9 (quan trong cho world model)
    assert STATE_COLUMNS[0] == "battery_pct"
    assert STATE_COLUMNS[9] == "discharge_norm"


def test_classify_workload_cpu_gpu():
    from schema import classify_workload
    assert classify_workload(5, 0) == 0           # idle that
    assert classify_workload(5, 15000) == 4       # CPU thap + GPU cao = render
    assert classify_workload(90, 0) == 4          # CPU cao
    assert classify_workload(40, 0) == 2          # office
    assert classify_workload(5, 0, "valorant.exe") == 4   # game theo ten
    # [MINOR-03] CPU vua + GPU thap -> office, khong nham game
    assert classify_workload(40, 3000) == 2
    # [MINOR-03] nguong bien GPU 8000mW: 7999 chua tinh la nang, 8000 thi co
    assert classify_workload(5, 7999) == 0        # duoi nguong -> idle (CPU thap)
    assert classify_workload(5, 8000) == 4        # dung nguong -> render


def test_env_obs_range_and_shape():
    from battery_env import BatteryClawEnv
    env = BatteryClawEnv()
    obs, _ = env.reset(seed=0)
    assert obs.shape == (15,), "obs env phai 15 chieu"
    assert obs.min() >= -0.001 and obs.max() <= 1.001, "obs phai trong [0,1]"
    # buoc thu vai action ngau nhien, obs van trong [0,1]
    for _ in range(20):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        assert obs.shape == (15,)
        assert obs.min() >= -0.001 and obs.max() <= 1.001
        if term or trunc:
            break


def test_env_action_space_bounds():
    from battery_env import BatteryClawEnv
    env = BatteryClawEnv()
    lo = env.action_space.low
    hi = env.action_space.high
    assert lo[0] >= 0.2 - 1e-6 and hi[0] <= 1.0 + 1e-6   # throttle [0.2,1]
    assert lo[1] >= 0.3 - 1e-6 and hi[1] <= 1.0 + 1e-6   # brightness [0.3,1]


def test_refresh_mode_consistency():
    # [BUG-06] mode<->hz phai nhat quan
    from battery_env import REFRESH_MODE_TO_HZ, PANEL_MAX_HZ
    assert REFRESH_MODE_TO_HZ[0] == 60
    assert REFRESH_MODE_TO_HZ[1] == 120
    assert REFRESH_MODE_TO_HZ[2] == PANEL_MAX_HZ


def test_reward_edge_cases():
    from reward import compute_reward, RewardWeights
    w = RewardWeights()
    # tat dGPU khi game -> context phat nang
    _, p_bad = compute_reward({"workload_id": 4, "discharge_mw": 40000,
        "cpu_throttle_max": 0.5, "gpu_switch": 0, "is_game": 1,
        "plugged": 0, "battery_pct": 0.5}, w)
    assert p_bad["r_context"] <= -1.0 + 1e-6, "tat dGPU khi game phai bi phat"
    # giu dGPU khi game -> context duong
    _, p_ok = compute_reward({"workload_id": 4, "discharge_mw": 40000,
        "cpu_throttle_max": 0.95, "gpu_switch": 1, "is_game": 1,
        "plugged": 0, "battery_pct": 0.5}, w)
    assert p_ok["r_context"] > 0
    # dang sac, giu pin <80% co charge limit -> longevity duong
    _, p_long = compute_reward({"workload_id": 2, "discharge_mw": 0,
        "cpu_throttle_max": 0.8, "gpu_switch": 1, "is_game": 0,
        "plugged": 1, "charge_limit_on": 1, "battery_pct": 0.75}, w)
    assert p_long["r_longevity"] > 0


def test_constraints_hard_limits():
    from constraints import clamp_action, MAX_CPU_TEMP_C, MIN_BRIGHTNESS
    # nong -> ep throttle
    a, reasons = clamp_action({"cpu_throttle_max": 1.0}, {"cpu_temp_c": 97})
    assert a["cpu_throttle_max"] <= 0.6
    # game -> khong tat dGPU
    a, _ = clamp_action({"gpu_switch": 0}, {"is_game": 1})
    assert a["gpu_switch"] == 1
    # brightness san
    a, _ = clamp_action({"brightness_act": 0.05}, {})
    assert a["brightness_act"] >= MIN_BRIGHTNESS - 1e-9


def test_replay_buffer_rolling():
    from replay_buffer import ReplayBuffer
    buf = ReplayBuffer(capacity=5)
    for i in range(8):
        buf.add(np.full(15, i, dtype=np.float32), np.zeros(7, dtype=np.float32),
                float(i), np.full(15, i, dtype=np.float32))
    assert len(buf) == 5, "buffer phai gioi han o capacity"


def test_cpp_state_json_has_all_obs_fields():
    """[TODO-02] Bao ve dong bo C++ <-> Python o tang test: parse stateToJson
    trong batteryclaw_main.cpp, dam bao no XUAT du cac field ma rl_brain.state_to_obs
    DOC. Khong sinh header, nhung bat duoc khi C++ quen field."""
    import re
    cpp = os.path.join(_ROOT, "engine", "src", "batteryclaw_main.cpp")
    if not os.path.exists(cpp):
        return  # khong co source C++ -> bo qua
    src = open(cpp, encoding="utf-8").read()
    json_keys = set(re.findall(r'\\"(\w+)\\":', src))
    needed = {"batt_pct", "cpu_load", "temp_c", "brightness", "cpu_max",
              "gpu_type", "gpu_power_mw", "discharge_mw", "refresh_hz",
              "wifi", "audio", "ram_pct", "tod"}
    missing = needed - json_keys
    assert not missing, f"C++ stateToJson thieu field rl_brain can: {missing}"


def test_normalization_constants_shared():
    """[REMAIN-02 + MINOR-A/B] MOI consumer chuan hoa GPU/DISCHARGE phai dung
    CHUNG gia tri tu constants. Lech -> obs/reward scale khac nhau giua thu thap,
    train (env, world model) va suy luan -> model sai."""
    sys.path.insert(0, os.path.join(_ROOT, "commons"))
    sys.path.insert(0, os.path.join(_ROOT, "datacollector"))
    sys.path.insert(0, os.path.join(_ROOT, "worldmodel"))
    import constants
    import battery_env
    # battery_env (env train policy)
    assert battery_env.GPU_POWER_MAX_MW == constants.GPU_POWER_MAX_MW
    assert battery_env.DISCHARGE_MAX_MW == constants.DISCHARGE_MAX_MW
    # data_collector (ghi transition ra parquet) — MINOR-A
    import data_collector
    assert data_collector.GPU_POWER_MAX_MW == constants.GPU_POWER_MAX_MW
    assert data_collector.DISCHARGE_MAX_MW == constants.DISCHARGE_MAX_MW
    # wm_env (denorm discharge khi train world model) — MINOR-B
    import wm_env
    assert wm_env.DISCHARGE_MAX_MW == constants.DISCHARGE_MAX_MW
    # Phase 4: worker (hierarchy) + mpc_planner (planning) — FIND-02/03
    sys.path.insert(0, os.path.join(_ROOT, "advanced", "hierarchy"))
    sys.path.insert(0, os.path.join(_ROOT, "advanced", "planning"))
    import worker as _wk
    import mpc_planner as _mpc
    assert _wk.DISCHARGE_MAX_MW == constants.DISCHARGE_MAX_MW
    assert _mpc.DISCHARGE_MAX_MW == constants.DISCHARGE_MAX_MW


def test_csharp_discharge_const_matches_python():
    """[FIND-01] C# Program.cs giu ban sao DischargeMaxMw (khong import duoc Python).
    Test nay parse gia tri trong .cs va so voi constants.DISCHARGE_MAX_MW de bat
    khi hai ben lech nhau."""
    import re
    sys.path.insert(0, os.path.join(_ROOT, "commons"))
    import constants
    cs = os.path.join(_ROOT, "engine_dotnet", "Program.cs")
    if not os.path.exists(cs):
        return  # khong co engine C# -> bo qua
    src = open(cs, encoding="utf-8").read()
    m = re.search(r"DischargeMaxMw\s*=\s*([\d.]+)f?", src)
    assert m, "khong tim thay const DischargeMaxMw trong Program.cs"
    assert float(m.group(1)) == constants.DISCHARGE_MAX_MW, \
        f"C# DischargeMaxMw={m.group(1)} != Python {constants.DISCHARGE_MAX_MW}"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
        except Exception as e:
            print(f"  [ERR ] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} test PASS")
    return passed == len(tests)


if __name__ == "__main__":
    print("BatteryClaw — unit tests (QUALITY-02)\n")
    ok = _run_all()
    sys.exit(0 if ok else 1)
