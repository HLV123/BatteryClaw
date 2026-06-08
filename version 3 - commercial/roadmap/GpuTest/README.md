# GpuTest — chẩn đoán GPU switch

## Sự thật
Windows quản GPU per-app (Graphics Settings), KHÔNG cho phần mềm ngoài ép tắt card
rời (dGPU) toàn cục — đó là tính năng bảo vệ (tắt nhầm dGPU có thể mất hiển thị).
Cách hợp lệ duy nhất: đặt "GPU preference" cho TỪNG app trong registry (cái Windows
ghi khi bạn chọn Power saving/High performance cho app trong Settings).

## Chạy (PowerShell Admin)
```powershell
cd E:\GpuTest
dotnet run -c Release
```
Test đọc GPU + preference hiện tại, rồi thử ghi cho notepad (vô hại) và xóa ngay.

## Gửi lại kết quả
Nếu bước [3] báo "đặt GPU preference per-app DUOC ✓" → BatteryClaw có thể gợi ý
Windows dùng iGPU cho app tiết kiệm pin (hợp lệ, per-app). Vẫn KHÔNG ép tắt dGPU
toàn cục được — đó là giới hạn của Windows, không phải lỗi.
