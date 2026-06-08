# BatteryClaw — Review code TỪNG DÒNG (Phần 7: FILE 37-42)

Tiếp nối phần 1-6 (file 1-36). Phần này: 3 file datacollector cuối (schema, reward,
dataset_uploader) + 3 file commercial (stats_store, profiles, tiers).

Định dạng: trích dòng (kèm số dòng) → giải thích ngay dưới.

═══════════════════════════════════════════════════════════════════════════════
# FILE 37/48 — datacollector/schema.py  (137 dòng — HỢP ĐỒNG DỮ LIỆU)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  """ docstring """ — định nghĩa CHUẨN transition, dùng chung datacollector/worldmodel/reward/simulator
15-26 import; nạp ngưỡng workload (GPU_HEAVY_MW, CPU_*_PCT) từ commons; fallback
```
**Dòng 1-26:** "Hợp đồng dữ liệu" cho 1 transition (s,a,r,s'), dùng chung 4 nơi. Thứ tự
15 obs PHẢI khớp battery_env._get_obs + rl_brain.state_to_obs — chỉ thêm vào cuối, không
đổi thứ tự. Nạp ngưỡng phân loại workload từ commons.

```
28-45 STATE_COLUMNS (15): battery_pct, cpu_load, cpu_temp_norm, workload_id, brightness, throttle_max, time_norm, gpu_type_norm, gpu_power_norm, discharge_norm, refresh_norm, wifi, audio, ram, tod
```
**Dòng 28-45:** 15 trường observation đúng thứ tự Phase 1 (có comment index từng cái).
⚠ **Dòng 40:** comment ghi refresh_norm = (hz-60)/105 — tức 105 = 165-60. Khớp với điểm
lệch 165 ở data_collector dòng 88 (cùng vấn đề). battery_env/rl_brain dùng 144-60=84. Nên
thống nhất về 144.

```
48-56 ACTION_COLUMNS (7): cpu_throttle_max, brightness_act, defer_tasks, gpu_switch, refresh_mode, wifi_power_save, charge_limit_on
```
**Dòng 48-56:** 7 trường action đúng thứ tự Phase 1 (kèm range/ý nghĩa từng cái).

```
58-70 RAW_COLUMNS (10): discharge_mw, gpu_power_mw, gpu_type, refresh_hz, cpu_temp_c, battery_mwh, plugged, charging, fg_app, is_game
```
**Dòng 58-70:** Trường thô (chưa chuẩn hóa) cần cho reward thật + world model. discharge_mw
là ground truth cho reward chính.

```
72-86 REWARD_COLUMNS (5): reward + 4 thành phần; META_COLUMNS: ts_ms, session_id, is_next
```
**Dòng 72-86:** Trường reward (điền sau khi tính) + metadata (timestamp, phiên, cờ next).

```
88-99 NEXT_STATE_COLUMNS = "next_"+state; ALL_COLUMNS = meta+state+action+raw+reward+next
```
**Dòng 88-99:** Một transition lưu phẳng: meta + state(15) + action(7) + raw(10) +
reward(5) + next_state(15, tiền tố "next_"). Tổng các cột.

```
101-111 GAME_HINTS (danh sách process game); is_game_process(name): tên chứa hint nào không
```
**Dòng 101-111:** Danh sách tên process game (valorant, dota, genshin...). is_game_process
kiểm tên app có phải game.

```
114-129 [DESIGN-06+BUG-04] classify_workload(cpu, gpu_power, fg_app): NGUỒN DUY NHẤT, kết hợp CPU+GPU
120-123 GPU≥8W hoặc app game → 4 (game/render)
125-129 còn lại theo CPU%: <10 idle, <30 browse, <55 office, <80 compile, else 4
```
**Dòng 114-129:** Phân loại workload — NGUỒN DUY NHẤT dùng chung. Kết hợp GPU: CPU 5%
nhưng GPU 100% (xem video/render) không bị nhầm "idle". GPU nặng hoặc app game → 4. Còn
lại theo CPU. Đây là fix BUG-04 (trước chỉ dựa CPU).

```
132-137 empty_row(): dict đủ cột giá trị mặc định 0/''
```
**Dòng 132-137:** Tạo dòng rỗng đủ cột (số=0, fg_app/session_id="") để điền.

**TÓM TẮT:** Hợp đồng dữ liệu trung tâm — định nghĩa 15 obs + 7 action + raw + reward, và
classify_workload dùng chung. Chứa điểm lệch refresh 165 (dòng 40). LIÊN KẾT: data_collector,
world_model, reward, wm_env đều import. Là single-source cho phân loại workload.

═══════════════════════════════════════════════════════════════════════════════
# FILE 38/48 — datacollector/reward.py  (172 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-22  """ docstring """ — reward THẬT từ dữ liệu đo: R = α·primary + β·comfort + γ·longevity + δ·context
24-32 @dataclass RewardWeights: alpha=1, beta=2, gamma=0.5, delta=0.5
```
**Dòng 1-32:** [2.3] Reward không còn ước tính mà tính trực tiếp từ dữ liệu đo thật (ACPI).
4 thành phần: primary (tiết kiệm điện thật), comfort (phạt lag), longevity (bảo vệ pin),
context (phù hợp ngữ cảnh GPU). Trọng số α/β/γ/δ chỉnh được. Lưu ý: cấu trúc giống reward
trong battery_env nhưng tính từ số đo thật thay vì mô phỏng.

