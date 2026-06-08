# BatteryClaw — Tài liệu vận hành kỹ thuật

Tài liệu dành cho **người bán / quản trị (Admin)**: cấu hình máy cần có, và quy
trình đầy đủ từ train model → tạo key → đóng gói → giao khách. 

Đường dẫn dự án mẫu: `E:\BatteryClaw_end`

---

## PHẦN I — BÁO CÁO CẤU HÌNH & MÔI TRƯỜNG

Trạng thái chung: **ĐỦ ĐIỀU KIỆN CHẠY & ĐÓNG GÓI BẢN THƯƠNG MẠI**

Lệnh kiểm tra môi trường:
```powershell
powershell -ExecutionPolicy Bypass -File check_env.ps1
```

### 1. Hệ điều hành & phần cứng
- **Hệ điều hành**: Microsoft Windows 11 Home Single Language (Build 26200).
- **Trạng thái tối ưu**: hỗ trợ đầy đủ tính năng **EcoQoS** (Phase 5) — giảm điện
  năng tiêu thụ của CPU rất hiệu quả.
- **Card đồ họa (GPU)**:
  - Card tích hợp: Intel(R) UHD Graphics
  - Card rời: NVIDIA GeForce RTX 3050 Laptop GPU (hỗ trợ **DirectML** tăng tốc xử lý
    mô hình AI WinML)

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

### 3. Môi trường phát triển & build
- **.NET SDK**: .NET 10.0.300 — tương thích ngược để biên dịch C# Engine target `net8.0`.
- **C++ Build Tools**: CMake 4.3.3.
- **Đánh giá C#**: sẵn sàng biên dịch Engine C# (self-contained) thành file chạy trực
  tiếp, **không cần cài .NET trên máy khách**.

### Kết luận môi trường
- Máy đáp ứng đầy đủ điều kiện để chạy, huấn luyện mô hình AI, chạy server quản lý
  khóa kích hoạt, và build ra phần mềm BatteryClaw dạng `.exe` thương mại.
- Khi gửi khách: chỉ cần đóng gói thư mục `dist\BatteryClaw_business\` thành ZIP. Máy
  khách chỉ cần chạy `BatteryClaw.exe` với quyền Admin là dùng được — **không cần cài
  Python, .NET hay thư viện nào khác**.

---

## PHẦN II — QUY TRÌNH ĐÓNG GÓI & BÁN KEY

Hướng dẫn người bán (Admin) thực hiện từ cập nhật mô hình AI → build engine → tạo
khóa kích hoạt trên server → nén file gửi khách.

### Bước 1: Cập nhật mô hình AI (Train Model) — TÙY CHỌN

Nếu muốn huấn luyện lại mô hình AI (Brain) với tham số mới:

```powershell
cd "E:\BatteryClaw_end"
python simulator\train.py --steps 300000
```

Sau khi xong, file model ONNX tự xuất ra tại:
```
E:\BatteryClaw_end\simulator\models\batteryclaw_policy.onnx
```

> Lưu ý: nếu không thay đổi thuật toán thì **bỏ qua** bước này. Kịch bản build ở Bước 4 sẽ tự nhận diện nếu đã có sẵn file ONNX.

### Bước 2: Chạy Server quản lý License (để tạo key)

Mở server kích hoạt chạy nền:

```powershell
cd "E:\BatteryClaw_end\server"
$env:BC_ADMIN_TOKEN="admin-test-123"; python server.py
```

Mở trình duyệt vào trang quản trị Admin:
```
http://localhost:8000/admin
```

Tại trang Web Admin:
- Nhập Admin token: `admin-test-123` → bấm Xác nhận.
- Điền thông tin: Số ngày sử dụng, Giá bán, Zalo khách hàng, Ghi chú.
- Bấm tạo khóa để sinh API Key bán cho khách (định dạng: `BC-XXXX-XXXX-XXXX`).

> Lưu ý bảo mật: `admin-test-123` chỉ là token ví dụ để chạy thử local. Khi triển khai thật phải đổi sang token mạnh (server sẽ chặn token yếu khi khởi động).

### Bước 3: Kiểm tra đồng bộ Engine C# — TÙY CHỌN

Nếu có thay đổi code trong phần C# Engine (`engine_dotnet`):

```powershell
cd "E:\BatteryClaw_end\engine_dotnet"
dotnet build -c Release
```
(Biên dịch thử bản Release để kiểm tra lỗi trước khi đóng gói.)

### Bước 4: Đóng gói bản thương mại (build bằng quyền Admin)

Bước quan trọng nhất để tạo sản phẩm hoàn chỉnh gửi khách:

1. Mở PowerShell **(Run as Administrator)**.
2. Di chuyển đến thư mục dự án:
   ```powershell
   cd "E:\BatteryClaw_end"
   ```
3. Chạy kịch bản đóng gói tự động:
   ```powershell
   powershell -ExecutionPolicy Bypass -File build_business.ps1
   ```
4. Đợi hoàn thành. Kết quả nằm tại:
   ```
   E:\BatteryClaw_end\dist\BatteryClaw_business\
   ```

### Bước 5: Bàn giao sản phẩm cho khách hàng

1. Vào thư mục `E:\BatteryClaw_end\dist\`.
2. Nén folder `BatteryClaw_business` thành file ZIP.
3. Gửi file ZIP này **kèm theo API Key** đã tạo ở Bước 2 cho khách hàng.

### Bước 6: Hướng dẫn khách hàng sử dụng

Yêu cầu khách thực hiện trên máy của họ:

1. Giải nén file ZIP nhận được vào một thư mục bất kỳ.
2. Click phải file `BatteryClaw.exe` → **Run as administrator**.
3. Tại giao diện kích hoạt lần đầu:
   - Điền **Server URL** của người bán đưa (ví dụ chạy local thử nghiệm:
     `http://localhost:8000`, hoặc IP VPS của bạn).
   - Nhập **Email** của khách hàng.
   - Nhập **API Key** (ví dụ: `BC-TLMJ-OVRL-YJVQ`) → bấm Kích hoạt.
4. App chuyển vào giao diện chính. Khách chỉ cần bấm **Bắt đầu** để tối ưu pin.

> Chú ý: API Key sau khi kích hoạt sẽ **bị khóa chặt vào máy (Hardware ID)** của khách hàng đó, không thể copy sang máy khác để dùng lậu.

---

## PHẦN III — TÓM TẮT QUY TRÌNH (CHEAT SHEET)

```
   [Người bán]                                           [Khách hàng]
   ───────────                                           ────────────
   1. (tùy chọn) train model                             6. Giải nén ZIP
      python simulator\train.py --steps 300000           7. Run BatteryClaw.exe (Admin)
   2. Chạy server + tạo key                              8. Nhập Server URL + Email + Key
      $env:BC_ADMIN_TOKEN=...; python server.py          9. Kích hoạt → bấm Bắt đầu
      → http://localhost:8000/admin → tạo BC-XXXX-...
   3. (tùy chọn) dotnet build -c Release
   4. build_business.ps1  (Run as Admin)
      → dist\BatteryClaw_business\
   5. Nén ZIP + gửi kèm Key cho khách
```

**Điều kiện máy người bán**: Python 3.10 + đủ thư viện, .NET SDK, (tùy chọn) CMake,
PyInstaller. 
**Điều kiện máy khách**: không cần gì — chỉ chạy file `.exe` với quyền Admin.
