"""
BatteryClaw — commercial/profiles.py  (PHASE 6 — mục 6.3)

Profile người dùng: mỗi profile là một "khẩu vị" ưu tiên khác nhau, ánh xạ sang
trọng số reward (α/β/γ/δ của Phase 2) + thiên hướng chế độ (Phase 4 manager).

  • "Sinh viên"   : ưu tiên pin lâu trong lớp (tiết kiệm mạnh, chấp nhận hơi chậm)
  • "Văn phòng"   : cân bằng hiệu năng <-> pin
  • "Gaming"      : không tiết kiệm khi chơi game; tối đa khi dừng
  • "Thuyết trình": pin lâu nhất + màn sáng nhất (không để tối lúc trình chiếu)
  • Người dùng tự tạo profile -> AI học theo profile đó (lưu weights tùy chỉnh)

Trọng số reward khớp RewardWeights ở datacollector/reward.py (alpha/beta/gamma/delta).
"""

import json
import os

# (alpha=tiết kiệm, beta=phạt lag, gamma=bảo vệ pin, delta=ngữ cảnh)
BUILTIN_PROFILES = {
    "student": {
        "label": "Sinh viên",
        "desc": "Ưu tiên pin lâu trong lớp học",
        "weights": {"alpha": 1.5, "beta": 1.2, "gamma": 0.5, "delta": 0.5},
        "min_brightness": 0.30,
    },
    "office": {
        "label": "Văn phòng",
        "desc": "Cân bằng hiệu năng và pin",
        "weights": {"alpha": 1.0, "beta": 2.0, "gamma": 0.6, "delta": 0.5},
        "min_brightness": 0.40,
    },
    "gaming": {
        "label": "Gaming",
        "desc": "Không tiết kiệm khi chơi; tối đa khi dừng",
        "weights": {"alpha": 0.6, "beta": 3.0, "gamma": 0.3, "delta": 1.0},
        "min_brightness": 0.50,
    },
    "presentation": {
        "label": "Thuyết trình",
        "desc": "Pin lâu nhất, màn hình luôn sáng",
        "weights": {"alpha": 1.3, "beta": 2.5, "gamma": 0.4, "delta": 0.4},
        "min_brightness": 0.70,   # không để màn tối khi trình chiếu
    },
}

DEFAULT_PROFILE = "office"


class ProfileManager:
    def __init__(self, path=None):
        self.path = path
        self.active = DEFAULT_PROFILE
        self.custom = {}          # profile do user tạo
        if path and os.path.exists(path):
            self._load()

    def list_profiles(self):
        out = dict(BUILTIN_PROFILES)
        out.update(self.custom)
        return out

    def set_active(self, name):
        if name in BUILTIN_PROFILES or name in self.custom:
            self.active = name
            return True
        return False

    def get(self, name=None):
        name = name or self.active
        return self.custom.get(name) or BUILTIN_PROFILES.get(name) \
            or BUILTIN_PROFILES[DEFAULT_PROFILE]

    def weights(self, name=None):
        """Trả dict weights để dựng RewardWeights (Phase 2)."""
        return self.get(name)["weights"]

    def min_brightness(self, name=None):
        return self.get(name).get("min_brightness", 0.30)

    def create_custom(self, name, label, weights, min_brightness=0.30, desc=""):
        self.custom[name] = {
            "label": label, "desc": desc or "Profile tùy chỉnh",
            "weights": weights, "min_brightness": min_brightness,
        }

    def to_reward_weights(self, name=None):
        """Tiện ích: tạo thẳng RewardWeights nếu reward.py có sẵn."""
        w = self.weights(name)
        try:
            import sys
            sys.path.insert(0, os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "datacollector"))
            from reward import RewardWeights
            return RewardWeights(w["alpha"], w["beta"], w["gamma"], w["delta"])
        except Exception:
            return w   # fallback trả dict

    def save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"active": self.active, "custom": self.custom}, f,
                      ensure_ascii=False)

    def _load(self):
        with open(self.path, encoding="utf-8") as f:
            d = json.load(f)
        self.active = d.get("active", DEFAULT_PROFILE)
        self.custom = d.get("custom", {})


if __name__ == "__main__":
    import tempfile
    print("BatteryClaw 6.3 — ProfileManager self-test")
    p = os.path.join(tempfile.mkdtemp(), "profile.json")
    pm = ProfileManager(p)

    assert pm.active == "office"
    print("  profiles:", [v["label"] for v in pm.list_profiles().values()])

    # đổi sang gaming -> alpha thấp (ít tiết kiệm), delta cao (trọng ngữ cảnh)
    assert pm.set_active("gaming")
    w = pm.weights()
    print("  gaming weights:", w)
    assert w["alpha"] < 1.0 and w["delta"] >= 1.0

    # thuyết trình -> min brightness cao
    assert pm.min_brightness("presentation") == 0.70

    # tạo profile tùy chỉnh
    pm.create_custom("night", "Ban đêm", {"alpha": 2.0, "beta": 1.0,
                     "gamma": 0.5, "delta": 0.5}, min_brightness=0.2)
    assert pm.set_active("night") and pm.weights()["alpha"] == 2.0

    # to_reward_weights nối Phase 2
    rw = pm.to_reward_weights("student")
    print("  student -> RewardWeights:", rw)

    pm.save()
    pm2 = ProfileManager(p)
    assert pm2.active == "night" and "night" in pm2.custom
    print("PASS ✓")
