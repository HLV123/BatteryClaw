# Vòng 13 — Sửa theo code review simulator (2026-06-06)

### BUG-01 (sửa — cần trước khi train dài)
train.py còn os.makedirs("models"/"logs") TƯƠNG ĐỐI trong train() → tạo thư mục
rác ở CWD khi chạy từ gốc project. Đã: thêm LOGS_DIR anchor ở module level, xóa 2
dòng tương đối, eval_cb dùng LOGS_DIR. Test: chạy từ gốc KHÔNG còn models/logs rác,
model vào đúng simulator/models/.

### BUG-02 (sửa — warmup peek)
Action queue lúc warmup dùng peek queue[0] → action đầu episode chạy lặp 2-3 lần
(delay 1-2). Đã đổi: khi queue chưa đủ delay, dùng action MẶC ĐỊNH trung tính
[0.85,0.80,0,1,0.5,0,0] thay vì lặp action đầu.

### DESIGN-02 (sửa — dead zone obs[10] của máy 165Hz)
Máy panel=165 + công thức chia (165-60) khiến obs[10] max chỉ tới 0.8 → dead zone
[0.8,1.0]. Đã: (1) đổi máy 165Hz → 144Hz (khớp PANEL_MAX_HZ, máy thật MSI 144Hz);
(2) chuẩn hóa obs[10] chia (PANEL_MAX_HZ-60)=(144-60) ở CẢ battery_env VÀ rl_brain
→ 144Hz cho obs[10]=1.0, hết dead zone, train/deploy vẫn khớp. Verify: env và
rl_brain cùng cho obs[10]=1.0 @144Hz. 11/11 test PASS.

### DESIGN-01 (ghi chú — không sửa, đúng review)
F7 multi-profile là 1 policy THỎA HIỆP (model ONNX không thấy profile lúc deploy).
Đây là lựa chọn (c) reward shaping, không sai, chỉ cần document: "model tối ưu cho
người dùng trung bình; cực battery_saver/performance được phục vụ kém hơn model
chuyên dụng". Cá nhân hóa thật cần train 3 model riêng (dài hạn) hoặc thêm profile
vào obs (phá contract). Để dài hạn.

---

# Vòng 14 — Dọn 2 dòng stale theo review v2 (2026-06-06)

### STALE-01: REFRESH_EXTRA_FACTOR bỏ key 165
Sau khi đổi máy 165Hz→144Hz (vòng 13), key 165 trong REFRESH_EXTRA_FACTOR không
bao giờ được tra → dead entry. Đã bỏ: {60:1.00, 120:1.12, 144:1.18}.

### STALE-02: docstring module bỏ "165Hz"
Docstring ghi "panel 60/120/144/165Hz" → sửa thành "panel 60/120/144Hz" cho khớp
thực tế (không còn máy 165Hz).

Cả 2 vô hại, chỉ dọn cho sạch. env_checker PASS, obs trong [0,1], 11/11 test PASS.
Không còn chuỗi "165" nào trong battery_env.py.

---

# Vòng 15 — Sửa từ log inference thật trên máy (2026-06-06)

Từ rl_brain.log thật (600+ step): Disch luôn 1mW, action ép tiết kiệm sát sàn,
online learning báo "No module named replay_buffer". 4 nhóm sửa:

### 1. FIX Disch=1mW (engine mù dòng xả — nghiêm trọng nhất)
SystemStateCollector: nhiều laptop (MSI) báo WMI DischargeRate=0 dù đang xả →
obs[9] (discharge, giác quan QUAN TRỌNG NHẤT) luôn 0. Đã: khi DischargeRate<=1 và
đang chạy pin, ƯỚC LƯỢNG discharge từ tốc độ tụt RemainingCapacity giữa 2 lần đọc
(delta_mWh / delta_giờ). Model không còn chạy với giác quan chính bị mù.

### 2. FIX online learning chết trong exe
build_business.ps1: online/ import submodule qua sys.path.insert động → PyInstaller
không gom (lỗi "No module named replay_buffer"). Đã thêm --paths cho từng thư mục
con (online/buffer, safety, finetune, personalize, feedback) + --collect-submodules
online + --hidden-import 10 module. Test: 10/10 submodule import OK với paths.

### 3. Nới override che AI
rl_brain: khi plugged trước ép cứng brightness>=0.70, throttle>=0.80 → che quyết
định AI (Br nhảy 30->70 là do code, không phải AI). Đã nới: brightness>=0.45,
throttle>=0.60, để AI tự quyết phần lớn.

