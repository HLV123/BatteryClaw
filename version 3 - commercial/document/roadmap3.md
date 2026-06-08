# BatteryClaw — Roadmap3

Tài liệu này ghi tiếp từ chỗ `roadmap2.md` dừng. 
Phần dưới là việc làm THÊM kể từ đó. 
Thực thi một kế hoạch nhiều tầng (0-4) để nâng sản phẩm từ lên cá nhân hóa.
Quyết định làm theo tầng (Không tiết lộ full nội các tầng ở đây)

---

## P. Machine ID bền hơn (Tầng 0.3)

- Thay `uuid.getnode()` (MAC address — đổi khi máy nhiều card mạng/VPN, gây khóa nhầm
  key) bằng tổ hợp ổn định: UUID mainboard (wmic csproduct) + serial ổ đĩa
  (wmic diskdrive) + processor + hostname.
- Giữ `_machine_id_legacy()` để TƯƠNG THÍCH NGƯỢC: khách đã kích hoạt bằng ID cũ không
  bị khóa khi cập nhật app. `_check_existing` chấp nhận cả ID mới lẫn cũ; verify gửi
  machine_id đã lưu (cái server đã khóa).

## Q. Ba model profile — cá nhân hóa THẬT (Tầng 1.1)

Giải quyết hạn chế DESIGN-01 (F7 chỉ là policy thỏa hiệp). Giờ train 3 model riêng:

- `battery_env`: thêm `force_profile` — mỗi episode dùng đúng 1 profile thay vì bốc
  ngẫu nhiên.
- `train.py`: thêm `--profile {battery_saver,balanced,performance}`; xuất ONNX theo
  tên (balanced → tên mặc định giữ tương thích; khác → `_<profile>.onnx`).
- `app/buy_business.py`: `_model_for_profile()` chọn onnx theo combobox Hồ sơ, fallback
  model mặc định nếu thiếu.
- `build_business.ps1`: copy cả 3 onnx vào dist.

KẾT QUẢ TRAIN THẬT (5M steps mỗi profile) — 3 model PHÂN HÓA rõ rệt:

| Profile        | Mean reward | Std    | Lag (giật) | Pin cuối |
|----------------|-------------|--------|------------|----------|
| battery_saver  | 81.9        | ±642   | 89.8       | 63.4%    |
| balanced       | 233.9       | ±469   | 58.2       | 63.2%    |
| performance    | 169.1       | ±94.9  | 0.62       | 54.0%    |

Cột Lag là bằng chứng cá nhân hóa hoạt động: performance gần như không giật (0.62)
nhưng pin cạn nhanh (54%); battery_saver chấp nhận giật nhiều (89.8) để giữ pin (63%).
performance ổn định nhất (std nhỏ). battery_saver thất thường (std lớn do phạt pin yếu
nặng) — dùng được nhưng có thể tinh chỉnh sau.

## R. Giảm thất thường + tự so model (Tầng 1.2, 1.3)

- **1.2**: learning rate GIẢM DẦN (linear 3e-4 → 5e-5 theo tiến độ) — hội tụ ổn định
  hơn, giảm std.
- **1.3**: `evaluate_model()` trả (mean, std); khi export lưu điểm vào `<onnx>.score`.
  Lần train sau so điểm: nếu model mới kém >5% → GIỮ model cũ (tránh deploy bản tệ hơn).
  Xóa `.score` để ép ghi đè.

## S. Đưa kho nghiên cứu vào deploy (Tầng 2)

- **2.2 SAC**: thêm `simulator/train_sac.py` — train SAC off-policy trên simulator,
  export actor ONNX 15→7 khớp rl_brain (thay PPO nếu muốn). Sau đó sửa: tự dùng GPU
  (cuda) nếu có, train 1 update/step (không phải 50 — bản đầu chậm-đều trên CPU).
  Lưu ý thật: SAC chưa kiểm chứng tốt hơn PPO cho bài toán này; PPO vẫn mặc định.
- **2.3 HRL+MPC**: manager/worker/mpc self-test PASS. Thêm `online/hrl_integration.py`
  — AutoProfileManager bọc Manager (HRL tầng cao) gợi ý đổi PROFILE theo pin/giờ/sạc,
  có hysteresis (đổi sau N lần ổn định). Cách nối HRL thực dụng, không phá contract.
