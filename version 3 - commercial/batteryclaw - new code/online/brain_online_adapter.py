"""
BatteryClaw — online/brain_online_adapter.py  (PHASE 3 — cầu nối)

Nối OnlineLearner (Phase 3) với rl_brain (deploy) mà KHÔNG làm rl_brain phình to.
rl_brain chỉ cần gọi 3 thứ:
  • adapter.refine(command, state)  -> command an toàn (mode + constraints)
  • adapter.observe(...)            -> tích transition cho buffer/pattern
  • adapter.tick()                  -> fine-tune khi máy nhàn

Chuyển đổi giữa "command JSON" của rl_brain và "action dict schema" của Phase 3
gói gọn tại đây để hai bên không phụ thuộc nhau.
"""

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from online_loop import OnlineLearner   # noqa: E402


def command_to_action(cmd: dict) -> dict:
    """command JSON (rl_brain) -> action dict (schema Phase 3)."""
    return {
        "cpu_throttle_max": cmd.get("cpu_max", 100) / 100.0,
        "brightness_act"  : cmd.get("brightness", 80) / 100.0
                            if cmd.get("brightness", -1) >= 0 else 0.8,
        "defer_tasks"     : 1.0 if cmd.get("defer") else 0.0,
        "gpu_switch"      : float(cmd.get("gpu_switch", 2)),
        "refresh_mode"    : float(cmd.get("refresh_rate", 2)),
        "wifi_power_save" : 1.0 if cmd.get("wifi_save") else 0.0,
        "charge_limit_on" : 1.0 if cmd.get("charge_limit", -1) >= 0 else 0.0,
    }


def action_to_command(cmd_in: dict, action: dict) -> dict:
    """action dict (đã chỉnh an toàn) -> ghi đè lại command JSON."""
    cmd = dict(cmd_in)
    cmd["cpu_max"]      = int(round(action["cpu_throttle_max"] * 100))
    cmd["brightness"]   = int(round(action["brightness_act"] * 100))
    cmd["defer"]        = bool(action["defer_tasks"] > 0.5)
    cmd["gpu_switch"]   = int(round(action["gpu_switch"]))
    cmd["refresh_rate"] = int(round(action["refresh_mode"]))
    cmd["wifi_save"]    = bool(action["wifi_power_save"] > 0.5)
    cmd["charge_limit"] = 80 if action["charge_limit_on"] > 0.5 else -1
    return cmd


class BrainOnlineAdapter:
    def __init__(self, state_dir, policy=None, model_path=None):
        self.learner = OnlineLearner(state_dir, policy=policy, model_path=model_path)
        self._prev_obs = None
        self._prev_action_vec = None

    def refine(self, command: dict, state: dict) -> dict:
        """Áp mode (3.4) + ràng buộc an toàn (3.5) lên command trước khi gửi."""
        action = command_to_action(command)
        safe, reasons = self.learner.finalize_action(action, state)
        return action_to_command(command, safe)

    def observe(self, obs_vec, action_vec, reward, next_obs_vec, state: dict):
        """Tích transition. obs/action là numpy vector (15,) / (7,)."""
        wl = int(round(float(state.get("workload_norm", 0)) * 4)) \
             if "workload_norm" in state else None
        # suy workload từ cpu_load nếu không có sẵn
        if wl is None:
            cl = state.get("cpu_load", 30)
            wl = 0 if cl < 10 else 1 if cl < 30 else 2 if cl < 55 else 3 if cl < 80 else 4
        import datetime
        hour = datetime.datetime.now().hour
        self.learner.observe(obs_vec, action_vec, reward, next_obs_vec,
                             hour=hour, workload_id=wl,
                             discharge_mw=state.get("discharge_mw", 0.0))

    def tick(self):
        """Gọi định kỳ: fine-tune nếu máy đã nhàn đủ lâu."""
        return self.learner.maybe_finetune()

    def mark_activity(self):
        self.learner.mark_activity()

    def feedback(self, kind):
        return self.learner.user_feedback(kind)

    def set_mode(self, mode, minutes=30):
        self.learner.set_mode(mode, minutes)

    def save(self):
        self.learner.save()


if __name__ == "__main__":
    import tempfile
    print("BatteryClaw Phase 3 — BrainOnlineAdapter self-test")

    ad = BrainOnlineAdapter(os.path.join(tempfile.mkdtemp(), "state"))

    # refine: game + nóng -> command phải an toàn
    cmd = {"cpu_max": 100, "brightness": 90, "gpu_switch": 0,
           "refresh_rate": 2, "defer": False}
    safe = ad.refine(cmd, {"cpu_temp_c": 98, "is_game": 1})
    print("  refined cmd:", safe)
    assert safe["gpu_switch"] == 1 and safe["cpu_max"] <= 60

    # observe + feedback
    obs = np.zeros(15, dtype=np.float32)
    act = np.zeros(7, dtype=np.float32)
    ad.observe(obs, act, 0.1, obs, {"cpu_load": 70, "discharge_mw": 40000})
    assert ad.feedback("save")
    assert len(ad.learner.buffer) == 2     # 1 observe + 1 feedback
    print("  buffer:", len(ad.learner.buffer))
    print("PASS ✓")
