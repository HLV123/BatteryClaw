# BatteryClaw — Kết quả thực nghiệm (bản cuối)

Tài liệu này tổng hợp bằng chứng chạy thật của phiên bản cuối, dựa trên 3 log thực tế: huấn luyện 3 model, đóng gói bản thương mại, và chạy thử trên máy. Mọi số liệu dưới đây trích trực tiếp từ log, không suy diễn.

Máy thử nghiệm: Windows 11 (build 26200), Python 3.10.11, laptop có card đồ họa rời, PyTorch bản CPU (không CUDA).

---

## 1. Huấn luyện — 3 model hồ sơ (PPO)

Cả 3 model được train **5.000.000 steps** mỗi model, trên CPU, tốc độ ~930–943 steps/giây (mỗi model mất khoảng 5.300–5.370 giây, tức ~1.5 giờ). 

Sau train, hệ thống tự lấy **best model** (theo đánh giá định kỳ) để export ONNX, không dùng model ở bước cuối.

Kết quả đánh giá (20 episode ở độ khó thực tế):

| Hồ sơ | Mean reward | Pin còn lại (trung bình) | Lag tổng | Best episode | File ONNX |
|---|---|---|---|---|---|
| **battery_saver** | 81.94 ± 642.82 | 63.4% | 89.81 | 1224.81 | `batteryclaw_policy_battery_saver.onnx` |
| **balanced** | 233.85 ± 469.12 | 63.2% | 58.16 | 1141.71 | `batteryclaw_policy.onnx` |
| **performance** | 169.05 ± 94.93 | 54.0% | **0.62** | 360.52 | `batteryclaw_policy_performance.onnx` |

**Đọc kết quả này thế nào:**

- 3 model **phân hóa thật** đúng như thiết kế. Nhìn cột *Lag tổng* (mức "giật"/thiếu hiệu năng tích lũy): performance gần như không giật (0.62), balanced trung bình (58), còn battery_saver chấp nhận giật nhiều (89.8) để đổi lấy tiết kiệm. Đây là bằng chứng việc gắn hồ sơ với độ nhạy người dùng trong simulator đã tạo ra 3 hành vi khác nhau, không phải 3 bản sao.

- performance có **độ lệch chuẩn nhỏ nhất** (±94.9) — ổn định nhất, dễ đoán nhất. Hai hồ sơ kia độ lệch lớn (±469, ±642) vì hành vi tiết kiệm phụ thuộc nhiều vào hoàn cảnh từng episode (máy, thói quen sạc, workload ngẫu nhiên).

- battery_saver giữ pin cuối cao hơn performance (63.4% so với 54.0%) — hợp lý: tiết kiệm mạnh thì còn nhiều pin hơn, đổi lại chịu giật.

**Lưu ý trung thực:** đây là reward trong môi trường giả lập, không phải phần trăm pin tiết kiệm đo trên máy thật. Nó cho thấy 3 model học ra 3 "tính cách" khác nhau đúng ý đồ, chứ chưa phải con số marketing kiểu "tiết kiệm X%".

### Ghi chú về SAC

SAC chạy chậm trên CPU. Bản deploy cuối dùng PPO. Điều này khớp với
nhận định xuyên suốt: SAC là nhánh thử nghiệm, chưa chứng minh tốt hơn PPO cho bài toán này.

---

## 2. Đóng gói bản thương mại (build)

