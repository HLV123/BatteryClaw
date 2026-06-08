# BatteryClaw — Tài liệu vận hành kỹ thuật

Tài liệu dành cho **người bán / quản trị (Admin)**: cấu hình máy cần có, và quy
trình đầy đủ từ train model → tạo key → đóng gói → giao khách.

Đường dẫn dự án: `E:\batteryclaw`

---

## PHẦN I — BÁO CÁO CẤU HÌNH & MÔI TRƯỜNG

Trạng thái chung: **ĐỦ ĐIỀU KIỆN CHẠY & ĐÓNG GÓI BẢN THƯƠNG MẠI**

Lệnh kiểm tra môi trường:
```powershell
powershell -ExecutionPolicy Bypass -File check_env.ps1
```

### 1. Hệ điều hành & phần cứng
- **Hệ điều hành**: Microsoft Windows 11 Home Single Language (Build 26200).
- **Trạng thái tối ưu**: hỗ trợ đầy đủ tính năng **EcoQoS** (Phase 5) — ghìm tiến
  trình nền tiết kiệm điện.
- **Card đồ họa (GPU)**:
  - Card tích hợp: Intel(R) UHD Graphics
  - Card rời: NVIDIA GeForce RTX 3050 Laptop GPU (hỗ trợ **DirectML** tăng tốc WinML)
- **Đã xác nhận trên máy thật**: đọc/đặt được độ sáng (WMI), CPU throttle (powercfg),
  refresh rate 60/144Hz (user32), wifi power policy, và đọc dòng xả pin thật
  (WMI DischargeRate ~6-12W).

### 2. Môi trường Python (ngôn ngữ lõi)
- **Phiên bản**: Python 3.10.11
- **Thư viện** (đầy đủ 100%, đã kiểm tra và kích hoạt):

| Thư viện | Vai trò |
|---|---|
| numpy | Xử lý ma trận dữ liệu |
| torch | Huấn luyện & chạy mạng neuron AI |
| gymnasium | Môi trường giả lập Reinforcement Learning |
| stable_baselines3 | Thuật toán học tăng cường PPO |
| onnx | Export định dạng mô hình AI dùng chung |
| onnxruntime | Chạy suy luận mô hình AI tốc độ cao |
| pandas & pyarrow | Xử lý và lưu trữ dữ liệu hiệu năng pin |
| fastapi & uvicorn | Chạy API Server quản lý License/Kích hoạt |
| jinja2 | Template trang quản trị Admin Server |
| requests | Gửi yêu cầu mạng kích hoạt Key |
| winotify | Gửi thông báo Toast trên Windows 11 |
| wmi & win32api | Giao tiếp phần cứng Windows nâng cao |
| pyinstaller | Đóng gói app thành .exe (cài bằng `pip install pyinstaller`) |

### 3. Môi trường phát triển & build
- **.NET SDK**: máy có .NET 10. Engine target `net8.0` → chạy bằng cách đặt biến
  `DOTNET_ROLL_FORWARD=Major` (xem lưu ý ở Bước 3 & 4).
- **C++ Build Tools**: CMake (chỉ cần nếu động đến engine C++ cũ — bản deploy KHÔNG dùng).
- **Đánh giá C#**: biên dịch Engine C# (self-contained) thành file chạy trực tiếp,
  **không cần cài .NET trên máy khách**.

### Kết luận môi trường
- Máy đáp ứng đầy đủ điều kiện để chạy, huấn luyện AI, chạy server quản lý khóa, và
  build phần mềm BatteryClaw dạng `.exe` thương mại.
