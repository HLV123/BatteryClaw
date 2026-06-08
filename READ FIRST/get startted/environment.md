# BatteryClaw — Môi trường & Phụ thuộc (Environment)

Tài liệu liệt kê **tất cả** runtime, SDK, công cụ và thư viện cần thiết để chạy trọn
vòng đời dự án: từ huấn luyện AI → build engine → đóng gói → vận hành license server
→ bán cho khách. Phân theo **vai trò** để biết cái nào cần ở đâu.

Đường dẫn dự án: `E:\batteryclaw`

---

## 0. Tóm tắt nhanh — ai cần cài gì

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │  MÁY NGƯỜI BÁN (bạn) — cần cài đầy đủ để train + build + bán           │
   │   • Windows 11                                                         │
   │   • Python 3.10 + các thư viện (mục 2)                                 │
   │   • .NET 10 SDK (build engine C#)                                      │
   │   • PyInstaller (đóng gói exe)                                         │
   │   • (tùy chọn) CMake — chỉ nếu động đến engine C++ cũ                  │
   ├────────────────────────────────────────────────────────────────────────┤
   │  MÁY KHÁCH HÀNG — KHÔNG cần cài gì                                     │
   │   • Chỉ cần Windows 10/11, chạy BatteryClaw.exe với quyền Admin        │
   │   • Python, .NET, thư viện đều đã gói sẵn trong exe (self-contained)   │
   └────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Hệ điều hành & phần cứng

| Thành phần | Yêu cầu | Ghi chú |
|---|---|---|
| Hệ điều hành | Windows 11 (build 22000+) | EcoQoS cần Win11 22000+; máy test build 26200 |
| CPU | x64 | dùng powercfg để throttle |
| GPU | bất kỳ | DirectML chạy WinML trên NVIDIA/AMD/Intel; máy test RTX 3050 + Intel UHD |
| Pin | laptop có pin | đọc WMI BatteryStatus; máy test health ~63% |
| Quyền | **Administrator** | bắt buộc để đặt brightness/CPU/refresh, ETW, EcoQoS |

Máy khách chỉ cần Windows 10/11 x64 + quyền Admin khi chạy.

---

## 2. Python (máy người bán)

### 2.1. Runtime
- **Python 3.10.11** (64-bit). Khuyến nghị đúng 3.10 vì thư viện RL test trên bản này.

### 2.2. Thư viện — phân theo vai trò

**Huấn luyện AI (train + simulator):**
| Thư viện | Vai trò |
|---|---|
| numpy | Xử lý ma trận, vector observation |
| torch | Mạng neuron, huấn luyện PPO |
| gymnasium | Khung môi trường Reinforcement Learning |
| stable-baselines3 | Thuật toán PPO (và SAC ở kho nghiên cứu) |
| onnx | Định dạng model dùng chung (export 15→7) |
| onnxruntime | Chạy suy luận ONNX tốc độ cao (cả lúc deploy) |

**Dữ liệu & world model (Phase 2):**
| Thư viện | Vai trò |
|---|---|
| pandas | Xử lý transition data |
| pyarrow | Ghi/đọc parquet (fallback jsonl nếu thiếu) |

**License server (FastAPI):**
| Thư viện | Phiên bản | Vai trò |
|---|---|---|
| fastapi | 0.115.0 | Web framework cho API license |
| uvicorn | 0.30.6 | ASGI server chạy FastAPI |
| jinja2 | 3.1.4 | Template trang admin |
| python-multipart | 0.0.12 | Nhận form data trên trang admin |
| pydantic | (theo fastapi) | Validate request body |

**App khách + giao tiếp Windows:**
| Thư viện | Vai trò |
|---|---|
| requests | Gọi API activate/verify key |
| wmi | Đọc phần cứng Windows (Windows only) |
| pywin32 (win32api) | API Windows nâng cao (Windows only) |
| winotify | Toast notification Windows 11 (Windows only) |
| tkinter | GUI app (đi kèm Python, không cài thêm) |

**Đóng gói:**
| Thư viện | Vai trò |
|---|---|
| pyinstaller | Gói app+brain thành 1 file .exe |

### 2.3. Lệnh cài nhanh tất cả
```powershell
pip install numpy torch gymnasium stable-baselines3 onnx onnxruntime ^
            pandas pyarrow ^
            fastapi==0.115.0 uvicorn==0.30.6 jinja2==3.1.4 python-multipart==0.0.12 ^
            requests wmi pywin32 winotify ^
            pyinstaller
```
(tkinter đã đi kèm Python; nếu thiếu thì cài lại Python tích chọn "tcl/tk".)

Hoặc cài từ requirements có sẵn trong dự án:
```powershell
pip install -r datacollector\requirements.txt   # train + data + world model
pip install -r server\requirements.txt           # license server
pip install -r app\requirements.txt              # app khách + Windows
pip install pyinstaller
```

---

## 3. .NET (máy người bán — build engine C#)

| Thành phần | Yêu cầu | Ghi chú |
|---|---|---|
| .NET SDK | **.NET 10** (máy đang có) | engine target `net8.0-windows10.0.19041.0` |
| Roll-forward | `DOTNET_ROLL_FORWARD=Major` | để engine .NET 8 chạy/build trên .NET 10 |
| Gói NuGet | System.Management 8.0.0 | WMI (đọc pin, brightness); tự restore khi build |

Lệnh build engine:
```powershell
cd E:\batteryclaw\engine_dotnet
$env:DOTNET_ROLL_FORWARD="Major"
dotnet build -c Release
```

Engine đóng gói **self-contained** (`dotnet publish --self-contained`) nên gói luôn
.NET runtime vào → **máy khách không cần cài .NET**.

---

## 4. Công cụ build khác (máy người bán)

| Công cụ | Bắt buộc? | Vai trò |
|---|---|---|
| PyInstaller | Có | đóng gói exe (đã liệt kê ở mục 2) |
| CMake | Không | chỉ cần nếu động đến engine C++ cũ (`engine/`) — bản deploy KHÔNG dùng |
| Git | Không | quản lý mã nguồn (tùy chọn) |

---

## 5. Hạ tầng khi BÁN THẬT (thu tiền)

Để bán cho khách ở xa và thu tiền thật, ngoài máy dev cần:

| Thành phần | Vai trò | Ghi chú |
|---|---|---|
| VPS / máy chủ công khai | chạy license server 24/7 | khách activate/verify key qua đây |
| IP tĩnh hoặc tên miền | khách nhập vào "Server URL" | thay cho localhost lúc test |
| HTTPS (chứng chỉ SSL) | bảo mật khi truyền key | có hướng dẫn `DEPLOY_HTTPS.md` |
| Python 3.10 trên VPS | chạy `server.py` | chỉ cần thư viện nhóm "license server" (mục 2.2) |
| BC_ADMIN_TOKEN mạnh | bảo vệ trang admin | KHÔNG dùng `admin-test-123` khi thật |
| Kênh thu tiền | nhận thanh toán | chuyển khoản/Zalo/MoMo... (ngoài phạm vi code) |
| Kênh giao hàng | gửi file ZIP + key | Zalo/email/Drive |

> Lúc thử local: chỉ cần chạy `server.py` trên chính máy bạn (`http://localhost:8000`),
> không cần VPS. VPS chỉ cần khi khách ở máy khác.

---

## 6. Lưu trữ runtime (chạy lúc dùng thật)

| Dữ liệu | Vị trí | Ghi chú |
|---|---|---|
| Config + license | `%APPDATA%\BatteryClaw\config.json` | luôn ghi được |
| Online learning state | `%APPDATA%\BatteryClaw\state\` | replay buffer, checkpoint, pattern |
| Dashboard stats | `%APPDATA%\BatteryClaw\state\` | thống kê tiết kiệm |
| Model ONNX | đóng gói trong exe / `dist\...\models\` | brain nạp lúc chạy |
| License DB (người bán) | SQLite cạnh `server.py` | keys + logs |

---

## 7. Checklist xác minh môi trường

Trước khi train/build, chạy script kiểm tra có sẵn:
```powershell
cd E:\batteryclaw
powershell -ExecutionPolicy Bypass -File check_env.ps1
```
Nó kiểm Python + thư viện, .NET, GPU, công cụ build. Nếu báo đủ thì sẵn sàng.

Kiểm thủ công nhanh:
```powershell
python --version                              # 3.10.x
python -c "import torch, stable_baselines3, onnxruntime; print('RL OK')"
python -c "import fastapi, uvicorn; print('server OK')"
dotnet --list-sdks                            # thấy 10.x
pip show pyinstaller                          # đã cài
```

---

## 8. Vì sao máy khách không cần cài gì

```
   BatteryClaw.exe  (PyInstaller --onefile)
      ├── Python runtime + numpy/onnxruntime/... ── gói sẵn
      ├── brain + online learning ──────────────── gói sẵn
      ├── model ONNX ────────────────────────────── gói sẵn
      └── engine/  (dotnet publish --self-contained)
             └── .NET runtime ──────────────────── gói sẵn
```

→ Khách chỉ giải nén + chạy `.exe` với quyền Admin. Không cài Python, .NET, hay thư viện.
```
