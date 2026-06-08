# BatteryClaw — Kiến trúc hệ thống

Tài liệu mô tả kiến trúc tổng thể

---

## 1. Tổng quan toàn hệ thống

Hai phía tách biệt: **máy khách hàng** và **server người bán**. Lõi là vòng lặp
Engine ↔ Brain qua Named Pipe.

```
┌───────────────────────────── PHÍA KHÁCH HÀNG (máy người dùng) ─────────────────────────────┐
│                                                                                            │
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
│        │           └──────────────┘                                                        │
│        │ đọc state / thực thi lệnh                                                         │
│        ▼                                          ┌──────────────────────────┐             │
│  ┌──────────────────────────┐                     │  Dashboard Web           │             │
│  │  Phần cứng Windows       │                     │  127.0.0.1 (Task Manager │◄─ app mở    │
│  │  CPU / GPU / Pin / Màn   │                     │  style, Chart.js offline)│             │
│  └──────────────────────────┘                     └──────────────────────────┘             │
└────────────────────────────────────────────────────────────────────────────────────────────┘
                │  activate / verify key                       ▲ upload ẩn danh (tùy chọn)
                ▼                                              │
┌───────────────────────────── PHÍA NGƯỜI BÁN (server) ────────┼──────────────────────────────┐
│   ┌────────────────────┐      ┌──────────────────┐    ┌──────┴───────────┐                  │
│   │  Trang Admin       │────► │  License Server  │───►│  SQLite          │                  │
│   │  tạo/quản lý key   │      │  (FastAPI)       │    │  keys + logs     │                  │
│   └────────────────────┘      └──────────────────┘    └──────────────────┘                  │
│                                       ▲  Dataset ẩn danh (multi-device)                     │
└───────────────────────────────────────────────────────────────────────────────────────────-─┘
```

---

## 2. Vòng lặp điều khiển lõi (Engine ↔ Brain)

Mỗi giây: engine gửi state, brain suy luận và trả action. Contract bất biến qua mọi phase.

```
  Phần cứng        Engine C#            Named Pipe         RL Brain (Python)        ONNX
  ─────────        ─────────            ──────────         ─────────────────        ────
      │                │                    │                    │                   │
      │  WMI/ETW/Win32 │                    │                    │                   │
      ├───────────────►│                    │                    │                   │
      │                │ thu thập state     │                    │                   │
      │                │ (pin,CPU,nhiệt,…)  │                    │                   │
      │                │  JSON state (15)   │                    │                   │
      │                ├───────────────────►│  đọc dòng JSON     │                   │
      │                │                    ├───────────────────►│                   │
      │                │                    │                    │ state_to_obs()    │
      │                │                    │                    ├──────────────────►│
      │                │                    │                    │   action (7)      │
      │                │                    │                    │◄──────────────────┤
      │                │                    │                    │ modes + safety    │
      │                │                    │   JSON command (7) │ (Phase 3)         │
      │                │                    │◄───────────────────┤                   │
      │                │  đọc command       │                    │                   │
      │                │◄───────────────────┤                    │                   │
      │ throttle/bright│                    │                    │                   │
      │ EcoQoS/refresh │                    │                    │ reward + buffer   │
      │◄───────────────┤                    │                    │ (--online)        │
      │                │                    │                    │                   │
      └────────────────────────── lặp lại mỗi 1 giây ────────────────────────────────┘
```

---

## 3. Observation & Action Contract (15 → 7)

Hợp đồng dữ liệu bất biến, khớp tuyệt đối giữa `battery_env`, `rl_brain`, engine.

```
   OBSERVATION (input, 15 chiều)              ACTION (output, 7 chiều)
   ─────────────────────────────             ──────────────────────────────
   [0]  battery_pct                           [0] cpu_throttle_max  [0.2 .. 1]
   [1]  cpu_load                              [1] brightness        [0.3 .. 1]
   [2]  cpu_temp_norm                         [2] defer_tasks
   [3]  workload_id / 4          ┌─────────┐  [3] gpu_switch  (<0.5 = ép iGPU)
   [4]  brightness               │  ONNX   │  [4] refresh_mode (60/120/max)
   [5]  throttle_max     ───────►│ Policy  │─►[5] wifi_save
   [6]  time_norm                │ MLP     │  [6] charge_limit (80%)
   [7]  gpu_type_norm            │ 128x128 │
   [8]  gpu_power_norm           │ tanh    │
   [9]  discharge_norm (ACPI)    └─────────┘
   [10] refresh_norm
   [11] wifi_active                  ▲  ground-truth quan trọng nhất:
   [12] audio_active                 └─ obs[9] discharge_norm (đo ACPI thật)
   [13] ram_pressure
   [14] time_of_day_norm
```

