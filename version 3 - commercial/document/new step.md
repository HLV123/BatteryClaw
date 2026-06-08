# Vòng 18 — Tầng 0.3 + 1.1 (machine ID bền + 3 model profile) (2026-06-07)

### 0.3 — Machine ID bền hơn
app/buy_business.py: thay uuid.getnode() (MAC, đổi khi nhiều card mạng) bằng tổ hợp
ổn định: UUID mainboard (wmic csproduct) + serial ổ đĩa (wmic diskdrive) + processor
+ hostname. Giữ _machine_id_legacy() để TƯƠNG THÍCH NGƯỢC: _check_existing chấp nhận
cả ID mới lẫn cũ; verify gửi machine_id đã lưu (cái server đã khóa). Khách đã activate
không bị khóa nhầm khi update.

### 1.1 — Train 3 model riêng cho 3 profile (cá nhân hóa THẬT)
- battery_env: thêm force_profile — mỗi episode dùng đúng 1 profile (thay vì bốc
  ngẫu nhiên 3). Test: force ép đúng (battery_saver rw 2.0/0.5, performance 0.5/3.0).
- train.py: thêm --profile {battery_saver,balanced,performance}; truyền force_profile
  vào tất cả env (curriculum); xuất onnx theo tên: balanced→batteryclaw_policy.onnx
  (giữ tương thích), khác→batteryclaw_policy_<profile>.onnx.
- app/buy_business.py: _model_for_profile() chọn onnx theo combobox UI (Tiết kiệm pin
  /Hiệu năng cao/Cân bằng), fallback model mặc định nếu chưa train file profile.
- build_business.ps1: copy cả 3 onnx (nếu có) vào dist\models.

Cách train 3 model:
  python simulator\train.py --steps 5000000 --profile battery_saver
  python simulator\train.py --steps 5000000 --profile balanced
  python simulator\train.py --steps 5000000 --profile performance

Test: train profile xuất đúng file riêng, ONNX 15→7 OK, 11/11 PASS.

CÒN LẠI (lượt sau): 1.2 giảm thất thường, 1.3 tự so model; Tầng 2 (LSTM/SAC/HRL/MPC/
TaskScheduler); Tầng 3 (charge limit/GPU switch/đa máy); Tầng 4 (admin/gia hạn/dashboard/installer).

---

# Vòng 19 — Tầng 1.2 + 1.3 + xác nhận 2.4 (2026-06-07)

### 1.2 — Giảm độ thất thường (std lớn)
train.py: learning rate GIẢM DẦN (linear schedule 3e-4 → 5e-5 theo progress). LR cao
đầu để học nhanh, giảm cuối để hội tụ ổn định → giảm std. Áp cho mọi lần train.

### 1.3 — Tự động so model mới vs cũ
- evaluate_model() giờ trả (mean, std).
- Khi export: lưu điểm eval vào file `<onnx>.score`. Lần train sau so điểm mới với cũ;
  nếu model mới KÉM HƠN >5% → GIỮ model cũ (không ghi đè), tránh "train lại lỡ deploy
  bản tệ hơn". Xóa file .score để ép ghi đè.
- Test: 2 lần train liên tiếp — lần 2 so đúng (cũ -122 vs mới -73.9 → ghi đè).

### 2.4 — Task Scheduler Reader: ĐÃ XONG TỪ TRƯỚC
Kiểm tra: package TaskScheduler 2.11.0 có trong csproj; Program.cs gọi
TaskSchedulerReader.NextHeavyTask(6) và in cảnh báo "task nặng sắp chạy → nên cắm
sạc trước". Hoạt động. (Nâng cấp tùy chọn sau: đẩy cảnh báo qua pipe → toast cho
app GUI thấy, vì hiện chỉ in console.)

Test: 11/11 PASS, ONNX 15→7 OK.

CÒN LẠI: Tầng 2.1 LSTM, 2.2 SAC, 2.3 HRL+MPC (phần nặng); Tầng 3 (charge limit/GPU/
đa máy — best-effort + test script); Tầng 4 (admin/gia hạn/dashboard/installer).

---

# Vòng 20 — Tầng 2 trọn vẹn (LSTM/SAC/HRL/MPC vào deploy) (2026-06-07)

### 2.2 — SAC train trên simulator
Thêm simulator/train_sac.py: thu thập transition từ BatteryClawEnv vào ReplayBuffer,
train SAC (off-policy, tối ưu entropy), export actor ONNX (15->7, tanh [-1,1]) KHỚP
rl_brain y hệt PPO. Hỗ trợ --profile. Test: train chạy, ONNX verify shape (1,7) range
khớp contract. Là lựa chọn thay PPO; PPO vẫn mặc định.
   python simulator\train_sac.py --steps 300000 [--profile X]

