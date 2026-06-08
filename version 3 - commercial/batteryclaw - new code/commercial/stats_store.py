"""
BatteryClaw — commercial/stats_store.py  (PHASE 6 — nền dữ liệu cho 6.1/6.2)

Lưu THỐNG KÊ THEO NGÀY để dashboard hiển thị bằng chứng hữu hình:
  • "Hôm nay dùng được 5h23, hôm qua 4h12 -> +1h11"
  • discharge rate theo từng giờ trong ngày
  • lịch sử 30 ngày: tổng Wh tiết kiệm
  • dự đoán "với tốc độ hiện tại, pin còn dùng được X"

Đây là store NHẸ (JSON), tách khỏi replay buffer (P3) và parquet (P2) vốn là
dữ liệu thô cho training. Store này chỉ phục vụ hiển thị -> gọn, đọc nhanh.

Cấu trúc JSON:
{
  "days": {
     "2026-06-02": {
        "on_battery_sec": 19380,        # tổng giây chạy pin
        "saved_mwh": 4200,              # ước tính tiết kiệm
        "hourly_discharge_mw": [..24..],# trung bình discharge mỗi giờ
        "hourly_count": [..24..]        # số mẫu mỗi giờ (để tính trung bình)
     }, ...
  }
}
"""

import json
import os
import datetime


class StatsStore:
    def __init__(self, path):
        self.path = path
        self.data = {"days": {}}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"days": {}}

    # ── ghi nhận một mẫu (gọi mỗi chu kỳ từ engine/brain) ───────────────────
    def record(self, discharge_mw, on_battery, saved_mwh=0.0,
               now=None, interval_sec=10):
        now = now or datetime.datetime.now()
        day = now.strftime("%Y-%m-%d")
        hour = now.hour
        d = self.data["days"].setdefault(day, self._empty_day())

        if on_battery:
            d["on_battery_sec"] += interval_sec
        d["saved_mwh"] += saved_mwh

        # cập nhật trung bình động discharge theo giờ
        c = d["hourly_count"][hour]
        prev = d["hourly_discharge_mw"][hour]
        d["hourly_discharge_mw"][hour] = (prev * c + discharge_mw) / (c + 1)
        d["hourly_count"][hour] = c + 1

    def _empty_day(self):
        return {
            "on_battery_sec": 0,
            "saved_mwh": 0.0,
            "hourly_discharge_mw": [0.0] * 24,
            "hourly_count": [0] * 24,
        }

    # ── truy vấn cho dashboard ──────────────────────────────────────────────
    def day(self, day_str):
        return self.data["days"].get(day_str)

    def today_vs_yesterday(self, now=None):
        """Trả (giây hôm nay, giây hôm qua, chênh lệch giây)."""
        now = now or datetime.datetime.now()
        today = now.strftime("%Y-%m-%d")
        yest = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        t = self.data["days"].get(today, self._empty_day())["on_battery_sec"]
        y = self.data["days"].get(yest, self._empty_day())["on_battery_sec"]
        return t, y, t - y

    def last_n_days_saved(self, n=30, now=None):
        """Trả list [(ngày, mWh tiết kiệm)] cho n ngày gần nhất."""
        now = now or datetime.datetime.now()
        out = []
        for i in range(n - 1, -1, -1):
            day = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            d = self.data["days"].get(day)
            out.append((day, round(d["saved_mwh"], 0) if d else 0))
        return out

    def total_saved_wh(self, n=30, now=None):
        return round(sum(mwh for _, mwh in self.last_n_days_saved(n, now)) / 1000.0, 1)

    def hourly_discharge_today(self, now=None):
        now = now or datetime.datetime.now()
        day = now.strftime("%Y-%m-%d")
        d = self.data["days"].get(day)
        return [round(x) for x in d["hourly_discharge_mw"]] if d else [0] * 24

    def predict_remaining(self, battery_mwh, now=None):
        """Dự đoán pin còn dùng được bao lâu, dựa discharge trung bình gần đây."""
        now = now or datetime.datetime.now()
        day = now.strftime("%Y-%m-%d")
        d = self.data["days"].get(day)
        if not d:
            return None
        # discharge trung bình của các giờ có dữ liệu
        vals = [v for v, c in zip(d["hourly_discharge_mw"], d["hourly_count"]) if c > 0]
        if not vals:
            return None
        avg = sum(vals) / len(vals)
        if avg <= 0:
            return None
        hours = battery_mwh / avg
        return hours

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # giữ tối đa 90 ngày để file không phình
        days = self.data["days"]
        if len(days) > 90:
            for k in sorted(days.keys())[:-90]:
                del days[k]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)


if __name__ == "__main__":
    import tempfile
    print("BatteryClaw 6 — StatsStore self-test")
    p = os.path.join(tempfile.mkdtemp(), "stats.json")
    s = StatsStore(p)

    base = datetime.datetime(2026, 6, 2, 9, 0, 0)
    # hôm qua: chạy pin 4h12 (15120s)
    yest = base - datetime.timedelta(days=1)
    for _ in range(1512):
        s.record(15000, on_battery=True, saved_mwh=2, now=yest, interval_sec=10)
    # hôm nay: chạy pin 5h23 (19380s), discharge giờ 9 = 14000
    for _ in range(1938):
        s.record(14000, on_battery=True, saved_mwh=3, now=base, interval_sec=10)

    t, y, diff = s.today_vs_yesterday(now=base)
    print(f"  hôm nay {t}s, hôm qua {y}s, chênh {diff}s ({diff//60} phút)")
    assert t == 19380 and y == 15120 and diff == 4260

    rem = s.predict_remaining(28000, now=base)
    print(f"  dự đoán còn: {rem:.2f}h với discharge ~14000mW")
    assert 1.9 < rem < 2.1   # 28000/14000 = 2.0h

    saved = s.total_saved_wh(now=base)
    print(f"  tổng tiết kiệm: {saved} Wh")
    assert saved > 0

    hourly = s.hourly_discharge_today(now=base)
    assert hourly[9] == 14000 and len(hourly) == 24

    s.save()
    s2 = StatsStore(p)
    assert s2.today_vs_yesterday(now=base)[0] == 19380
    print("PASS ✓")
