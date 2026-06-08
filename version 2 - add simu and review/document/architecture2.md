# BatteryClaw — Kiến trúc hệ thống (bản hiện tại)

Tài liệu mô tả kiến trúc thực tế của BatteryClaw ở trạng thái hiện tại: sản phẩm đã
chạy thật end-to-end trên máy, engine điều khiển phần cứng thật (độ sáng / CPU /
refresh / wifi), đọc dòng xả pin thật, online learning chạy ngầm, đóng gói & bán
được qua license server.

Sơ đồ dùng dạng ASCII trực quan.

---

## 1. Tổng quan toàn hệ thống

Hai phía tách biệt: **máy khách hàng** và **server người bán**. Lõi là vòng lặp
Engine ↔ Brain qua Named Pipe.

```
┌───────────────────────────── PHÍA KHÁCH HÀNG (máy người dùng) ─────────────────────────────┐
│    ┌─────────────────────────┐                                                             │
│    │   BatteryClaw.exe       │  ← điểm vào duy nhất (App GUI + License Gate)               │
│    │   (PyInstaller, Admin)  │                                                             │
│    └───────────┬─────────────┘                                                             │
│                │ khởi động ngầm                                                            │
│        ┌───────┴────────┐                                                                  │
│        ▼                ▼                                                                  │
│  ┌───────────┐     ┌──────────────┐      ┌───────────────┐                                 │
│  │ Engine C# │◄───►│  RL Brain    │─────►│  ONNX Policy  │                                 │
│  │ (.exe)    │pipe │  (Python,    │ infer│  15 obs→7 act │                                 │
│  └─────┬─────┘JSON │  trong app)  │      └───────────────┘                                 │
│        │           └──────┬───────┘                                                        │
│        │                  │ online learning → %APPDATA%\BatteryClaw\state                  │
│        │ đọc state /       ▼                                                               │
│        │ thực thi lệnh  ┌──────────────────────────┐                                       │
│        ▼                │  Dashboard Web           │◄─ app mở                              │
│  ┌──────────────────────────┐ │  127.0.0.1 (Task Manager │                                 │
│  │  Phần cứng Windows       │ │  style, Chart.js offline)│                                 │
│  │  Brightness/CPU/Refresh/ │ └──────────────────────────┘                                 │
│  │  Wifi / Pin              │                                                              │
│  └──────────────────────────┘                                                              │
└────────────────────────────────────────────────────────────────────────────────────────────┘
                │  activate / verify key                       ▲ upload ẩn danh (tùy chọn)
                ▼                                              │
┌───────────────────────────── PHÍA NGƯỜI BÁN (server) ────────┼──────────────────────────────┐
│   ┌────────────────────┐      ┌──────────────────┐    ┌──────┴───────────┐                  │
│   │  Trang Admin       │────► │  License Server  │───►│  SQLite          │                  │
│   │  tạo/quản lý key   │      │  (FastAPI)       │    │  keys + logs     │                  │
│   └────────────────────┘      └──────────────────┘    └──────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Vòng lặp điều khiển lõi (Engine ↔ Brain)

Engine đọc state nhanh (~1s); brain quyết định mỗi 10s rồi engine thực thi lên phần
cứng thật. Contract 15→7 bất biến.

```
   ENGINE C# (.exe, Admin)                    RL BRAIN (Python)
   ───────────────────────                    ─────────────────
   1. Thu thập state thật                        4. state_to_obs: dict → 15 floats [0,1]
      • Pin %, dung lượng (WMI)                         │
      • CPU load (GetSystemTimes)                       ▼
      • Nhiệt độ, RAM, app                       5. ONNX policy: 15 obs → 7 action
      • Brightness THẬT (WMI)                           │
      • Refresh THẬT (user32)                           ▼
      • Discharge THẬT (WMI ưu tiên) ──┐         6. modes.apply (feedback người dùng)
              │                        │                │
              ▼  JSON state            │                ▼
   ──────► Named Pipe ─────────────────┼──────►  7. constraints.clamp (safety)
   \\.\pipe\BatteryClaw                │                │
              ▲  JSON action           │                ▼
              │                        │         8. command dict → JSON
   3. Thực thi lệnh lên phần cứng ◄────┼──────      (cpu_max, brightness, refresh_hz,
      • SetBrightness (WMI)            │             wifi_save, defer ...)
      • SetCpuMax (powercfg)           │
      • SetRefreshHz (user32)          └──────  9. (online) lưu (state,action,reward)
      • SetWifiPowerSave (powercfg)                  vào replay buffer
      • Throttle app nền (EcoQoS)