- **2.1 LSTM**: giải bài toán "ONNX không trạng thái" bằng export LSTM dạng CHUỖI
  (batch,30,15)→(batch,7) — không cần hidden state qua ONNX. `export_lstm_onnx.py` +
  rl_brain OnnxPolicy tự phát hiện model chuỗi, giữ rolling window 30 state. Đường
  deploy LSTM thông; cần train riêng để LSTM giỏi (chưa làm, tốn tài nguyên).
- **2.4 Task Scheduler**: xác nhận ĐÃ XONG từ trước (Program.cs gọi NextHeavyTask,
  cảnh báo task nặng sắp chạy).

## T. Hỗ trợ đa máy + test phần cứng (Tầng 3)

- **3.3 đa máy**: rl_brain bền hơn với máy đọc state khác nhau — brightness không đọc
  được → 80 trung tính; refresh không đọc được → 60Hz. Engine đã sẵn skip an toàn.
- **3.2 GPU switch — LÀM ĐƯỢC** (sau test máy thật xác nhận ghi registry OK):
  `HardwareControl.SetAppGpuPreference` đặt GPU preference PER-APP (iGPU tiết kiệm/
  dGPU hiệu năng) cho app foreground qua registry. Engine lấy full path app; brain
  gửi kèm. Hợp lệ (như Windows Graphics Settings), KHÔNG ép tắt dGPU toàn cục.
- **3.1 charge limit — KHÔNG làm được** (test máy MSI Katana GF66 không expose WMI
  class để đặt ngưỡng sạc). Thay vì giả vờ: app phát hiện hãng (MSI/Lenovo/ASUS) và
  HƯỚNG DẪN người dùng bật trong app hãng (MSI Center). Trung thực.
- Tạo test script độc lập cho người dùng chạy xác minh: `ChargeTest`, `GpuTest`
  (giống cách HardwareTest/BatteryProbe trước đây).

## U. Sản phẩm & kinh doanh (Tầng 4)

- **4.1 admin** + **4.2 gia hạn key**: backend đã đủ (create/revoke/extend/stats/logs);
  cải tiến UI nút gia hạn từ "+4 ngày" cố định → nhập số ngày tùy ý, báo hạn mới.
- **4.3 dashboard báo cáo**: đã đầy đủ (tiết kiệm hôm nay/30 ngày, biểu đồ, dự đoán
  pin, sức khỏe pin); bổ sung báo cáo tóm tắt dạng chữ ("30 ngày tiết kiệm ~X Wh ≈ Y
  lần sạc").
- **4.4 installer**: thêm `install.ps1` (tạo shortcut Desktop + Start Menu, tùy chọn
  autostart, cờ -Uninstall). build script copy vào bản phân phối.

## V. Sửa bug nút Bắt đầu biến mất (sau khi build thật)

- Khi build và chạy thật, người dùng báo màn chính KHÔNG có nút Bắt đầu.
- Gốc rễ: lúc thêm `_model_for_profile` (mục Q), hàm này bị chèn GIỮA `_build_ui` →
  cắt hàm làm đôi → phần tạo nút Bắt đầu/Dashboard/note nằm sau `return`, không chạy.
- Sửa: tách `_model_for_profile` ra; đưa nút Start/Dashboard/note về lại trong
  `_build_ui`; xóa khối chết trùng. Verify _build_ui chứa đủ các widget.

## W. Đồng bộ tài liệu

- Cập nhật `ARCHITECTURE.md`: GPU preference, 3 model profile, SAC/HRL/LSTM, installer,
  charge limit hướng dẫn.
- Cập nhật `VAN_HANH_KY_THUAT.md`: train 3 model, install.ps1, sửa phần GPU (giờ làm
  được) và charge limit (hướng dẫn MSI Center) — bỏ câu sai "bỏ qua an toàn".

---

## Trạng thái hiện tại

Sản phẩm có đầy đủ: 3 model profile cá nhân hóa thật (đã train, phân hóa rõ), điều
khiển phần cứng thật (brightness/CPU/refresh/wifi/GPU per-app), online learning,
license + gia hạn, dashboard báo cáo, installer. 11/11 test PASS xuyên suốt.