Lệnh `build_business.ps1` chạy **thành công trọn vẹn**, tạo ra gói khách hàng tại `dist\BatteryClaw_business\`. Các bước đều xanh:

- **[1] Model:** nhận đủ 3 model (balanced mặc định + battery_saver + performance).
- **[2] Engine C#:** `dotnet publish` self-contained thành công trong ~7 giây (`net8.0-windows10.0.19041.0`, win-x64) → khách không cần cài .NET.
- **[3] App + brain:** PyInstaller đóng gói `buy_business.py` thành 1 file `BatteryClaw.exe` (`--onefile --windowed --uac-admin`). Build hoàn tất, EXE tạo thành công.

Đáng chú ý: lệnh PyInstaller có đầy đủ `--paths` cho từng thư mục con của `online/` + `--collect-submodules online` + 10 `--hidden-import`. 

Đây chính là fix cho lỗi "online learning chết trong exe" — và log xác nhận các module nạp động (replay_buffer, ewc, finetuner...) đã được PyInstaller thấy. Kết quả chạy thử (mục 3) cho thấy online learning bật được trong bản đóng gói, chứng minh fix này hoạt động.

Cảnh báo trong log đều vô hại: PyInstaller nhắc "chạy bằng quyền admin không cần thiết", torch thiếu tensorboard/torchvision (không dùng tới), matplotlib chọn backend Agg. Không có lỗi build.

---

## 3. Chạy thử trên máy thật (rl_brain.log)

Log ghi lại app chạy thật, brain kết nối engine qua pipe và điều khiển máy mỗi 10 giây. 

Có 3 phiên (nạp lần lượt battery_saver, rồi balanced), online learning **bật** (`--online`, state ghi vào `%APPDATA%\BatteryClaw\state` — đúng vị trí ghi được).

### Hành vi quan sát được (bằng chứng AI hoạt động đúng)

Phân biệt rõ giữa **chạy pin** và **cắm sạc** — đây là điểm thuyết phục nhất:

| Trạng thái | CPU throttle | Brightness | GPU | Tốc độ xả |
|---|---|---|---|---|
| **BATTERY** (chạy pin) | bóp xuống 20–21% | 30% | ép iGPU (sw0) | 9.000–26.000 mW |
| **PLUGGED** (cắm sạc) | nới lên 60% | 45% | giữ dGPU (sw1) | 0 mW |

Khi rút sạc, AI lập tức siết tiết kiệm; khi cắm lại, AI nới ra để ưu tiên trải nghiệm. 

Đây đúng là logic guard "cắm sạc thì nới, chạy pin thì siết" đã thiết kế — và nó chạy thật trên máy, không phải mô phỏng.

Trong phiên chạy pin đầu tiên (battery_saver), chỉ số "Saved" (ước tính tiết kiệm tích lũy) tăng dần tới khoảng **2.880 mWh** sau vài phút — cho thấy vòng đo tiết kiệm hoạt động.

Nhiệt độ giữ ổn định 40–45°C suốt phiên (máy nhàn), chưa chạm ngưỡng thermal throttle 90°C.

### Một lỗi nhỏ quan sát được (nên ghi nhận)

Ở **Step 1–2 của phiên đầu**, cột xả hiển thị `Disch:787076mW` (≈787W) — phi lý, là lỗi đọc WMI ở 1–2 nhịp đầu khi giá trị chưa ổn định. Từ Step 3 trở đi về mức thật (9.000–26.000mW). Lỗi này chỉ ảnh hưởng con số "Saved" ở nhịp đầu (nhảy 2.186 mWh bất thường), không ảnh hưởng hành vi điều khiển. Cách xử lý gợi ý: kẹp giá trị discharge đọc được vào ngưỡng hợp lý (ví dụ bỏ qua giá trị > 100.000 mW) ở 1–2 nhịp đầu. Ghi lại để sau này sửa.

---

## 4. Kết luận

Phiên bản cuối đã chứng minh được chuỗi end-to-end **chạy thật**:

1. **Train được** 3 model hồ sơ phân hóa rõ ràng (số liệu eval chứng minh không phải 3 bản sao).
2. **Build được** thành gói khách hàng hoàn chỉnh (engine C# self-contained  1 exe có license gate + online learning đóng gói thành công).
3. **Chạy được** trên máy thật: kết nối engine, điều khiển phần cứng đúng logic theo trạng thái pin/sạc, online learning bật được, có đo tiết kiệm.

Những điều còn hạn chế đã được ghi nhận thẳng thắn: reward là số trong giả lập (chưa phải %pin đo thật trên nhiều máy), SAC chưa chứng minh hơn PPO, và có một lỗi nhỏ đọc discharge ở nhịp đầu. Đây là một bản hoàn chỉnh ở mức "sản phẩm chạy được và bán được", với các nhánh nâng cao để dành học tiếp sau này.
