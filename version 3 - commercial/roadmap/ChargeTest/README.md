# ChargeTest — chẩn đoán charge limit (giới hạn sạc 80%)

## Sự thật quan trọng
Windows KHÔNG có API chuẩn để giới hạn sạc pin ở 80%. Mỗi hãng làm riêng (MSI Center,
Lenovo Vantage, ASUS Armoury...). Test này DÒ xem máy bạn (MSI) có expose cơ chế WMI
nào để phần mềm điều khiển không — TRƯỚC khi viết code, tránh viết mò.

## Chạy (PowerShell Admin)
```powershell
cd E:\ChargeTest
dotnet run -c Release
```

## Gửi lại kết quả
Copy toàn bộ. Tôi cần biết có dòng nào báo "✓ TIM THAY" không:
- Nếu CÓ (vd MSI_ACPI / MSI_BatteryHealth) → tôi viết code điều khiển qua đó.
- Nếu KHÔNG → máy bạn không cho giới hạn sạc qua phần mềm ngoài; chỉ MSI Center làm
  được (app chính hãng). Khi đó BatteryClaw sẽ HƯỚNG DẪN người dùng bật trong MSI
  Center thay vì tự làm — trung thực hơn là giả vờ làm được.
