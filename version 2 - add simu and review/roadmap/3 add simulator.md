# Vòng 9 — Nâng cấp simulator + train mạnh (2026-06-03)

### Simulator nâng cấp (simulator/battery_env.py) — giữ contract 15→7
Thêm rất nhiều yếu tố thực tế để model gặp đủ tình huống:
- 12 workload (idle, web_light/heavy, office, video_call, video_play, music,
  code_ide, compile, render, game_light/heavy) — gom về 5 nhóm cho obs[3].
- 6 loại máy bốc ngẫu nhiên mỗi episode (pin, độ chai 0.6-1.0, có/không dGPU,
  cpu base, panel 60/120/144/165Hz, screen base).
- Mô hình SẠC thật: cắm/rút ngẫu nhiên, sạc tăng pin + nóng thêm, charge limit 80%.
- Nhiệt độ động theo công suất + nhiệt phòng (18-38C), thermal throttle >90C gây giật.
- Wifi/audio/ram thật theo workload; wifi tải nặng tốn điện hơn.
- Chu kỳ ngày/đêm: giờ ảnh hưởng workload hay gặp.
- Cá tính người dùng: nhạy cảm giật / nhạy cảm màn tối khác nhau mỗi episode.
- Reward: A·tiết kiệm − B·giật − C·khó chịu + D·tuổi thọ; chết pin −5, sống +pct·8.
- env_checker PASS, obs luôn trong [0,1].

### train.py — train mạnh hơn
- Default 2,000,000 steps, n_envs=8, net_arch=[256,256], batch_size=512, ent_coef=0.02.
- Sửa info key "lag_penalty" → "lag" cho khớp env mới.
- Đã test: train + đánh giá + ONNX export (15→7) chạy thông; test_core 11/11 PASS.

Cách train dài trên máy: python simulator\train.py --steps 3000000

---

# Vòng 10 — Sửa đường dẫn ghi state (online learning) (2026-06-03)

VẤN ĐỀ: app/buy_business.py trỏ online_dir + dashboard state vào os.path.join(BASE,
"online","state") — tức CẠNH file exe. Nếu khách cài app vào C:\Program Files\,
Windows chặn ghi -> online learning thất bại ÂM THẦM (app chạy nhưng không tự học).

FIX: thêm STATE_DIR = %APPDATA%\BatteryClaw\state (luôn ghi được, kể cả khi cài
trong Program Files). online_dir và dashboard state_dir đều dùng STATE_DIR.
config.json cũng gom về %APPDATA%\BatteryClaw\.

Đã xác minh: OnlineLearner/adapter ghi replay.npz, pattern.json, ckpt/ đều dưới
state_dir được truyền vào (không hardcode), nên sửa ở app là đủ. Syntax OK.

---

# Vòng 11 — Simulator đợt 2: action delay, spike, pin phi tuyến, curriculum (2026-06-03)

Giữ nguyên contract 15→7. 4 tính năng (không cần thêm observation, khớp engine thật):

### F1 — Action Delay (độ trễ thực thi)
Lệnh AI vào hàng đợi, trễ ACTION_DELAY=2 step (20s) mới có hiệu lực — mô phỏng HDH
cần thời gian áp dụng (powercfg/brightness không tức thì). AI học tính kiên nhẫn,
tránh dao động lệnh. Chỉ bật ở difficulty 3.

### F2 — Spike Workload (tác vụ ngầm bất ngờ)
~2%/step kích hoạt spike (Windows Update/antivirus/OneDrive) vọt CPU +0.55 trong
30–120s rồi tắt. AI không "tắt" được spike, phải học chịu đựng/bù trừ. Chỉ ở difficulty 3.

### F3 — Đường cong xả pin phi tuyến + sập nguồn ảo
Dưới 20% pin xả nhanh hơn (hệ số tới ~1.8, pin chai càng dốc); pin chai nặng có thể
sập nguồn sớm (brownout) trước khi về 0. AI học chắt chiu chặng cuối. Chỉ ở difficulty 3.

### F4 — Curriculum Learning (train.py)
Tham số difficulty (1=dễ: 1 máy ultrabook, không phá bĩnh; 2=vừa: 6 máy+12 workload;
3=full: bật hết). train() chia 3 phase: 15% diff1 → 35% diff2 → 50% diff3, dùng
model.set_env() đổi độ khó, giữ đếm timestep liên tục. Giúp hội tụ nhanh, tránh
"ngợp" khi train 3–5 triệu steps. Tắt bằng --no-curriculum.

train.py: default --steps 3,000,000, --envs 8. Đã test: 3 phase chuyển mượt,
ONNX export 15→7 OK, env_checker PASS ở cả 3 difficulty, test_core 11/11 PASS.

KHÔNG làm (đợt sau): ambient_lux (máy thật không đọc được cảm biến sáng qua WMI),
fan_noise (giá trị thấp, engine không đọc tốc độ quạt), LSTM (cần sửa ONNX export +
rl_brain xử lý hidden state — rủi ro cao).

---

# Vòng 12 — Simulator đợt 3: lịch sạc, quán tính nhiệt, reward profile, curriculum 4 phase

Giữ nguyên contract 15→7, không thêm observation. 4 tính năng:

### F5 — Lịch sạc theo thói quen (thay sạc ngẫu nhiên thuần)
4 charge profile theo giờ: office (cắm giờ hành chính + tối), student (cắm đêm),
freelance (chiều tối), desktop (luôn cắm). plugged tính theo profile+giờ (+2% nhiễu).
Kết hợp chu kỳ ngày/đêm → AI đoán trước "10h sáng thường đang sạc → bật charge limit".

### F6 — Quán tính nhiệt theo dòng máy
Mỗi máy có heat_rate (tốc độ nóng) + cool_rate (tản nhiệt) riêng. Ultrabook mỏng
nóng gắt/tản kém (heat 0.32, cool 0.05); gaming dày nóng chậm/tản tốt. Công thức
nhiệt bậc 1: Temp += (target-Temp)*heat − cool*(Temp−room). AI học hạ xung sớm trên máy mỏng.

### F7 — Reward theo profile (gắn chặt độ nhạy người dùng)
3 profile: battery_saver (save x2, lag x0.5), performance (save x0.5, lag x3),
balanced. QUAN TRỌNG: trọng số reward gắn KHỚP với độ nhạy giật/màn tối của người
dùng (battery_saver ↔ ít nhạy giật; performance ↔ rất nhạy giật) để AI suy ra profile
qua tín hiệu nó thấy, tránh tín hiệu mâu thuẫn → 1 policy đa mục tiêu phục vụ cả 3 chế độ UI.

### F8 — Curriculum 4 phase (thêm stress test)
Phase 1 (15%) diff1 → Phase 2 (30%) diff2 → Phase 3 (35%) diff3 (phá bĩnh VỪA: trễ
1 step, spike thường) → Phase 4 (20%) diff4 KỊCH KHUNG (trễ 2 step, spike gấp đôi,
pin chai nặng 55-80%). eval ở diff4. Tránh cú sốc reward khi nhảy độ khó.

Test: env_checker + obs[0,1] ở cả 4 difficulty; curriculum 4 phase chuyển mượt;
ONNX 15→7 OK; test_core 11/11 PASS.
