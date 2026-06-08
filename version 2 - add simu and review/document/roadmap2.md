# BatteryClaw — Roadmap (phần tiếp theo)

Tài liệu này ghi tiếp từ chỗ `roadmap.md` dừng lại (trạng thái "Sau Phase 6 — sản
phẩm chạy thật, bán được"). Liệt kê những việc đã làm THÊM kể từ đó đến nay, theo
thứ tự thời gian thực tế.

Bối cảnh: roadmap cũ kết thúc khi sản phẩm đã deploy được lần đầu. Phần dưới đây là
quá trình **làm giàu simulator để model mạnh hơn**, rồi **debug từ log chạy thật**
cho tới khi sản phẩm hoạt động đúng hoàn chỉnh trên máy.

---

## G. Nâng cấp Simulator — Đợt 1 (5 → 12 workload, 1 → 6 máy)

Mục tiêu: model "khôn" hơn không phải bằng fake data mà bằng simulator phong phú hơn
(data nhất quán vật lý). Giữ nguyên contract 15 obs → 7 action.

- Workload: 5 → **12 loại** (idle, web_light, web_heavy, office, video_call,
  video_play, music, code_ide, compile, render, game_light, game_heavy).
- Phần cứng: 1 máy cố định → **6 loại máy** bốc ngẫu nhiên mỗi episode (ultrabook →
  gaming cao cấp → máy cũ), khác nhau pin/dGPU/CPU base/panel Hz.
- Thêm: độ chai pin ngẫu nhiên 60–100%, mô hình sạc (cắm/rút + charge limit 80%),
  nhiệt độ động theo công suất + nhiệt phòng 18–38°C + thermal throttle >90°C,
  mạng/audio/RAM thật theo workload, chu kỳ ngày/đêm, cá tính người dùng (nhạy
  giật / nhạy màn tối), reward phạt −5 khi pin chết.
- Train mạnh hơn: net [128,128] → **[256,256]**, n_envs 4 → 8, steps mặc định 2 triệu.
- Kiểm thử: env_checker PASS, obs luôn trong [0,1], ONNX export 15→7, 11/11 test PASS.

## H. Nâng cấp Simulator — Đợt 2 (action delay, spike, pin phi tuyến, curriculum)

4 tính năng, tất cả không cần thêm observation, khớp engine thật:

- **F1 Action Delay**: lệnh AI trễ 2 step (20s) mới có hiệu lực (mô phỏng HĐH cần
  thời gian áp dụng) → AI học tính kiên nhẫn, tránh dao động lệnh.
- **F2 Spike Workload**: tác vụ ngầm (Update/antivirus) vọt CPU bất chợt → AI học
  chịu đựng thay vì hoảng loạn.
- **F3 Đường cong pin phi tuyến**: dưới 20% pin xả nhanh hơn (tới ~1.8×) + sập nguồn
  ảo khi pin chai → AI học chắt chiu chặng cuối.
- **F4 Curriculum Learning**: thêm tham số difficulty; train 3 phase dễ → khó để
  model không "ngợp".
- TỪ CHỐI có lý do: ambient_lux (engine không đọc được cảm biến sáng qua WMI →
  tránh AI học tín hiệu không tồn tại lúc deploy), fan_noise (giá trị thấp), LSTM
  (ONNX không trạng thái, rủi ro cao). Ghi rõ vì sao để không nhầm sau này.

## I. Nâng cấp Simulator — Đợt 3 (lịch sạc, quán tính nhiệt, reward profile, curriculum 4 phase)

- **F5 Lịch sạc theo thói quen**: thay sạc ngẫu nhiên bằng 4 profile ngày (office /
  student / freelance / desktop) theo giờ → AI đoán trước "10h sáng thường đang sạc".
- **F6 Quán tính nhiệt theo dòng máy**: mỗi máy có hệ số nóng/tản riêng (ultrabook
  nóng gắt/tản kém, gaming dày nóng chậm/tản tốt) → AI học hạ xung sớm trên máy mỏng.
- **F7 Reward theo profile**: 3 chế độ (battery_saver / performance / balanced),
  trọng số reward GẮN CHẶT với độ nhạy người dùng để AI suy ra profile qua tín hiệu
  nó thấy (tránh tín hiệu mâu thuẫn) — một policy phục vụ cả 3 nút UI.
- **F8 Curriculum 4 phase**: thêm phase stress test (difficulty 4 kịch khung) để mài
  policy, bước nhảy độ khó mượt hơn.

## J. Các vòng code review simulator (sửa bug + dọn)

- **Review simulator v1**: BUG-01 (train.py còn os.makedirs tương đối → tạo thư mục
  rác ở CWD; thêm LOGS_DIR anchor), BUG-02 (action queue warmup peek → lặp action
  đầu; đổi sang action mặc định trung tính), DESIGN-02 (dead zone obs[10] của máy
  165Hz; đổi máy 165→144Hz + chuẩn hóa chia (PANEL_MAX_HZ−60) ở cả env và rl_brain).
- **Review simulator v2**: STALE-01 (bỏ key 165 thừa trong REFRESH_EXTRA_FACTOR),
  STALE-02 (docstring khớp "60/120/144Hz").
- DESIGN-01 ghi chú không sửa: F7 multi-profile là policy thỏa hiệp, không cá nhân
  hóa thật — đúng bản chất, để dài hạn (cần 3 model riêng hoặc thêm profile vào obs).

## K. Train thật 5 triệu steps + chẩn đoán

- Train 5M steps curriculum 4 phase trên máy thật (~21 phút, ~3900 FPS).
- Kết quả eval: Mean reward 225 ± 459, best episode 1122, mean battery end 62.8%.
- Hai cố vấn ngoài chẩn đoán "policy collapse / catastrophic forgetting". Phân tích
  lại: KHÔNG phải collapse — reward tụt qua phase là vì mỗi phase KHÓ HƠN (so sánh
  táo với cam); best 1122 chứng tỏ năng lực còn nguyên. Vấn đề thật: độ lệch chuẩn
  lớn (model thất thường) + chính sách hơi cực đoan.

## L. Debug từ log inference THẬT (vòng 15) — 4 nhóm sửa

Từ rl_brain.log thật (600+ step): Disch luôn 1mW, action ghim cứng, lỗi
"No module named replay_buffer".

- **Sửa online learning chết trong exe**: PyInstaller không gom submodule online/
  (import động qua sys.path). Thêm --paths cho từng thư mục con + --collect-submodules
  + --hidden-import 10 module. → online learning chạy thật (xác nhận "Online learning ON").
- **Nới lớp override che AI**: rl_brain ép cứng brightness≥0.70 khi plugged → nới
  xuống 0.45 để AI tự quyết phần lớn.
- **Model bớt cực đoan**: export ONNX từ BEST model (không phải model cuối phase 4
  khắc nghiệt) + set eval mode; nhẹ phase 4 (spike 2×→1.5×, pin chai 0.55-0.80 →
  0.62-0.85); đổi tỉ lệ curriculum phase4 20%→12%; eval ở difficulty 3 (thực tế).
- **Sửa APPDATA**: state online learning + dashboard ghi vào %APPDATA%\BatteryClaw\
  state thay vì cạnh exe (cài Program Files sẽ bị chặn ghi → online learning câm lặng).

## M. Nối ACTION vào phần cứng THẬT (vòng 16)

Phát hiện lớn: engine chỉ thực thi 1/7 action (defer). Brightness/CPU/refresh/wifi
nhận rồi BỎ → "log Br:45% mà màn hình thật 100%". AI suy nghĩ đúng nhưng chân tay
chưa nối với não.

- Viết **test phần cứng độc lập** (`HardwareTest`, `HardwareTest2`) cho người dùng
  chạy TRƯỚC khi build full — xác nhận trên máy thật: brightness (WMI) đổi thật
  35/90%, refresh (ChangeDisplaySettingsEx) đổi thật 60/144Hz, CPU throttle
  (powercfg) OK, wifi OK. Tránh build/train mò.
- Thêm `engine_dotnet/Control/HardwareControl.cs`: SetBrightness/ReadBrightness,
  SetCpuMax, SetRefreshHz/ReadRefreshHz, SetWifiPowerSave (chỉ gọi API khi giá trị
  đổi, lỗi nuốt an toàn).
- Nối vào Program.cs HandleActionJson; đọc brightness THẬT thay hardcode 80; rl_brain
  gửi thêm refresh_hz (Hz thật).
- KHÔNG nối (nói rõ): GPU switch (Windows quản per-app, không ép từ ngoài),
  charge_limit (phụ thuộc hãng, không có API Windows chuẩn) — AI vẫn xuất nhưng
  engine bỏ qua an toàn.

## N. Sửa bug Disch=1mW gốc rễ (vòng 17)

- Chẩn đoán bằng dữ liệu thật (`BatteryProbe` đọc thẳng pin): WMI DischargeRate trả
  6973/11770/10161 mW — ĐỌC ĐƯỢC HOÀN HẢO. Phần cứng không mù.
- Gốc rễ: engine chọn `discharge = etwDischargeMw > 0 ? etw : wmi`. ETW trên máy này
  trả ~1mW nhưng vì >0 nên "thắng" WMI 6973mW → engine luôn gửi 1mW.
- Sửa: đảo ưu tiên — dùng WMI (đáng tin) trước, chỉ dùng ETW khi WMI=0 và ETW đủ lớn.

## O. Trạng thái cuối — xác nhận từ log thật

Log inference mới nhất (chạy pin) xác nhận cả 4 vấn đề đã khỏi:

- **Disch là số thật**: 10709 / 8254 / 8132 / 12753 mW (dao động theo tải).
- **Online learning ON** (không lỗi replay_buffer).
- **Action đa dạng + phần cứng đổi thật**: CPU @20%→@24%, refresh 60→144Hz, brightness
  đổi theo tình huống — không còn ghim cứng như log cũ.
- **"Saved" tích lũy thật**: 0 → 53 → 214 → 470 → 723 mWh (tính được vì có discharge thật).

→ Sản phẩm chạy đúng hoàn chỉnh end-to-end trên máy thật.

---

## Đính chính so với tài liệu marketing (để nộp/bán trung thực)

Vài điểm trong bản quảng cáo cần khớp lại với thực tế hiện tại:

- **Con số "kéo dài pin 20–35%"**: là DỰ KIẾN, chưa đo A/B thật. Nên ghi "mục tiêu,
  đang đo đối chứng" thay vì khẳng định.
- **"165Hz" / "pin chai 55%"**: đã đổi (panel max 144Hz; pin chai phase 4 là 62-85%).
- **SAC/HRL/MPC/LSTM**: có code thật trong kho (advanced/, worldmodel/) nhưng KHÔNG
  chạy trong bản deploy — bản thật dùng PPO→ONNX. Nên nói "có sẵn dạng nghiên cứu".
- **ETW "độ chính xác mili giây"**: thực tế ETW không chạy trên máy test, đang dùng
  WMI. Với bài toán pin (nhịp giây/phút) thì WMI thừa đủ — nên không quảng cáo ETW
  ms như điểm mạnh cốt lõi.

---