### 4. Model bớt cực đoan + export tốt hơn
- export ONNX từ BEST model (EvalCallback lưu) thay vì model cuối phase 4 khắc nghiệt.
- model.policy.set_training_mode(False) trước export (eval mode, ổn định inference).
- nhẹ phase 4: spike 2x→1.5x, pin chai 0.55-0.80 → 0.62-0.85.
- đổi tỉ lệ curriculum: phase4 20%→12%, dồn cho phase 2-3 (sweet spot).
- eval ở difficulty 3 (thực tế) thay vì 4 (stress) để chọn best model thực dụng.

Test: train curriculum 4 phase OK, export best model OK, ONNX 15→7 OK, 11/11 PASS.
Cần train lại 5M steps để ra model mới.

---

# Vòng 16 — Nối action AI vào phần cứng THẬT (2026-06-07)

PHÁT HIỆN: engine chỉ thực thi 1/7 action (defer). Brightness/CPU/refresh/wifi
nhận rồi BỎ -> "log Br:45% mà màn hình 100%". AI suy nghĩ đúng nhưng chân tay
chưa nối với não.

XÁC NHẬN TRÊN MÁY THẬT (HardwareTest + HardwareTest2): cả 4 cơ chế chạy được:
brightness (WMI WmiSetBrightness) đổi thật 35/90%, refresh (ChangeDisplaySettingsEx)
đổi thật 60/144Hz, CPU throttle (powercfg) lệnh OK, wifi (powercfg policy) OK.

ĐÃ LÀM:
- Thêm engine_dotnet/Control/HardwareControl.cs: SetBrightness/ReadBrightness (WMI),
  SetCpuMax (powercfg max proc state), SetRefreshHz/ReadRefreshHz
  (ChangeDisplaySettingsEx, chỉ đặt khi máy hỗ trợ Hz đó), SetWifiPowerSave (powercfg).
  Cơ chế an toàn: chỉ gọi API khi giá trị MỤC TIÊU đổi (tránh spam mỗi 10s); lỗi nuốt.
- Program.cs HandleActionJson: nối brightness, cpu_max, refresh_hz, wifi_save (ngoài
  defer đã có). Thêm using Control.
- SystemStateCollector: đọc brightness THẬT (HardwareControl.ReadBrightness) thay
  hardcode 80.
- rl_brain.py: command thêm "refresh_hz" (map mode 0/1/2 -> 60/120/144) cho engine
  đặt refresh đúng.

Test: HardwareTest2 (dùng đúng HardwareControl.cs) trên máy thật — brightness đổi
35->90 thật, refresh 60->144 thật, khôi phục OK. Ngoặc 8 file engine cân. 11/11 PASS.

CHƯA NỐI (không khả thi/không chắc, đã nói rõ): GPU switch (Windows tự quản per-app,
không ép được từ ngoài), charge_limit (phụ thuộc hãng, MSI có tool riêng, không có
API Windows chuẩn). 2 cái này AI vẫn xuất nhưng engine bỏ qua an toàn.

---

# Vòng 17 — Sửa bug Disch=1mW gốc rễ (2026-06-07)

CHẨN ĐOÁN BẰNG DỮ LIỆU THẬT (BatteryProbe trên máy):
  WMI DischargeRate = 6973 / 11770 / 10161 mW  -> ĐỌC ĐƯỢC HOÀN HẢO!
  RemainingCapacity giảm thật (28261->28112).
Vậy phần cứng KHÔNG mù. Bug nằm ở engine.

GỐC RỄ: SystemStateCollector.Collect chọn discharge bằng:
    discharge = etwDischargeMw > 0 ? etwDischargeMw : dischargeWmiMw
ETW trên máy này trả ~1mW (gần như không chạy) nhưng VÌ > 0 nên nó "thắng" WMI
(6973mW) -> engine luôn gửi ~1mW. obs[9] mù dù WMI có số thật.

FIX: đảo ưu tiên — WMI DischargeRate đáng tin hơn:
    if (wmi > 1.0)        dùng WMI         (ưu tiên, vì máy trả 6-11W thật)
    else if (etw > 100)   dùng ETW         (chỉ khi đủ lớn)
    else                  dùng ước lượng   (ReadBatteryWmi tự tính)
-> obs[9] giờ có discharge thật; phần tính "Saved" trong rl_brain cũng đúng hơn.

LƯU Ý: vòng 15 thêm ước lượng từ RemainingCapacity là dự phòng cho máy WMI mù —
máy này không cần (WMI chạy tốt), nhưng giữ lại cho máy khác.

Chỉ đổi engine C# -> build lại engine, KHÔNG cần train lại model.