```

---

## 3. Observation & Action Contract (15 → 7)

Khớp tuyệt đối giữa 3 nơi: `battery_env._get_obs` (simulator), `rl_brain.state_to_obs`
(deploy), JSON từ engine C#.

```
  OBSERVATION (15 chiều, chuẩn hóa [0,1])         ACTION (7 chiều)
  ────────────────────────────────────────        ──────────────────────────
   0  battery_pct          8  gpu_power            0  cpu_throttle  [0.2,1]
   1  cpu_load             9  discharge  ★          1  brightness    [0.3,1]
   2  cpu_temp            10  refresh_hz            2  defer_tasks   {0,1}
   3  workload_group      11  wifi_active           3  gpu_switch    (bỏ qua*)
   4  brightness          12  audio_active          4  refresh_mode  {0,1,2}
   5  throttle_max        13  ram_pressure          5  wifi_save     {0,1}
   6  time_norm           14  time_of_day           6  charge_limit  (bỏ qua*)
   7  gpu_type

   ★ discharge: tín hiệu quan trọng nhất; lấy từ WMI DischargeRate thật.
   * gpu_switch & charge_limit: AI vẫn xuất, engine BỎ QUA an toàn
     (Windows quản GPU per-app; charge_limit phụ thuộc hãng máy).
```

refresh_mode (0/1/2) → brain map sang Hz thật (60/120/144) gửi engine.

---

## 4. Cấu trúc thư mục

```
batteryclaw/
├── commons/         constants.py — nguồn hằng số chuẩn hóa DUY NHẤT
├── simulator/       battery_env.py (12 workload, 6 máy, F1-F8) + train.py (curriculum 4 phase)
├── brain/           rl_brain.py — state_to_obs, ONNX infer, override an toàn, online loop
├── engine_dotnet/   Engine C# (.NET) — bản deploy chính:
│   ├── Program.cs              serve loop + thực thi action
│   ├── State/                  SystemStateCollector — thu thập 15 state thật
│   ├── Control/                HardwareControl — đặt brightness/CPU/refresh/wifi  ◄ MỚI
│   ├── Throttle/               ProcessThrottler (EcoQoS)
│   └── Etw/ Ml/ Battery/ Tasks/  ETW, WinML, BatteryReport, TaskScheduler
├── online/          buffer/ finetune/(ewc) safety/ personalize/ feedback/ + online_loop
├── worldmodel/      world model (Phase 2) — dự phòng
├── advanced/        sac/ hierarchy/ planning/ memory(lstm) — kho nghiên cứu, KHÔNG deploy
├── app/             buy_business.py — GUI + license gate (điểm vào)
├── server/          server.py — FastAPI license server
├── dashboard/       web Task-Manager-style + Chart.js offline
├── engine/          (C++ cũ — không dùng trong bản deploy)
└── build_business.ps1
```

---

## 5. Engine C# — module & nguồn dữ liệu thật

```
  ┌────────────────────────────────────────────────────────────────┐
  │  SystemStateCollector  — THU THẬP (đọc)                        │
  │   Pin %, plugged    ← Win32 GetSystemPowerStatus               │
  │   Dung lượng mWh    ← WMI BatteryStatus                        │
  │   Discharge ★       ← WMI DischargeRate (ưu tiên)             │
  │                       fallback: ETW → ước lượng ΔmWh/Δh        │
  │   CPU load          ← GetSystemTimes                           │
  │   Nhiệt độ          ← WMI thermal (fallback 45°C nếu chặn)     │
  │   Brightness        ← WMI WmiMonitorBrightness  ◄ đọc THẬT     │
  │   Refresh           ← user32 EnumDisplaySettings               │
  │   RAM, app          ← GlobalMemoryStatusEx, foreground win     │
  ├────────────────────────────────────────────────────────────────┤
  │  HardwareControl  — THỰC THI (đặt)              ◄ MỚI          │
  │   SetBrightness     → WMI WmiMonitorBrightnessMethods          │
  │   SetCpuMax         → powercfg (max processor state)           │
  │   SetRefreshHz      → user32 ChangeDisplaySettingsEx           │
  │   SetWifiPowerSave  → powercfg (wireless policy)               │
  │   (chỉ gọi khi giá trị đổi; lỗi nuốt an toàn)                  │
  ├────────────────────────────────────────────────────────────────┤
  │ProcessThrottler (EcoQoS) · ETW · WinML+DirectML · BatteryReport│
  └────────────────────────────────────────────────────────────────┘

  Discharge resolve (fix gần nhất):
     WMI > 1mW   → dùng WMI       (đáng tin: máy thật trả 6-12W)
     else ETW>100 → dùng ETW
     else        → giá trị ước lượng từ ΔRemainingCapacity
