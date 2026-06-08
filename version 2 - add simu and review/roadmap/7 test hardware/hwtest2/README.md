# HardwareTest2 — Test đường dây "lệnh AI → phần cứng thật"

Test này dùng ĐÚNG file `HardwareControl.cs` mà engine thật sẽ dùng. Nó mô phỏng
2 tình huống AI ra lệnh (tiết kiệm / hiệu năng) và đặt phần cứng thật, rồi đọc lại
xác nhận. Mục đích: chắc chắn đường dây chạy đúng TRƯỚC khi build engine full.

## Chạy (PowerShell ADMIN)
```powershell
cd E:\hwtest2
dotnet run -c Release
```

## Bạn sẽ thấy
- Bước [2]: màn hình tối đi (brightness ~35%), refresh về 60Hz.
- Bước [3]: màn hình sáng lên (brightness ~90%), refresh lên 144Hz (màn có thể nháy 1 cái).
- Bước [4]: trả về như ban đầu.

Nếu "doc lai brightness" khớp giá trị kỳ vọng và bạn THẤY màn hình đổi → đường dây OK,
tôi sẽ chốt để bạn build engine full + train.

COPY toàn bộ kết quả gửi lại.
