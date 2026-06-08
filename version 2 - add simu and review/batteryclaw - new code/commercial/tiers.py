"""
BatteryClaw — commercial/tiers.py  (PHASE 6 — mục 6.5)

Mô hình kinh doanh: khóa tính năng theo tier. Map từ tier -> tập tính năng bật.
Nối với server bán key (tier có thể trả về khi /api/verify).

  Tier 1 — Free        : chỉ CPU throttle cơ bản
  Tier 2 — Basic (29k) : + GPU switching, dashboard, pin health
  Tier 3 — Pro (59k)   : + online learning, profile tùy chỉnh, mọi thứ Phase 1-3
  Tier 4 — Lifetime    : tất cả + update vĩnh viễn

File chỉ lo "tier nào mở tính năng gì" + kiểm tra. Logic dùng ở app/engine để
quyết định có chạy một tính năng hay không.
"""

FREE     = "free"
BASIC    = "basic"
PRO      = "pro"
LIFETIME = "lifetime"

# Tính năng (feature flags)
F_CPU_THROTTLE   = "cpu_throttle"     # tiết kiệm CPU cơ bản
F_GPU_SWITCH     = "gpu_switch"       # tắt/bật dGPU
F_DASHBOARD      = "dashboard"        # dashboard thống kê
F_BATTERY_HEALTH = "battery_health"   # theo dõi sức khỏe pin
F_ONLINE_LEARN   = "online_learning"  # AI học theo máy (Phase 3)
F_CUSTOM_PROFILE = "custom_profile"   # tự tạo profile
F_PLANNING       = "planning"         # model-based planning (Phase 4)

TIER_FEATURES = {
    FREE:     {F_CPU_THROTTLE},
    BASIC:    {F_CPU_THROTTLE, F_GPU_SWITCH, F_DASHBOARD, F_BATTERY_HEALTH},
    PRO:      {F_CPU_THROTTLE, F_GPU_SWITCH, F_DASHBOARD, F_BATTERY_HEALTH,
              F_ONLINE_LEARN, F_CUSTOM_PROFILE},
    LIFETIME: {F_CPU_THROTTLE, F_GPU_SWITCH, F_DASHBOARD, F_BATTERY_HEALTH,
              F_ONLINE_LEARN, F_CUSTOM_PROFILE, F_PLANNING},
}

TIER_LABELS = {
    FREE: "Miễn phí", BASIC: "Basic", PRO: "Pro", LIFETIME: "Lifetime",
}

TIER_PRICE_VND = {FREE: 0, BASIC: 29000, PRO: 59000, LIFETIME: 499000}


class TierGate:
    def __init__(self, tier=FREE):
        self.tier = tier if tier in TIER_FEATURES else FREE

    def set_tier(self, tier):
        self.tier = tier if tier in TIER_FEATURES else FREE

    def can(self, feature):
        """Tier hiện tại có mở tính năng này không?"""
        return feature in TIER_FEATURES.get(self.tier, set())

    def features(self):
        return sorted(TIER_FEATURES.get(self.tier, set()))

    def require(self, feature):
        """Trả (ok, thông điệp nâng cấp nếu bị khóa)."""
        if self.can(feature):
            return True, ""
        # tìm tier rẻ nhất mở tính năng này để gợi ý nâng cấp
        for tier in (BASIC, PRO, LIFETIME):
            if feature in TIER_FEATURES[tier]:
                return False, (f"Tính năng này cần gói {TIER_LABELS[tier]} "
                               f"({TIER_PRICE_VND[tier]:,}đ).")
        return False, "Tính năng chưa khả dụng."


if __name__ == "__main__":
    print("BatteryClaw 6.5 — TierGate self-test")

    free = TierGate(FREE)
    assert free.can(F_CPU_THROTTLE)
    assert not free.can(F_GPU_SWITCH)
    ok, msg = free.require(F_GPU_SWITCH)
    print("  free xài GPU switch:", ok, "|", msg)
    assert not ok and "Basic" in msg

    pro = TierGate(PRO)
    assert pro.can(F_ONLINE_LEARN) and pro.can(F_CUSTOM_PROFILE)
    assert not pro.can(F_PLANNING)   # planning chỉ Lifetime
    ok, msg = pro.require(F_PLANNING)
    print("  pro xài planning:", ok, "|", msg)
    assert not ok and "Lifetime" in msg

    life = TierGate(LIFETIME)
    assert all(life.can(f) for f in
               [F_CPU_THROTTLE, F_GPU_SWITCH, F_ONLINE_LEARN, F_PLANNING])

    # tier rác -> về free
    assert TierGate("hacker").tier == FREE
    print("  giá các tier:", TIER_PRICE_VND)
    print("PASS ✓")