```
35-44 BASELINE_DISCHARGE_MW theo workload: idle 18W, browse 30W, office 38W, compile 62W, game 90W
46-47 LAG_THRESHOLD: throttle tối thiểu mỗi workload không gây lag
```
**Dòng 35-47:** Baseline discharge (khi KHÔNG có BatteryClaw) theo workload — lấy từ
profile máy MSI, Phase 2 sẽ đo thật từng máy. LAG_THRESHOLD = throttle tối thiểu mỗi
workload (game cần 0.95, idle chỉ 0.20).

```
50-55 _workload_id(row): lấy workload_id an toàn (int)
58-68 r_primary(row): -discharge/baseline; đang sạc (discharge=0) → 0 (không phạt)
```
**Dòng 50-68:** primary = −discharge/baseline (xả càng thấp so với baseline → reward càng
gần 0 = tốt). Đang sạc thì không phạt xả.

```
71-79 r_comfort(row): throttle dưới ngưỡng workload → phạt tỉ lệ thiếu hụt
```
**Dòng 71-79:** comfort phạt lag: nếu throttle < ngưỡng workload cần → phạt theo mức
thiếu. Đủ throttle → 0.

```
82-92 r_longevity(row): cắm sạc + charge_limit + pin≤80% → +1; cắm sạc + pin≥98% → -0.5
```
**Dòng 82-92:** longevity thưởng giữ pin ~80% khi cắm sạc (tốt cho tuổi thọ), phạt sạc
đầy 100% liên tục. Giống r_long trong battery_env.

```
95-111 r_context(row): game+tắt dGPU → -1 (rất sai); game+giữ dGPU → +0.5; không game+tắt dGPU → +0.5 (tiết kiệm đúng)
```
**Dòng 95-111:** context thưởng/phạt theo ngữ cảnh GPU: tắt dGPU khi game = rất sai (−1),
giữ dGPU khi game = đúng (+0.5), tắt dGPU khi không cần = tiết kiệm đúng (+0.5).

```
114-130 compute_reward(row, w): tính 4 thành phần, tổng có trọng số; trả (total, parts dict)
133-143 fill_rewards(df, w): điền cột reward cho cả DataFrame (build dataset)
```
**Dòng 114-143:** compute_reward gộp 4 thành phần với trọng số (đây là cái rl_brain Phase
3 gọi). fill_rewards điền reward cho cả dataset (sau khi thu dữ liệu thụ động reward trống).