```

Hai chế độ: `--serve` (IPC cho brain Python) và `--standalone` (engine tự inference WinML).

---

## 6. Phase 3 — Vòng quyết định khi bật Online Learning

```
   obs (15)
     │
     ▼
   ┌──────────────┐   action thô (7)
   │ ONNX policy  │ ──────────────┐
   └──────────────┘               ▼
                          ┌─────────────────┐
                          │ modes.apply     │  "Nhanh hơn"/"Tiết kiệm hơn",
                          │ (3.4)           │  "Họp"/"Pin yếu" (tự hết hạn)
                          └────────┬────────┘
                                   ▼
                          ┌─────────────────┐  lớp CUỐI không vượt được:
                          │ constraints.    │  CPU<95°C, không tắt dGPU khi game,
                          │ clamp (3.5)     │  brightness ≥ sàn an toàn
                          └────────┬────────┘
                                   ▼
                            gửi engine → phần cứng

   song song (máy nhàn >5 phút):
   replay buffer (10k) → fine-tune LR 1e-5 + EWC → validate → rollback nếu tệ
   state ghi tại %APPDATA%\BatteryClaw\state (luôn ghi được dù cài Program Files)
```

---

## 7. Simulator & Training (curriculum 4 phase)

```
   battery_env.py  (12 workload × 6 máy × F1-F8)
   F1 action delay   F5 lịch sạc theo thói quen
   F2 spike workload F6 quán tính nhiệt theo dòng máy
   F3 pin phi tuyến  F7 reward theo profile (gắn độ nhạy người dùng)
   F4 curriculum     F8 stress test phase 4
        │
        ▼  train.py: PPO, net [256,256], 8 envs
   ┌───────────────────────────────────────────────────┐
   │ Phase 1 (12%)  difficulty 1  ultrabook, dễ        │
   │ Phase 2 (33%)  difficulty 2  6 máy + 12 workload  │  độ khó tăng dần
   │ Phase 3 (43%)  difficulty 3  bật F1/F2/F3 vừa     │
   │ Phase 4 (12%)  difficulty 4  kịch khung (stress)  │
   └───────────────────────────────────────────────────┘
        │  EvalCallback lưu best model (eval ở difficulty 3)
        ▼
   export ONNX TỪ BEST MODEL → batteryclaw_policy.onnx (15→7)
```

---

## 8. Luồng License & Phân phối (thương mại)

```
   NGƯỜI BÁN                                    KHÁCH HÀNG
   server.py (FastAPI) chạy nền
        │
   trang admin /admin (token)
        │  tạo key BC-XXXX-XXXX-XXXX
        ▼
   [key trong SQLite] ──── gửi key + zip ────► giải nén, chạy BatteryClaw.exe (Admin)
                                                     │
                          POST /api/activate ◄───────┤ Server URL + Email + Key + HardwareID
   khóa key vào HardwareID ───────────────────►      │ (key đã dùng máy khác → từ chối)
                                                     ▼
                          POST /api/verify  ◄──── mỗi lần mở (offline grace nếu mất mạng)
                                                     │
                                                bấm Start → tối ưu pin
```

Tier (Free/Basic/Pro/Lifetime) lấy từ field server trả khi `/api/verify`.

---

## 9. Đóng gói bản phân phối (build_business.ps1)

```
   build_business.ps1 (Admin)
     ├─ 1. (tùy chọn) train → simulator/models/batteryclaw_policy.onnx
     ├─ 2. dotnet publish engine C# --self-contained (khách không cần cài .NET)
     ├─ 3. PyInstaller gói app+brain+online → BatteryClaw.exe
     │        --onefile --uac-admin
     │        --collect-submodules online        ◄ fix: gom submodule online
     │        --hidden-import replay_buffer ...    (online learning chạy được trong exe)
     └─ 4. → dist/BatteryClaw_business/  (zip gửi khách)
              ├── BatteryClaw.exe
              ├── engine/  (self-contained .NET)
              └── models/batteryclaw_policy.onnx
```

---

## 10. Mức quyền & bảo mật

```
   CẦN QUYỀN ADMIN:
     • Engine: đặt brightness/CPU/refresh/wifi, ETW, EcoQoS
     • App chạy elevated → engine con cùng quyền (tránh pipe "Access denied")
   GHI Ở ĐÂU:
     • config/license, online state, dashboard → %APPDATA%\BatteryClaw\
     • KHÔNG ghi cạnh exe (Program Files chặn ghi)
   CHỐNG LẬU:
     • key khóa vào HardwareID (ổ đĩa + mainboard + card mạng)
     • verify online mỗi lần mở; offline grace có hạn
```

---

## Nguyên tắc thiết kế xuyên suốt

- **Contract 15→7 bất biến** — mọi nâng cấp giữ nguyên, model cũ/mới thay thế nhau
  được, không phá tương thích.
- **Một nguồn sự thật** cho hằng số chuẩn hóa: `commons/constants.py`.
- **Học trong simulator, tinh chỉnh trên máy thật** — không train từ đầu trên máy
  khách; online learning chỉ fine-tune nhẹ có rollback.
- **Engine chỉ thực thi cái phần cứng thật làm được** — gpu_switch/charge_limit bỏ
  qua an toàn thay vì giả vờ làm.
- **An toàn nhiều lớp** — override khi plugged/pin yếu, constraints clamp cuối, rollback
  online learning, lỗi phần cứng nuốt không làm sập engine.
