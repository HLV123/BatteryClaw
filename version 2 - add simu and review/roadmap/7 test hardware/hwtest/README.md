# HardwareTest — Kiểm tra phần cứng trước khi nối vào engine

Mục đích: xác nhận máy bạn **đọc + đặt** được từng cơ chế phần cứng (độ sáng,
CPU throttle, refresh rate, wifi) TRƯỚC khi nối vào engine và train. Tránh tốn
thời gian build/train rồi mới phát hiện cơ chế không chạy.

## Cách chạy (PowerShell ADMIN)

1. Giải nén thư mục `hwtest` ra (ví dụ `E:\hwtest`).
2. Mở **PowerShell với quyền Administrator** (click phải → Run as administrator).
3. Chạy:

```powershell
cd E:\hwtest
dotnet run -c Release
```

Lần đầu sẽ tải gói `System.Management` (vài giây). Sau đó test chạy, in kết quả
ra màn hình.

## Test làm gì

| Test | Đọc | Đặt thử | An toàn? |
|---|---|---|---|
| 1. Brightness | độ sáng hiện tại | hạ 30% → 80% → trả về cũ | có (tự khôi phục) |
| 2. CPU throttle | — | giới hạn 50% → 100% qua powercfg | có (trả về 100%) |
| 3. Refresh rate | refresh + các mode hỗ trợ | chỉ ĐỌC (không đổi, tránh nháy màn) | có |
| 4. Wifi | tìm adapter wifi | chỉ đọc | có |

Test 1 và 2 có **đổi thật** trên máy bạn trong vài giây rồi tự trả về như cũ —
bạn sẽ thấy màn hình nhấp nháy độ sáng, CPU đỡ tải một chút. Đó là bình thường.

## Sau khi chạy

**Copy TOÀN BỘ những gì in ra màn hình** (từ dòng `BatteryClaw — HARDWARE TEST`
đến hết) và gửi lại. Tôi cần thấy mỗi test KẾT LUẬN là DÙNG ĐƯỢC hay LỖI, để biết
chính xác cơ chế nào nối được vào engine thật.

Đặc biệt chú ý Test 1 (brightness) — nếu nó báo "✓ DOI THAT" thì đúng cái bạn cần;
nếu "✗ KHONG DOI" hoặc "KHONG dung duoc" thì máy bạn cần cách khác (sẽ tính tiếp).

## Lưu ý

- Test này **độc lập hoàn toàn** với BatteryClaw, không đụng gì tới code/model của
  bạn. Chạy xong xóa thư mục là xong.
- Nếu `dotnet run` báo lỗi thiếu SDK, bạn đã có .NET 10 SDK rồi nên chạy được
  (target net8.0 tương thích ngược).
- Nếu Test 2 đổi CPU mà quên trả về, chạy lại lệnh này để chắc chắn 100%:
  `powercfg /setacvalueindex SCHEME_CURRENT 54533251-82be-4824-96c1-47b60b740d00 bc5038f7-23e0-4960-96da-33abaf5935ec 100; powercfg /setactive SCHEME_CURRENT`
