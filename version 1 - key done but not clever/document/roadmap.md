# BatteryClaw — Roadmap phát triển

Trợ lý tối ưu pin laptop Windows dùng Reinforcement Learning. 
Tài liệu này ghi lại toàn bộ chặng đường: từ bản thử nghiệm đầu tiên, qua 6 phase, đến khi thành sản phẩm thương mại chạy thật trên máy và bán được.

Kiến trúc tổng quát:

```
  Engine (C# / C++)    →    Named Pipe (JSON)     →  RL Brain (Python)    →  ONNX policy
  thu thập state            \\.\pipe\BatteryClaw     suy luận hành động      15 obs → 7 action
  + thực thi lệnh                                    + online learning
```

---

## Bảng tổng quan

| Giai đoạn | Tên | Trạng thái |
|---|---|---|
| V0 | Prototype | ✅ Đường ống cơ bản chạy thông |
| Phase 1 | Nền tảng thật (obs 15 / action 7, ACPI) | ✅ (GPU switch & charge_limit là safe-stub) |
| Phase 2 | Simulator thật (data + world model + reward) | ✅ |
| Phase 3 | Online Learning (EWC, safety, feedback) | ✅ |
| Phase 4 | Kiến trúc tiên tiến (SAC/LSTM/HRL/MPC) | ✅ (khối dự phòng) |
| Phase 5 | Hệ sinh thái Windows (C#/.NET) | ✅ |
| Phase 6 | Thương mại hóa & Dashboard | ✅ |
| Sau P6 | Review + deploy thật + đóng gói bán | ✅ Sản phẩm chạy thật, bán được |

---

## Version 0 — Bản thử nghiệm đầu tiên (Prototype)

Mục tiêu: chứng minh ý tưởng "agent học cách tiết kiệm pin" khả thi.

- Môi trường giả lập pin (`battery_env`) đơn giản: pin, CPU, độ sáng.
- Observation/action vector nhỏ (ban đầu 7 obs → 3 action).
- Engine C++ tối giản đọc trạng thái, giao tiếp qua named pipe.
- Brain Python nhận state, trả action cố định/heuristic để kiểm tra đường ống.
- Train thử bằng PPO trên simulator, xuất ONNX.

Kết quả: đường ống Engine ↔ Pipe ↔ Brain ↔ ONNX chạy thông end-to-end ở mức cơ bản.

---

## Phase 1 — Nền tảng thật ("từ simulator giả sang dữ liệu thực")

Nâng từ mô hình đồ chơi lên mô hình đủ giàu để phản ánh máy thật, đo bằng số liệu thật.

- **1.1 Đo điện năng thật**: discharge rate qua ACPI (`power_monitor.cpp`) — số liệu ground-truth thay vì ước tính.
- **1.2 Phát hiện GPU**: iGPU/dGPU + công suất qua PDH (`gpu_monitor.cpp`).
- **1.3 GPU switching**: phát hiện thật + lớp bảo vệ thật, nhưng thao tác ghi phần cứng (registry Optimus / PnP disable / ACPI MUX) là **safe-stub** — khóa sau cờ build `BATTERYCLAW_ENABLE_HW_GPU_SWITCH` vì tắt nhầm dGPU có thể mất hiển thị.
- **1.4 Observation 7 → 15 chiều**: battery %, CPU load, nhiệt độ CPU, workload, độ sáng, throttle, thời gian, loại GPU, công suất GPU, tốc độ xả (ACPI), tần số màn hình, wifi, audio, áp lực RAM, thời điểm trong ngày.
- **1.5 Action 3 → 7 chiều**: throttle CPU [0.2,1], độ sáng [0.3,1], hoãn tác vụ, chuyển GPU, chế độ tần số quét, tiết kiệm wifi, giới hạn sạc (charge_limit cũng là safe-stub, làm thật ở Phase 5).
- Cập nhật chu kỳ đọc state 2s → 1s.
- **Lớp bảo vệ an toàn**: không tắt dGPU khi đang game/đồ họa hoặc có tiến trình CUDA hoặc đang sạc; pin < 10% → ép tiết kiệm tối đa.
- Thứ tự 15 obs khớp tuyệt đối giữa 3 nơi: `battery_env._get_obs`, `rl_brain.state_to_obs`, và JSON từ engine.

---

## Phase 2 — Simulator thật ("train trên dữ liệu thật, không phải số ước tính")

Chuyển từ "học trong giả lập thuần" sang "học từ dữ liệu máy thật".

- **2.1 Data collector**: chạy ngầm, chỉ quan sát, ghi transition (state 15 + action 7 + raw 10 + reward 5 + next_state 15) ra parquet theo schema chuẩn (`datacollector/schema.py`). Thiếu pandas/pyarrow thì fallback ghi `.jsonl`.
- **2.2 World Model** (`worldmodel/`): học delta `next_state = state + MLP(state,action)` từ dữ liệu thật → tạo `wm_env` (Gym env bọc world model) để train policy trên động học thật. Trên dữ liệu test, world model tốt hơn ~20× so với baseline "giữ nguyên state".
- **2.3 Reward function thật** (`reward.py`): `R = α·R_primary + β·R_comfort + γ·R_longevity + δ·R_context`. R_primary đo discharge ACPI; phạt throttle dưới nhu cầu; thưởng giữ pin <80% khi sạc; **−1 nếu tắt dGPU khi đang game**. Trọng số chỉnh được.
- **2.4 Multi-device dataset**: client gửi dữ liệu **ẩn danh** (device_hash không đảo ngược được, device_class để gom máy giống nhau, loại bỏ tên app/email/machine_id gốc ở cả client lẫn server). Server gom để train model base.
- Phân loại workload (idle/browse/office/compile/game) từ CPU + GPU.

---

## Phase 3 — Online Learning ("càng dùng lâu càng thông minh hơn")

Để agent thích nghi với thói quen riêng của từng người dùng theo thời gian. Tùy chọn, bật bằng cờ `--online`.

- **3.1 Replay buffer**: vòng tròn 10.000 transition, tự ghi đè cũ nhất, lưu/nạp `.npz`.
- **3.2 Fine-tuning offline** khi máy nhàn: LR rất nhỏ (1e-5), **EWC** chống quên (catastrophic forgetting), validate trên tập giữ lại, **rollback** nếu tệ hơn.
- **3.3 Personalization**: `PatternTracker` học thói quen theo 24 khung giờ, trả gợi ý "save/perform/neutral" để chủ động trước thay vì chỉ phản ứng.
- **3.4 User feedback**: nút "Nhanh hơn"/"Tiết kiệm hơn" → reward; chế độ tạm thời "Họp quan trọng"/"Pin yếu" tự hết hạn.
- **3.5 Safety**: lớp lọc cuối cùng không thể vượt — CPU<95°C, không tắt dGPU khi game, không hạ brightness <20%; checkpoint mỗi ngày, giữ 7 ngày, auto-rollback.
- **Thứ tự vòng quyết định**: `policy(obs) → modes.apply (3.4) → constraints.clamp (3.5) → gửi engine`.

---

## Phase 4 — Kiến trúc Model tiên tiến ("từ policy phẳng sang agent thực sự thông minh")

Bộ công cụ RL mạnh hơn — model có bộ nhớ và biết lập kế hoạch, không chỉ phản xạ.

- **4.1 SAC** (Soft Actor-Critic) thay PPO: off-policy (học từ replay buffer Phase 3), tối ưu entropy (auto-temperature) explore tốt, twin critic + soft update giảm overestimation. Xuất chỉ actor (deterministic) → ONNX (15→7), deploy y hệt qua rl_brain.
- **4.2 LSTM policy**: nhìn 30 state gần nhất (`SequenceBuffer` rolling window) → nhận ra mẫu thời gian ("vừa mở IDE → sắp compile"). Hidden 128, nhẹ, chạy được trên laptop.
- **4.3 Hierarchical RL** (2 tầng): **Manager** (mỗi 5 phút) chọn chế độ SAVE_MAX/BALANCED/PERFORMANCE → mục tiêu discharge; **Worker** (mỗi 10 giây) goal-conditioned (obs 15→16 chiều) chọn action bám mục tiêu.
- **4.4 Model-Based Planning (MPC)**: random-shooting dùng world model Phase 2 — sinh K chuỗi action, rollout "trong đầu", chọn chuỗi tốt nhất, trả action đầu (receding horizon).

(Phase 4 là kho thuật toán dự phòng; đường deploy mặc định dùng policy phẳng Phase 1/2 cho gọn. Bật khối nào vào luồng deploy là tùy chọn.)

---

## Phase 5 — Engine C# khai thác sâu Windows

Viết lại engine bằng C#/.NET để tận dụng API Windows hiện đại, thay engine C++.

- **5.1 ETW** (Event Tracing for Windows): đọc công suất/điện năng realtime.
- **5.2 WinML + DirectML**: chạy ONNX policy tăng tốc bằng GPU.
- **5.3 Process Power Throttling (EcoQoS)**: ghìm tiến trình nền tiết kiệm điện (chỉ Windows 11 build 22000+).
- **5.4 Task Scheduler Reader**: phát hiện tác vụ nặng sắp chạy (updater, antivirus) để cảnh báo sạc trước.
- **5.5 Battery Report**: đọc sức khỏe pin thật (FullChargeCapacity vs Design), học degradation curve của chính máy → dự đoán chai pin. (Máy MSI test: design 52007, full 33026 → health ~63.5%, ~13.4%/năm, dự đoán ~50% sau 1 năm — đã kiểm chứng bằng `test_degradation.py`.)

Hai chế độ chạy: **`--serve`** (làm IPC server cho rl_brain Python, giống engine C++ cũ) và **`--standalone`** (engine tự inference bằng WinML, không cần Python). Giữ nguyên pipe `\\.\pipe\BatteryClaw` + JSON nên rl_brain (kể cả `--online`) kết nối được như cũ.

---

## Phase 6 — Thương mại hóa

Biến công cụ kỹ thuật thành sản phẩm có thể bán.

- **Stats store**: lưu thống kê tiết kiệm theo ngày/giờ.
- **Profiles**: Balanced / Battery saver / Performance.
- **Notifications**: toast Windows 11 (winotify).
- **Tiers**: Free (chỉ CPU throttle) / Basic 29k (+ GPU switching, dashboard, pin health) / Pro 59k (+ online learning, hồ sơ tùy chỉnh) / Lifetime 499k (+ planning Phase 4, tất cả). Tier lấy từ field server trả khi `/api/verify`.
- **Dashboard**: web localhost kiểu Task Manager (biểu đồ pin, CPU, tiết kiệm), Chart.js nhúng offline.
- **Setup wizard** + tích hợp app (launcher, profile bridge, toaster).
- **License server** (FastAPI): bán key, kích hoạt, quản trị admin.

---

## Sau Phase 6 — Hoàn thiện, review & đưa vào chạy thật

Đây là phần lớn công sức thực tế: làm cho mọi thứ chạy được trên máy thật và bán được, qua nhiều vòng review code và debug deploy.

### A. 5 vòng code review (27 vấn đề thực tế đã sửa)

- **Vòng 1 (22 vấn đề)**: sửa bug dùng biến trước khi gán (BUG-01), admin token mặc định yếu (BUG-02), thiếu rate limiting (BUG-03), hardcode dung lượng pin (BUG-05), lệch tần số quét giữa env và brain (BUG-06), escape JSON trong C++ (QUALITY-05), cache import, exponential backoff cho pipe, done-mask cho SAC, EcoQoS check Win11, thêm unit test...
- **Vòng 2**: FastAPI lifespan (token check chạy với mọi cách deploy), dọn rate bucket chống rò bộ nhớ, parser JSON C++ chống nhầm prefix, template HTTPS, gom magic number vào `commons/constants.py`.
- **Vòng 3**: đọc X-Forwarded-For sau nginx (BEHIND_PROXY), rl_brain + battery_env dùng constants chung, bỏ dead code.
- **Vòng 4**: data_collector + wm_env dùng constants chung (khóa single-source).
- **Vòng 5**: engine C# + Phase 4 (worker, mpc_planner) dùng hằng số chuẩn hóa chung; thêm test tự động kiểm C# khớp Python.

Kết quả: toàn bộ hằng số chuẩn hóa quy về một nguồn `commons/constants.py`, 11/11 unit test PASS, dự án đạt trạng thái production-ready.

### B. Deploy thật trên máy (MSI, Windows 11, RTX 3050)

- Script `check_env.ps1`: kiểm tra môi trường (Python, thư viện, .NET, C++ tools, GPU).
- Train model thật trên simulator (PPO, ~300k steps, ~90 giây, mean reward ~1244).
- Build engine C# chạy được trên .NET 10 (qua `DOTNET_ROLL_FORWARD=Major`).
- **Sửa engine C# thu thập state thật** (`SystemStateCollector`): pin, CPU (GetSystemTimes), nhiệt độ, RAM, foreground app, discharge — trước đó `--serve` gửi toàn số 0.
- **Sửa bug pipe handle 64-bit**: ctypes `CreateFileW` không khai báo restype → handle bị cắt → "kết nối giả" → pipe đóng/mở lặp vô tận. Khai báo đúng kiểu → brain kết nối ổn định, engine nhận state thật.
- Xử lý quyền Admin: engine cần Admin cho ETW; app chạy elevated để engine con cùng quyền, tránh lỗi "Access denied" trên pipe.

### C. Hoàn thiện chất lượng & trải nghiệm

- **Vá nhiệt độ**: máy chặn đọc thermal qua WMI → trả -1 (N/A) thay vì -273°C; brain coi như 45°C trung tính.
- **Đổi toàn bộ output sang tiếng Anh** (PowerShell không hiển thị tốt tiếng Việt).
- **App GUI cho khách** (`batteryclaw_app.py` → `buy_business.py`): điểm vào duy nhất, bấm Start là tự khởi động engine ẩn + chạy brain trong thread, hiển thị pin/CPU/app/tiết kiệm live, nút Stop / Open Dashboard / chọn profile.
- **Dashboard chạy trong thread nội bộ** (import trực tiếp) để hoạt động cả khi đóng gói thành exe.

### D. Đóng gói & bán hàng thương mại

- **License gate** (`buy_business.py`): màn hình kích hoạt 3 bước (Server URL → Email → API Key), verify online mỗi lần mở, offline grace khi mất mạng, khóa key theo Hardware ID (machine_id) chống dùng lậu trên máy khác.
- **Engine self-contained**: `dotnet publish --self-contained` gói luôn .NET → máy khách không cần cài .NET.
- **`build_business.ps1`**: tự train model (nếu cần) → build engine → đóng gói app + brain thành một `BatteryClaw.exe` (PyInstaller, `--uac-admin`) → tạo thư mục `dist\BatteryClaw_business\` để zip gửi khách.
- **License server** vận hành: admin tạo key (BC-XXXX-XXXX-XXXX), đặt số ngày, giá, ghi chú; key activate lock vào máy khách.

### E. Trạng thái cuối

Sản phẩm chạy thật end-to-end trên máy thật và đã test bán được:

- Người bán: train model → chạy server → tạo key → `build_business.ps1` → gửi zip + key.
- Khách hàng: giải nén → chạy `BatteryClaw.exe` (Admin) → nhập Server URL + Email + Key → kích hoạt → bấm Start. Không cần cài Python, .NET hay thư viện nào.

---

## Hướng phát triển tương lai (chưa làm, gợi ý)

- Machine ID bền hơn (`uuid.getnode()` có thể đổi khi máy nhiều card mạng → dùng UUID máy / serial ổ đĩa).
- HTTPS cho license server khi lên VPS thật (đã có hướng dẫn `DEPLOY_HTTPS.md`).
- Tự động gia hạn key, trang admin quản lý khách đẹp hơn.
- Backlog kiến trúc: dùng thư viện JSON đầy đủ trong C++, sinh header C++ tự động từ schema, tích hợp Phase 4 (hierarchy/MPC) vào đường deploy chính.