---

## 4. Cấu trúc thư mục theo phase

```
BatteryClaw/
│
├── engine/          (P1) C++ core: ACPI discharge, GPU detect, state, action
├── engine_dotnet/   (P5) C#: ETW · WinML · EcoQoS · Task Scheduler · Battery Report
├── brain/           RL brain Python (15→7) + cờ --online (P3)
├── simulator/       (P1) train PPO → ONNX
├── datacollector/   (P2) schema · data collector · reward thật
├── worldmodel/      (P2) world model f(s,a)→s' + wm_env + train_on_wm
├── online/          (P3) buffer · safety · finetune · personalize · feedback
├── advanced/        (P4) sac/ · memory/ · hierarchy/ · planning/
├── commercial/      (P6) stats_store · profiles · notifications · tiers
├── dashboard/       (P6) server localhost + static (HTML + Chart.js offline)
├── server/          license server (FastAPI) + (P2) multi-device dataset
├── app/             GUI người dùng + license gate (buy_business.py)
├── commons/         constants.py  ← single source of truth (hằng số chuẩn hóa)
└── tests/           unit test contract + bất biến (11/11 PASS)
```

---

## 5. Engine C# (Phase 5) — các module

```
                       ┌───────────────────────────────────┐
                       │           Program.cs              │
                       │     (--serve / --standalone)      │
                       └───────────────┬───────────────────┘
            ┌──────────────┬───────────┼───────────┬──────────────┬─────────────┐
            ▼              ▼           ▼           ▼              ▼             ▼
   ┌───────────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐
   │EtwPowerMonitor│ │WinMlPolicy│ │Process   │ │TaskSched │ │Battery   │ │SystemState   │
   │ 5.1 discharge │ │5.2 ONNX   │ │Throttler │ │Reader    │ │Report    │ │Collector     │
   │ realtime ~ms  │ │trên Direct│ │5.3 EcoQoS│ │5.4 task  │ │5.5 health│ │thu thập state│
   │ (cần Admin)   │ │ML (GPU)   │ │per-proc  │ │sắp chạy  │ │+ dự đoán │ │(WMI/Win32)   │
   └───────┬───────┘ └───────────┘ └──────────┘ └──────────┘ └──────────┘ └───────┬──────┘
           │ discharge                                                            │ state đầy đủ
           └──────────────────────────────────────────────────────────────────►   │
                                                                                  ▼
                                                               Named Pipe ──► rl_brain.py

   Ghi chú: ETW cần quyền Admin; không có thì tự tắt, engine vẫn chạy bình thường.
```

---

## 6. Phase 3 — Vòng quyết định khi bật Online Learning

```
   obs(15)
     │
     ▼
  ┌─────────────────┐
  │ policy(obs)     │ → command thô
  └────────┬────────┘
           ▼
  ┌─────────────────────────────┐
  │ modes.apply        (3.4)    │  Họp quan trọng / Pin yếu → ghi đè tạm thời
  └────────┬────────────────────┘
           ▼
  ┌──────────────────────────────────────────────┐
  │ constraints.clamp  (3.5)  ← LỚP CHẶN CUỐI    │  CPU<95°C · không tắt dGPU khi game
  │                            không thể vượt    │  · brightness ≥ 20%
  └────────┬─────────────────────────────────────┘
           ▼
   gửi Engine ──► thực thi
           │
           ▼
  ┌─────────────────┐    ┌───────────────────┐    máy nhàn >5'?  ┌─────────────────────────┐
  │ tính reward thật│──► │ replay buffer(3.1)│──── có ──────────►│ fine-tune + EWC (3.2)   │
  │ (reward.py)     │    └───────────────────┘                   │ validate → rollback nếu │
  └─────────────────┘                                            │ tệ hơn → deploy bản tốt │
           ▲                                                     └─────────────────────────┘
           │
  ┌────────┴───────────────────────┐
  │ pattern tracker (3.3)          │ học thói quen theo giờ → gợi ý chủ động
  └────────────────────────────────┘
```

---

## 7. Luồng dữ liệu Phase 2 (train từ dữ liệu thật)