### 2.3 — HRL + MPC vào deploy (opt-in, an toàn)
- manager/worker/mpc_planner self-test PASS (đã có code đủ).
- Thêm online/hrl_integration.py: AutoProfileManager bọc Manager (HRL tầng cao) ->
  gợi ý PROFILE MODEL (save_max->battery_saver, performance->performance) theo
  pin/giờ/sạc/thói quen, có hysteresis (đổi sau N lần ổn định, tránh nạp model liên tục).
  App có thể bật "tự đổi profile theo hoàn cảnh". Test: pin thấp->battery_saver,
  cắm sạc->performance. Đây là dùng HRL mức "chọn chiến lược" — thực dụng, không phá
  contract. (Worker goal-conditioned/MPC từng action để dành — phức tạp, rủi ro cao.)

### 2.1 — LSTM deploy được (giải bài toán ONNX không trạng thái)
- Thêm simulator/export_lstm_onnx.py: export LSTM dạng CHUỖI (batch,30,15)->(batch,7),
  KHÔNG cần hidden state qua ONNX -> deploy được. verify ONNX OK.
- rl_brain OnnxPolicy: tự PHÁT HIỆN model LSTM (input 3 chiều) -> giữ rolling window
  30 state, feed cả chuỗi mỗi bước. Tương thích ngược model phẳng (mặc định).
- Test: nạp LSTM ONNX, predict nhiều bước, action (7,) đúng. Đường deploy LSTM thông.
- LƯU Ý: đây là HẠ TẦNG deploy LSTM. Để LSTM giỏi cần TRAIN thật (behavior cloning
  hoặc RL) — bước riêng tốn tài nguyên, chưa làm. Kiến trúc + deploy đã sẵn sàng.

Test: 11/11 PASS. Tầng 2 hoàn tất.

CÒN LẠI: Tầng 3 (3.1 charge limit theo hãng, 3.2 GPU switch, 3.3 đa máy — best-effort
+ test script cho máy thật); Tầng 4 (4.1 admin, 4.2 gia hạn key, 4.3 dashboard báo cáo,
4.4 installer).

---

# Vòng 21 — Tầng 3 (đa máy + test script charge/GPU) (2026-06-07)

### 3.3 — Hỗ trợ đa máy (làm được trong code)
rl_brain.state_to_obs bền hơn với máy đọc state khác nhau:
- brightness không đọc được (-1, máy màn ngoài/driver lạ) -> dùng 80 trung tính.
- refresh không đọc được (<60) -> coi 60Hz trung tính.
- (refresh_hz chia (144-60) đã clip [0,1] nên máy 60Hz/165Hz đều an toàn.)
Engine HardwareControl đã sẵn skip an toàn khi máy không hỗ trợ (IsRefreshSupported,
lỗi nuốt). Test 11/11 PASS.