```
146-172 self-test: 4 ca (browse tiết kiệm, game đúng, game sai, cắm sạc bảo vệ pin) → in reward + thành phần
```
**Dòng 146-172:** Test 4 tình huống minh họa, in reward tổng + từng thành phần. Không
assert (chỉ in để xem mắt).

**TÓM TẮT:** [2.3] Hàm reward thật (4 thành phần có trọng số) tính từ dữ liệu đo. Dùng
cả cho build dataset world model lẫn online learning. LIÊN KẾT: rl_brain (Phase 3 gọi
compute_reward), wm_env (reward env), schema (workload_id), world_model. Là bản "thật"
của công thức reward trong battery_env.

═══════════════════════════════════════════════════════════════════════════════
# FILE 39/48 — datacollector/dataset_uploader.py  (108 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-15  """ docstring """ — gửi dữ liệu lên server dạng ẨN DANH để gom dataset chung
17-24 import; DROP_COLS = {fg_app, session_id}
```
**Dòng 1-24:** [2.4] Gửi dữ liệu thu thập lên server ẩn danh. KHÔNG gửi email/machine_id
gốc/tên app. Ẩn danh: device_hash = sha256(machine_id+salt)[:16] (không đảo ngược),
device_class mô tả phần cứng chung để gom nhóm, bỏ cột fg_app/session_id.

```
27-28 device_hash(machine_id, salt): sha256 cắt 16 ký tự
31-49 load_rows(data_dir): đọc parquet (pandas) hoặc jsonl → list dict
```
**Dòng 27-49:** Băm machine_id (1 chiều, không lần ra máy). Đọc dữ liệu từ parquet/jsonl
thành list dòng.

```
52-57 anonymize(rows): bỏ cột trong DROP_COLS (fg_app, session_id)
```
**Dòng 52-57:** Ẩn danh: loại tên app + id phiên trước khi gửi (server lọc lại lần nữa).

```
60-87 main: argparse --server/--data/--machine-id/--device-class/--batch/--dry-run; load + anonymize; dry-run in mẫu
```
**Dòng 60-87:** CLI. --dry-run chỉ in mẫu 1 dòng ẩn danh + số dòng sẽ gửi (không gửi
thật). Thiếu --server → báo dùng dry-run.

```
89-104 gửi từng batch POST /api/dataset/upload với device_hash + device_class + rows; in số server nhận
```
**Dòng 89-104:** Gửi dữ liệu theo batch (mặc định 2000 dòng/lần) tới server. Mỗi batch
gửi kèm device_hash + device_class (không kèm machine_id gốc). Lỗi → dừng.

**TÓM TẮT:** [2.4] Gửi dữ liệu ẩn danh lên server để gom dataset đa máy (train model
chung tốt hơn). Chú trọng quyền riêng tư (băm 1 chiều, bỏ tên app). LIÊN KẾT: data_collector
(nguồn parquet), server/server.py (endpoint /api/dataset/upload nhận). Lưu ý: người dùng
đã từ chối VPS+HTTPS nên tính năng đa máy này hiện chạy localhost; là hạ tầng sẵn.

───────────────────────────────────────────────────────────────────────────────
HẾT NHÓM datacollector. Sang nhóm commercial (stats_store, profiles, tiers, notifications).
───────────────────────────────────────────────────────────────────────────────

═══════════════════════════════════════════════════════════════════════════════
# FILE 40/48 — commercial/stats_store.py  (161 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-24  """ docstring """ — lưu thống kê theo NGÀY cho dashboard (bằng chứng hữu hình); cấu trúc JSON
26-40 StatsStore.__init__(path): nạp JSON {"days": {...}} nếu có
```
**Dòng 1-40:** [6.1/6.2] Lưu thống kê theo ngày cho dashboard hiển thị bằng chứng hữu
hình ("hôm nay dùng 5h23, hôm qua 4h12 → +1h11"). Store nhẹ (JSON), tách khỏi replay
buffer/parquet (dữ liệu training). Cấu trúc: mỗi ngày có giây chạy pin, mWh tiết kiệm,
discharge trung bình 24 giờ + số mẫu.