- Khi gửi khách: đóng gói thư mục `dist\BatteryClaw_business\` thành ZIP. Máy khách
  chỉ chạy `BatteryClaw.exe` với quyền Admin — **không cần cài Python, .NET hay gì khác**.

---

## PHẦN II — QUY TRÌNH ĐÓNG GÓI & BÁN KEY

### Bước 1: Train mô hình AI

Bản hiện tại dùng **curriculum 4 phase**, khuyến nghị train dài để model mạnh:

```powershell
cd E:\batteryclaw
python simulator\train.py --steps 5000000
```

- Train chạy 4 phase (dễ → khó), tự xuất ONNX từ **best model**.
- ~5 triệu steps trên RTX 3050 khoảng 20 phút. Muốn nhanh để thử: `--steps 1000000`.
- File model tự xuất tại:
```
E:\batteryclaw\simulator\models\batteryclaw_policy.onnx
```

> Nếu đã có model ưng ý thì **bỏ qua** bước này; build ở Bước 4 tự nhận file ONNX sẵn có.

### Bước 2: Chạy Server quản lý License (để tạo key)

Mở **một cửa sổ PowerShell riêng** (để server chạy nền liên tục):

```powershell
cd E:\batteryclaw\server
$env:BC_ADMIN_TOKEN="admin-test-123"; python server.py
```

Mở trình duyệt vào trang quản trị Admin:
```
http://localhost:8000/admin
```

Tại trang Web Admin:
- Nhập Admin token: `admin-test-123` → bấm Xác nhận.
- Điền: Số ngày sử dụng, Giá bán, Zalo khách hàng, Ghi chú.
- Bấm tạo khóa → sinh API Key (định dạng `BC-XXXX-XXXX-XXXX`).

> Bảo mật: `admin-test-123` chỉ để chạy thử local. Khi bán thật phải đổi token mạnh
> và đặt server trên VPS có IP/domain công khai (server chặn token yếu khi khởi động).

### Bước 3: Kiểm tra build Engine C# — TÙY CHỌN

Nếu có thay đổi code trong `engine_dotnet`, build thử để bắt lỗi compile:

```powershell
cd E:\batteryclaw\engine_dotnet
$env:DOTNET_ROLL_FORWARD="Major"
dotnet build -c Release
```

> `DOTNET_ROLL_FORWARD=Major` cho phép engine target .NET 8 chạy trên .NET 10 đang cài.
> Build báo `Build succeeded` là được; vài warning (CS8625/CS8602...) vô hại.

### Bước 4: Đóng gói bản thương mại (build bằng quyền Admin)

1. Mở PowerShell **(Run as Administrator)**.
2. (Lần đầu) cài PyInstaller: `pip install pyinstaller`
3. Di chuyển đến thư mục dự án và build:
   ```powershell
   cd E:\batteryclaw
   powershell -ExecutionPolicy Bypass -File build_business.ps1
   ```
4. Đợi hoàn thành. Kết quả tại:
   ```
   E:\batteryclaw\dist\BatteryClaw_business\
   ```

> Script tự build engine self-contained + gói app/brain/online thành một `.exe`.
> Bản build này đã gom đúng các module online (online learning chạy được trong exe).

### Bước 5: Bàn giao sản phẩm cho khách hàng

1. Vào `E:\batteryclaw\dist\`.
2. Nén folder `BatteryClaw_business` thành ZIP.
3. Gửi ZIP **kèm API Key** đã tạo ở Bước 2 cho khách.

### Bước 6: Hướng dẫn khách hàng sử dụng

1. Giải nén ZIP vào thư mục bất kỳ.
2. Click phải `BatteryClaw.exe` → **Run as administrator**.
3. Màn hình kích hoạt lần đầu:
   - **Server URL** của người bán (thử local: `http://localhost:8000`; bán thật: IP/domain VPS).
   - **Email** của khách.
   - **API Key** (ví dụ `BC-TLMJ-OVRL-YJVQ`) → bấm Kích hoạt.
4. Vào giao diện chính → bấm **Bắt đầu** để tối ưu pin (online learning tự chạy ngầm).

> API Key sau khi kích hoạt **bị khóa vào máy (Hardware ID)**, không copy sang máy khác được.
> Lưu ý: phải **Run as administrator** thì engine mới đặt được độ sáng/CPU/refresh thật.

---

## PHẦN III — TÓM TẮT QUY TRÌNH (CHEAT SHEET)

```
   [Người bán]                                           [Khách hàng]
   ───────────                                           ────────────
   1. (tùy chọn) train model                             6. Giải nén ZIP
      python simulator\train.py --steps 5000000          7. Run BatteryClaw.exe (Admin)
   2. Chạy server + tạo key (cửa sổ riêng)               8. Nhập Server URL + Email + Key
      $env:BC_ADMIN_TOKEN="..."; python server.py        9. Kích hoạt → bấm Bắt đầu
      → http://localhost:8000/admin → tạo BC-XXXX-...
   3. (tùy chọn) dotnet build -c Release
      ($env:DOTNET_ROLL_FORWARD="Major" trước)
   4. build_business.ps1  (Run as Admin)
      → dist\BatteryClaw_business\
   5. Nén ZIP + gửi kèm Key cho khách
```

**Điều kiện máy người bán**: Python 3.10 + đủ thư viện + pyinstaller, .NET 10 SDK.
**Điều kiện máy khách**: không cần gì — chỉ chạy `.exe` với quyền Admin.

---

## PHẦN IV — GHI CHÚ VẬN HÀNH (lưu ý quan trọng)

- **Luôn Run as Administrator** ở cả engine lẫn app: cần quyền này để đặt độ sáng,
  CPU throttle, refresh, ETW, EcoQoS, và để pipe engine↔brain không bị "Access denied".
- **DOTNET_ROLL_FORWARD=Major**: máy có .NET 10, engine target .NET 8 → cần biến này
  để chạy. `build_business.ps1` đã xử lý; chỉ cần đặt thủ công khi chạy `dotnet build/run` tay.
- **State ghi ở `%APPDATA%\BatteryClaw\`** (config, license, online learning, dashboard),
  KHÔNG ghi cạnh exe → cài vào Program Files vẫn ghi được.
- **Discharge**: máy đọc dòng xả thật qua WMI (~6-12W khi chạy pin). Nếu một máy khác
  trả 0, engine tự ước lượng từ tốc độ tụt dung lượng pin.
- **Phần cứng không điều khiển được**: chuyển GPU rời (Windows quản per-app) và giới
  hạn sạc theo % (phụ thuộc hãng máy) — AI vẫn tính nhưng engine bỏ qua an toàn. Các
  cơ chế tiết kiệm chính (độ sáng, CPU, refresh, wifi, ghìm app nền) đều hoạt động thật.
- **Nếu re-extract zip dự án**: thư mục `bin/obj` của engine bị xóa → cần
  `dotnet build -c Release` lại trước khi đóng gói.