```
   Engine (state thật, discharge ACPI)
        │  Named Pipe
        ▼
   data_collector.py
        │  ghi parquet
        ▼
   data/*.parquet  (transition s, a, s')
        │
        ├──────────────► reward.py        R = α·P + β·C + γ·L + δ·X
        │
        ├──────────────► world_model.py   f(s,a) → s'   (học delta, tốt hơn ~20× baseline)
        │                     │
        │                     ▼
        │                wm_env.py  (Gym env bọc world model)
        │                     │
        │                     ▼
        │                train_on_wm.py (PPO)
        │                     │
        │                     ▼
        │                policy_wm.onnx (15→7) ──► rl_brain.py deploy
        │
        └──(ẩn danh)──► dataset_uploader ──► server /api/dataset/upload ──► gom train model base
```

---

## 8. Luồng License & Phân phối (thương mại)

```
   Người bán (Admin)        License Server            Khách hàng         BatteryClaw.exe
   ────────────────         ──────────────            ──────────         ───────────────
        │  tạo key               │                        │                    │
        ├───────────────────────►│                        │                    │
        │  BC-XXXX-XXXX-XXXX     │                        │                    │
        │◄───────────────────────┤                        │                    │
        │  gửi zip + key                                  │                    │
        ├────────────────────────────────────────────────►│                    │
        │                                                 │  chạy (Run as Admin)
        │                                                 ├───────────────────►│
        │                                                 │                    │ tính machine_id
        │                          /api/activate (key, email, machine_id)      │ (Hardware ID)
        │                        │◄────────────────────────────────────────────┤
        │                        │ key hợp lệ & chưa dùng?                     │
        │                        │   CÓ → lock vào machine_id → ok + số ngày   │
        │                        │   ĐÃ DÙNG máy khác → từ chối                │
        │                        ├────────────────────────────────────────────►│
        │                                                 │ vào app → bấm Start│
        │
        Lần sau mở app: /api/verify  (mất mạng → offline grace tới khi hết hạn)
```

---

## 9. Đóng gói bản phân phối (build_business.ps1)

```
   build_business.ps1  (máy người bán)
        │
        ├── 1. Train model (nếu chưa có)      simulator/train.py
        │         └──────────────────────┐
        ├── 2. dotnet publish            │     engine + .NET runtime (self-contained)
        │      --self-contained          │
        │         └─────────────────┐    │
        ├── 3. PyInstaller          │    │   app + brain + dashboard → 1 exe
        │      --onefile --uac-admin│    │
        │                  └────────┼────┼──────────┐
        ▼                           ▼    ▼          ▼
   dist/BatteryClaw_business/
        ├── BatteryClaw.exe                  (app GUI — khách bấm)
        ├── engine/BatteryClawEngine.exe     (engine, đã gói .NET)
        └── models/batteryclaw_policy.onnx   (model)
        │
        └──(zip)──► gửi khách: KHÔNG cần cài Python / .NET / thư viện
```

---

## 10. Mức quyền & bảo mật (lưu ý vận hành)

```
   ┌──────────────── Chạy quyền Admin (UAC) ─────────────────┐
   │   BatteryClaw.exe (--uac-admin)                         │
   │        │ cùng mức quyền                                 │
   │        ▼                                                │
   │   Engine C# (tiến trình con)                            │
   │        │ đủ quyền                                       │
   │        ▼                                                │
   │   ETW realtime power                                    │
   └─────────────────────────────────────────────────────────┘
     ↳ App và engine CÙNG mức quyền → tránh lỗi "Access Denied"
       trên Named Pipe. Engine cần Admin để đọc ETW.

   ┌──────────────── Bảo mật server ──────────────────┐
   │  • BC_ADMIN_TOKEN mạnh (chặn token yếu khi start)│
   │  • Rate limiting theo IP (BEHIND_PROXY → đọc     │
   │    X-Forwarded-For khi sau nginx)                │
   │  • HTTPS qua nginx khi lên production            │
   │  • Key lock theo Hardware ID (chống xài lậu)     │
   └──────────────────────────────────────────────────┘
```

---

## Nguyên tắc thiết kế xuyên suốt

- **Một contract bất biến 15 obs / 7 action** — mọi phase tôn trọng, nên các thành phần thay thế được cho nhau (PPO ↔ SAC ↔ world-model policy) mà không phá vỡ hệ thống.
- **Mỗi file một nhiệm vụ** — file ngắn, tên rõ, dễ đọc và bảo trì.
- **Single source of truth** — hằng số chuẩn hóa (GPU/discharge max…) gom ở `commons/constants.py`, có test tự động chống lệch giữa các module.
- **An toàn khi thiếu** — module/exe vắng thì tắt nhẹ, không làm sập app.
- **Tách biệt Engine (native, đặc quyền Windows) và Brain (Python, logic AI)** qua Named Pipe — mỗi bên thay đổi độc lập, miễn giữ đúng giao thức JSON.