### 3.1 — Charge limit theo hãng: TEST SCRIPT trước (chưa viết code điều khiển)
Sự thật: KHÔNG có API Windows chuẩn; mỗi hãng riêng (MSI Center/Lenovo Vantage...).
Tạo ChargeTest.zip (C#): dò máy MSI có expose WMI class (MSI_ACPI/MSI_BatteryHealth)
để điều khiển không. CHƯA viết code vào engine — chờ kết quả test từ máy thật (viết
mò sẽ sai). Nếu máy không expose -> BatteryClaw sẽ HƯỚNG DẪN dùng MSI Center thay vì
giả vờ làm (trung thực).

### 3.2 — GPU switch: TEST SCRIPT trước (chưa viết code điều khiển)
Sự thật: Windows quản GPU per-app, KHÔNG ép tắt dGPU toàn cục được (bảo vệ).
Tạo GpuTest.zip (C#): test đặt GPU preference per-app qua registry
(Software\Microsoft\DirectX\UserGpuPreferences) — cơ chế hợp lệ duy nhất. CHƯA viết
vào engine — chờ kết quả test. Nếu OK -> BatteryClaw gợi ý iGPU per-app cho app tiết
kiệm pin (không ép toàn cục).

CẦN NGƯỜI DÙNG: chạy ChargeTest + GpuTest trên máy, gửi kết quả -> rồi mới viết code
điều khiển đúng cơ chế máy hỗ trợ.

CÒN LẠI: Tầng 4 (4.1 admin, 4.2 gia hạn key, 4.3 dashboard báo cáo, 4.4 installer).
Sau khi có kết quả ChargeTest/GpuTest: viết code charge limit + GPU preference vào engine.

---

# Vòng 22 — Tầng 4 (admin/gia hạn/dashboard/installer) — HOÀN TẤT KẾ HOẠCH (2026-06-07)

### 4.1 — Trang admin: ĐÃ ĐẦY ĐỦ TỪ TRƯỚC
server.py có: create/revoke/delete/extend key, list keys, logs, stats (total/active/
expired/revenue). admin.html có tab Khóa/Lịch sử, hiển thị doanh thu, các nút quản lý.

### 4.2 — Gia hạn key: ĐÃ CÓ + cải tiến
Backend /admin/key/extend đã có. Cải tiến UI: nút "+4 ngay" cố định -> "Gia han" cho
nhập số ngày tùy ý (prompt), báo hạn mới sau khi gia hạn.

### 4.3 — Dashboard báo cáo tiết kiệm: ĐÃ ĐẦY ĐỦ + bổ sung
dashboard đã có: tiết kiệm hôm nay vs hôm qua, tổng Wh 30 ngày, lịch sử 30 ngày
(Chart.js), dự đoán giờ pin còn, sức khỏe pin + dự đoán chai 1 năm. Bổ sung: field
report_text tóm tắt dạng chữ ("30 ngày tiết kiệm ~X Wh ≈ Y lần sạc, pin Z% sức khỏe")
+ cycles_saved cho người dùng đọc nhanh.

### 4.4 — Installer: MỚI
Thêm install.ps1 (chạy trên máy khách): tạo shortcut Desktop + Start Menu, tùy chọn
khởi động cùng Windows, cờ -Uninstall để gỡ sạch. build_business.ps1 copy install.ps1
vào bản phân phối.

Test: tất cả Python syntax OK, 11/11 PASS.

ĐÃ XONG:
  0.3 machine ID bền | 1.1 ba model profile | 1.2 giảm thất thường | 1.3 tự so model
  2.1 LSTM deploy được | 2.2 SAC | 2.3 HRL integration | 2.4 TaskScheduler (sẵn)
  3.3 đa máy | 4.1 admin | 4.2 gia hạn | 4.3 dashboard báo cáo | 4.4 installer

CHỜ KẾT QUẢ TEST TỪ MÁY (đã gửi script ChargeTest.zip + GpuTest.zip):
  3.1 charge limit theo hãng — viết code điều khiển sau khi biết máy expose gì
  3.2 GPU switch — viết code preference per-app sau khi xác nhận registry ghi được

CẦN TÀI NGUYÊN (hạ tầng đã sẵn, chưa train thật):
  2.1 LSTM — đường deploy thông; cần train (behavior cloning/RL) để LSTM giỏi

---

# Vòng 23 — Tầng 3.1 + 3.2 sau test máy thật (2026-06-07)

KẾT QUẢ TEST TỪ MÁY (Katana GF66 11UC):
- GpuTest: ghi/đọc GPU preference per-app registry OK ✓
- ChargeTest: KHÔNG có class MSI_* để đặt charge limit; chỉ có class ĐỌC battery.

### 3.2 — GPU switch: LÀM ĐƯỢC (per-app, hợp lệ)
- HardwareControl.SetAppGpuPreference: ghi GpuPreference per-app vào registry
  (Software\Microsoft\DirectX\UserGpuPreferences). 1=iGPU tiết kiệm, 2=dGPU.
- SystemStateCollector: thêm GetForegroundAppPath() (full path .exe) -> field fg_app_path.
- rl_brain: command gửi kèm fg_app_path.
- Program.cs: gpu_switch 0/1 -> đặt preference cho app foreground (giữ guard cũ:
  brain không tắt dGPU khi game/cắm sạc). KHÔNG ép tắt dGPU toàn cục (Windows chặn).

### 3.1 — Charge limit: KHÔNG làm được qua phần mềm -> hướng dẫn trung thực
Máy MSI không expose WMI để đặt ngưỡng sạc (chỉ MSI Center làm được). Thay vì giả vờ:
- app/buy_business: _maybe_show_charge_tip() phát hiện hãng (MSI/Lenovo/ASUS) -> hiện
  gợi ý người dùng bật giới hạn sạc trong app chính hãng (MSI Center/Vantage/Armoury).
  Hiện 1 lần (cờ charge_tip_shown trong config). Trung thực, vẫn hữu ích.

Test: 11/11 PASS, ngoặc C# cân, Python syntax OK.

---

# Vòng 24 — Sửa SAC train quá chậm (2026-06-07)

VẤN ĐỀ: train_sac.py chạy 10 phút chưa qua 25k steps. Nguyên nhân:
1. SAC chạy CPU (device="cpu" mặc định) — không dùng GPU RTX 3050.
2. train_every=50, train_iters=50 -> mỗi 50 step chạy 50 iter train mạng (quá dày,
   = 25k iter để tới 25k steps).

SỬA:
- train_sac.py: tự phát hiện GPU (torch.cuda.is_available -> "cuda"/"cpu"), in Device.
  Truyền device vào SAC. Đưa obs tensor lên đúng device khi infer.
- train_every=1, train_iters=1 (chuẩn SAC: 1 update/step) -> nhẹ hơn ~50 lần.
- sac_trainer: thêm .detach() cho critic_loss/actor_loss -> hết UserWarning.

Test: 12k steps chạy nhanh gọn. Trên máy có GPU sẽ hiện Device: cuda -> nhanh hơn nữa.