```
43-58 record(discharge_mw, on_battery, saved_mwh, interval): cập nhật giây pin + saved + trung bình động discharge theo giờ
```
**Dòng 43-58:** Ghi nhận 1 mẫu mỗi chu kỳ. Cộng giây chạy pin (nếu on_battery) + saved.
Cập nhật trung bình động discharge theo giờ (công thức trung bình tích lũy chính xác:
(prev×count + mới)/(count+1)).

```
60-66 _empty_day(): dict ngày rỗng (on_battery_sec, saved_mwh, hourly arrays)
69-79 day(day_str); today_vs_yesterday(): giây hôm nay/hôm qua/chênh
```
**Dòng 60-79:** Tạo ngày rỗng. today_vs_yesterday so giây chạy pin 2 ngày — đây là số
"bằng chứng" chính cho người dùng thấy giá trị app.

```
81-92 last_n_days_saved(n=30): list (ngày, mWh tiết kiệm); total_saved_wh: tổng Wh
94-98 hourly_discharge_today(): mảng 24 giờ discharge hôm nay
```
**Dòng 81-98:** Lịch sử 30 ngày tiết kiệm + tổng Wh. discharge theo giờ hôm nay (cho biểu
đồ dashboard).

```
100-115 predict_remaining(battery_mwh): pin / discharge trung bình các giờ có dữ liệu → giờ còn lại
```
**Dòng 100-115:** Dự đoán pin còn dùng bao lâu = dung lượng / discharge trung bình gần
đây. Trả None nếu chưa đủ dữ liệu.

```
117-125 save(): giữ tối đa 90 ngày (xóa cũ); ghi JSON
128-161 self-test: hôm qua 4h12, hôm nay 5h23 → chênh 4260s; predict 28000/14000=2h; total saved; save/load
```
**Dòng 117-161:** save giới hạn 90 ngày để file không phình. Test: ghi 2 ngày, kiểm chênh
lệch giây + dự đoán pin + tổng tiết kiệm + save/load. In PASS.

**TÓM TẮT:** [6.1/6.2] Store thống kê nhẹ cho dashboard — bằng chứng giá trị (giờ pin
thêm, Wh tiết kiệm, dự đoán pin còn). LIÊN KẾT: dashboard/server (đọc để hiển thị), rl_brain/
engine (gọi record mỗi chu kỳ). Là phần "thuyết phục người dùng" của sản phẩm thương mại.

