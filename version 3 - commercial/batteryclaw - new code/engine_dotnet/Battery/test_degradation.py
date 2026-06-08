"""
Kiểm chứng thuật toán phân tích battery health của BatteryReport.cs
(PHASE 5 — mục 5.5) bằng Python — port y hệt logic thuần để chứng minh đúng.

Chạy: python test_degradation.py
"""

import datetime


def estimate_degradation_pct_per_year(design, history):
    """Port của BatteryReport.EstimateDegradationPctPerYear."""
    if design <= 0 or len(history) < 2:
        return 0.0
    history = sorted(history, key=lambda x: x[0])
    first, last = history[0], history[-1]
    days = (last[0] - first[0]).total_seconds() / 86400.0
    if days < 1:
        return 0.0
    first_pct = first[1] / design * 100.0
    last_pct = last[1] / design * 100.0
    drop = first_pct - last_pct
    return drop / days * 365.0


def build_health(design, full, history):
    """Port của BatteryReport.BuildHealth."""
    health = full / design * 100.0 if design > 0 else 0.0
    per_year = estimate_degradation_pct_per_year(design, history)
    in_1y = max(0.0, health - per_year)
    warn = health < 50.0
    return {
        "design": design, "full": full,
        "health_pct": round(health, 1),
        "in_1year_pct": round(in_1y, 1),
        "per_year": round(per_year, 2),
        "warning": warn,
    }


if __name__ == "__main__":
    print("Phase 5 — Battery degradation algorithm self-test\n")

    # Máy MSI của user: design 52007, full hiện tại 33026 -> health ~63.5%
    today = datetime.date.today()
    d = lambda days: datetime.datetime.combine(
        today - datetime.timedelta(days=days), datetime.time())

    # Lịch sử: 1 năm trước full=40000, nay 33026
    history = [(d(365), 40000), (d(180), 36500), (d(0), 33026)]
    h = build_health(52007, 33026, history)
    print("MSI i7-11800H (design 52007, full 33026):")
    print(f"  health     : {h['health_pct']}%")
    print(f"  giảm/năm   : {h['per_year']}%")
    print(f"  dự đoán 1y : {h['in_1year_pct']}%")
    print(f"  cảnh báo   : {h['warning']}")

    assert 63 <= h["health_pct"] <= 64, "health phải ~63.5%"
    # 40000->33026 trong 365 ngày = giảm (76.9%-63.5%) = ~13.4%/năm
    assert 13 <= h["per_year"] <= 14, f"degradation phải ~13.4%/năm, được {h['per_year']}"
    assert h["in_1year_pct"] < h["health_pct"], "dự đoán phải thấp hơn hiện tại"
    assert not h["warning"], "63.5% chưa dưới ngưỡng 50%"

    # Trường hợp pin yếu -> cảnh báo
    h2 = build_health(52007, 24000, history)
    print(f"\nPin yếu (full 24000): health {h2['health_pct']}% -> warning {h2['warning']}")
    assert h2["warning"]

    # Không đủ lịch sử -> degradation 0
    assert estimate_degradation_pct_per_year(52007, [(d(0), 33026)]) == 0.0

    print("\nPASS ✓  — thuật toán degradation đúng kỳ vọng")
