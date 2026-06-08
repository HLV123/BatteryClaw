# BatteryProbe — đọc nguồn pin thật để tìm vì sao Disch=0

## QUAN TRỌNG: RÚT SẠC RA trước khi chạy (để máy ở chế độ chạy pin)

```powershell
cd E:\battprobe
dotnet run -c Release
```

Nó đọc pin 3 lần cách nhau 15s. Gửi lại toàn bộ. Tôi cần biết:
- DischargeRate có > 0 không (nếu có thì WMI đọc được, không cần ước lượng)
- RemainingCapacity có giảm dần qua 3 lần đọc không (nếu có thì ước lượng chạy được)
- Win32_Battery trả gì (nguồn dự phòng)

Từ kết quả này tôi sẽ chốt cách lấy discharge đúng cho máy bạn.