═══════════════════════════════════════════════════════════════════════════════
# FILE 41/48 — commercial/profiles.py  (145 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-14  """ docstring """ — profile người dùng = "khẩu vị" ưu tiên → trọng số reward α/β/γ/δ
16-47 BUILTIN_PROFILES: student/office/gaming/presentation (mỗi cái: label, desc, weights, min_brightness); DEFAULT="office"
```
**Dòng 1-47:** [6.3] Profile người dùng ánh xạ sang trọng số reward (α/β/γ/δ của Phase 2).
4 profile dựng sẵn: Sinh viên (tiết kiệm mạnh α 1.5), Văn phòng (cân bằng), Gaming (ít
tiết kiệm α 0.6, trọng ngữ cảnh δ 1.0), Thuyết trình (màn sáng nhất min_brightness 0.70).
Lưu ý: khác với 3 profile MODEL (battery_saver/balanced/performance) — đây là profile
"khẩu vị" ánh xạ reward weights, dùng cho reward thật/world model.

```
50-56 ProfileManager.__init__(path): active=office; custom={}; load nếu có
58-67 list_profiles (builtin+custom); set_active (kiểm tồn tại)
```
**Dòng 50-67:** Quản lý profile. list gộp builtin + tự tạo. set_active đổi profile đang
dùng (kiểm hợp lệ).

```
69-79 get(name): custom > builtin > default; weights(name); min_brightness(name)
```
**Dòng 69-79:** get ưu tiên profile tùy chỉnh, rồi builtin, cuối cùng default. weights trả
α/β/γ/δ. min_brightness trả sàn sáng của profile.

```
81-85 create_custom(name, label, weights, min_brightness): tạo profile người dùng tự định nghĩa
87-98 to_reward_weights(name): dựng RewardWeights từ weights (nối Phase 2); fallback dict
```
**Dòng 81-98:** create_custom cho người dùng tự tạo profile (AI học theo). to_reward_weights
nối thẳng sang RewardWeights của reward.py (Phase 2) để dùng trong tính reward.

```
100-112 save/load JSON (active + custom)
115-145 self-test: office mặc định; gaming α thấp/δ cao; presentation min_bright 0.70; tạo custom "night"; to_reward_weights; save/load
```
**Dòng 100-145:** Lưu/nạp. Test: profile mặc định, đổi gaming, min_brightness thuyết trình,
tạo custom, nối RewardWeights, save/load. In PASS.

**TÓM TẮT:** [6.3] Profile "khẩu vị" người dùng → trọng số reward. Cho phép tùy biến + tự
tạo profile. LIÊN KẾT: datacollector/reward (RewardWeights), app/buy_business (chọn profile
trên GUI). Lưu ý: phân biệt với 3 profile MODEL đã train — đây là lớp tùy chỉnh reward
weights cho Phase 2/online, không phải file ONNX.

═══════════════════════════════════════════════════════════════════════════════
# FILE 42/48 — commercial/tiers.py  (96 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-14  """ docstring """ — mô hình kinh doanh: khóa tính năng theo tier (Free/Basic/Pro/Lifetime)
16-28 hằng tier (FREE/BASIC/PRO/LIFETIME) + feature flag (F_CPU_THROTTLE/GPU_SWITCH/DASHBOARD/...)
```
**Dòng 1-28:** [6.5] Mô hình kinh doanh khóa tính năng theo tier. 4 tier: Free (CPU
throttle cơ bản), Basic 29k (+GPU switch, dashboard, pin health), Pro 59k (+online learning,
profile tùy chỉnh), Lifetime (+planning, update vĩnh viễn). 7 feature flag.

```
30-43 TIER_FEATURES: tập tính năng mỗi tier (tăng dần); TIER_LABELS; TIER_PRICE_VND {0/29k/59k/499k}
```
**Dòng 30-43:** Ánh xạ tier → tập tính năng (Free ⊂ Basic ⊂ Pro ⊂ Lifetime). Nhãn +
giá VND (Lifetime 499k).

```
46-58 TierGate.__init__(tier): tier rác → FREE; set_tier; can(feature); features()
```
**Dòng 46-58:** Cổng kiểm tier. Tier không hợp lệ → về FREE (an toàn). can() kiểm tính
năng có mở không. features() liệt kê tính năng đang mở.

```
60-69 require(feature): nếu có → (True, ""); nếu không → tìm tier rẻ nhất mở nó, trả gợi ý nâng cấp
```
**Dòng 60-69:** require kiểm + sinh thông điệp nâng cấp ("Tính năng này cần gói Basic
29,000đ"). Tìm tier rẻ nhất mở tính năng để gợi ý.

```
72-96 self-test: free không có GPU switch (gợi ý Basic); pro không có planning (gợi ý Lifetime); lifetime có tất cả; tier rác → free
```
**Dòng 72-96:** Test phân quyền từng tier + thông điệp nâng cấp + tier rác về free. In PASS.

**TÓM TẮT:** [6.5] Khóa tính năng theo gói trả phí — mô hình kinh doanh. LIÊN KẾT:
app/buy_business (kiểm tier trước khi bật tính năng), server (trả tier khi verify key).
Sản phẩm thực tế đã bán với license key (BC-...) — đây là logic phân quyền tính năng.

───────────────────────────────────────────────────────────────────────────────
HẾT PHẦN 7 (FILE 37-42): schema, reward, dataset_uploader, stats_store, profiles,
tiers. Còn: commercial/notifications + app (buy_business, app_integrations) + server
+ dashboard + tests (6 file) → phần 8 (cuối).
───────────────────────────────────────────────────────────────────────────────
