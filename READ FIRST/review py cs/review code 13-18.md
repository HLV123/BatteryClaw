# BatteryClaw — Review code TỪNG DÒNG (Phần 3: FILE 13-18)

Tiếp nối phần 1 (file 1-6) và phần 2 (file 7-12). Phần này: 2 file engine C# cuối
(BatteryReport, TaskSchedulerReader) + bắt đầu nhóm online (test_degradation,
replay_buffer, constraints, ewc).

Định dạng: trích dòng (kèm số dòng) → giải thích ngay dưới.

═══════════════════════════════════════════════════════════════════════════════
# FILE 13/48 — engine_dotnet/Battery/BatteryReport.cs  (137 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  // comment: dùng powercfg /batteryreport /xml; parse health + degradation
15-18 using Diagnostics, Xml.Linq
```
**Dòng 1-18:** Dùng lệnh có sẵn Windows `powercfg /batteryreport /xml` xuất XML chứa
DesignCapacity, FullChargeCapacity, lịch sử dung lượng. Từ đó tính health (FullCharge/
Design), học đường cong xuống cấp, dự đoán pin sau 1 năm, cảnh báo pin yếu. Logic parse
thuần (đã kiểm song song bằng test_degradation.py).

```
20-27 record BatteryHealth: DesignCapacityMwh, FullChargeCapacityMwh, HealthPct, EstimatedHealthIn1YearPct, Warning, Message
```
**Dòng 20-27:** Bản ghi kết quả phân tích pin: dung lượng thiết kế, dung lượng đầy hiện
tại, % sức khỏe, dự đoán sau 1 năm, có cảnh báo không, thông điệp.

```
29-31 class BatteryReport; WarningThresholdPct=50 (dưới 50% → cảnh báo)
```
**Dòng 29-31:** Lớp tĩnh. Ngưỡng cảnh báo: sức khỏe dưới 50% → khuyên thay pin.

```
33-48 Generate(outDir): chạy powercfg /batteryreport /xml /output; chờ ≤10s; trả đường dẫn XML
```
**Dòng 33-48:** Sinh file XML báo cáo pin bằng powercfg. Ẩn cửa sổ, chờ tối đa 10s.

```
50-62 Analyze(xmlPath): load XML; đọc DesignCapacity, FullChargeCapacity; đọc lịch sử; BuildHealth
```
**Dòng 50-62:** Phân tích XML: đọc dung lượng thiết kế + đầy + lịch sử, rồi dựng
BatteryHealth. Lấy namespace XML động (54) vì powercfg đặt namespace riêng.

```
65-81 BuildHealth(design, full, history): healthPct = full/design*100; pctPerYear từ history; in1Year; warn nếu <50%; message
```
**Dòng 65-81:** Tính sức khỏe (tách riêng để test độc lập). healthPct = đầy/thiết kế.
Ước tốc độ xuống cấp/năm rồi trừ ra dự đoán sau 1 năm. Cảnh báo nếu <50%. Soạn message
phù hợp.

```
84-100 EstimateDegradationPctPerYear: sort history theo ngày; lấy đầu/cuối; dropPct/days*365
```
**Dòng 84-100:** Ước tốc độ mất dung lượng (%/năm) tuyến tính: lấy điểm đầu và cuối lịch
sử, tính % giảm trên số ngày, quy ra mỗi năm. Cần ≥2 điểm lịch sử, cách nhau ≥1 ngày.

```
103-114 ReadFirstInt: duyệt XML tìm attribute/element tên cho trước, parse int (strip đơn vị)
116-133 ReadCapacityHistory: duyệt element "HistoryEntry", lấy FullChargeCapacity + StartDate
135-136 StripUnits: chỉ giữ chữ số (bỏ "mWh"...)
```
**Dòng 103-136:** Helper đọc XML. ReadFirstInt tìm giá trị đầu khớp tên. ReadCapacityHistory
gom các mục lịch sử (dung lượng + ngày). StripUnits lọc chỉ lấy số (bỏ đơn vị "mWh").

**TÓM TẮT:** Phân tích sức khỏe pin từ powercfg battery report. Dùng để cảnh báo pin yếu
+ dự đoán xuống cấp (hiển thị trên dashboard). LIÊN KẾT: Program.cs (TryPrintBatteryHealth
gọi Generate+Analyze), test_degradation.py (kiểm thuật toán degradation song song).

═══════════════════════════════════════════════════════════════════════════════
# FILE 14/48 — engine_dotnet/Tasks/TaskSchedulerReader.cs  (86 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-10  // comment: đọc Windows Task Scheduler để biết trước task sắp chạy (Update/scan)
12    using Microsoft.Win32.TaskScheduler
```
**Dòng 1-12:** Đọc Task Scheduler của Windows để agent BIẾT TRƯỚC việc sắp xảy ra (Windows
Update 3h sáng, antivirus scan trưa...) → gợi ý sạc trước/hoãn tới khi cắm điện. Dùng
thư viện TaskScheduler (wrapper COM API). CHỈ ĐỌC, không sửa task hệ thống.

```
16-20 record UpcomingTask: Name, NextRun, LikelyHeavy
```
**Dòng 16-20:** Bản ghi 1 task sắp chạy: tên, thời điểm chạy kế tiếp, có vẻ nặng không.

```
22-29 class TaskSchedulerReader; HeavyHints = {update, defender, scan, backup, telemetry, defrag...}
```
**Dòng 22-29:** Lớp tĩnh. Danh sách từ khóa nhận diện task nặng pin/CPU (update/scan/
backup/defrag...).

```
32-50 GetUpcoming(withinHours=12): tạo TaskService; CollectFromFolder(RootFolder); lỗi → rỗng; sort theo NextRun
```
**Dòng 32-50:** Liệt kê task chạy trong N giờ tới. Mở TaskService, duyệt từ thư mục gốc.
Lỗi (quyền/COM) → trả rỗng, engine vẫn chạy bình thường. Sắp xếp theo thời gian chạy.

```
52-72 CollectFromFolder (đệ quy): bỏ task Disabled; nếu NextRunTime trong [now, horizon] → thêm (kèm heavy); duyệt SubFolders
```
**Dòng 52-72:** Duyệt đệ quy mọi thư mục task. Bỏ task đã tắt. Task có giờ chạy kế tiếp
nằm trong khoảng quan tâm → thêm vào kết quả, đánh dấu nặng nếu tên/đường dẫn khớp hint.
try/catch vì một số task ném lỗi khi đọc NextRunTime. Đệ quy vào thư mục con.

```
74-78 IsHeavy(s): chuyển thường, kiểm chứa hint nào không
80-85 NextHeavyTask(withinHours=6): lấy task nặng đầu tiên sắp chạy; trả (có không, task)
```
**Dòng 74-85:** IsHeavy kiểm tên có chứa từ khóa nặng. NextHeavyTask trả task nặng gần
nhất trong 6h (Program.cs dùng để cảnh báo lúc khởi động).

**TÓM TẮT:** [2.4] Đọc lịch task Windows để cảnh báo task nặng sắp chạy → gợi ý cắm sạc.
Chỉ đọc, an toàn. LIÊN KẾT: Program.cs (Main gọi NextHeavyTask(6) in cảnh báo). Cần
package TaskScheduler 2.11.0 trong csproj.

═══════════════════════════════════════════════════════════════════════════════
# FILE 15/48 — engine_dotnet/Battery/test_degradation.py  (72 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-8   """ docstring """ + import datetime
```
**Dòng 1-8:** Kiểm chứng thuật toán battery health của BatteryReport.cs bằng Python —
port y hệt logic thuần để chứng minh đúng (vì C# không test được trong môi trường Linux,
port sang Python test được).

```
11-23 estimate_degradation_pct_per_year(design, history): port của hàm C# cùng tên
```
**Dòng 11-23:** Bản port Python của EstimateDegradationPctPerYear (BatteryReport.cs dòng
84-100). Logic giống hệt: sort history, lấy đầu/cuối, tính % giảm/ngày × 365. Cần ≥2
điểm, cách ≥1 ngày.

```
26-38 build_health(design, full, history): port của BuildHealth; trả dict health/in_1year/per_year/warning
```
**Dòng 26-38:** Port của BuildHealth (C# dòng 65-81). health = full/design×100, trừ
degradation ra dự đoán 1 năm, cảnh báo nếu <50%.

```
41-56 self-test với máy MSI thật: design 52007, full 33026 → health ~63.5%; history giả lập
```
**Dòng 41-56:** Test với số liệu máy MSI của người dùng: dung lượng thiết kế 52007 mWh,
hiện tại 33026 mWh → sức khỏe ~63.5% (khớp pin chai ~63% nhắc nhiều lần). Lịch sử giả
lập (1 năm trước 40000 → nay 33026).

```
58-62 assert: health 63-64%; degradation 13-14%/năm; dự đoán < hiện tại; chưa cảnh báo
65-67 test pin yếu (full 24000) → phải cảnh báo
70 test thiếu lịch sử → degradation 0
72 print PASS
```
**Dòng 58-72:** Các khẳng định kiểm tính đúng: health đúng ~63.5%, tốc độ giảm ~13.4%/
năm (40000→33026 trong 365 ngày), dự đoán thấp hơn hiện tại, 63.5% chưa cảnh báo. Test
biên: pin 24000 → cảnh báo; thiếu lịch sử → degradation 0. In PASS nếu mọi assert qua.

**TÓM TẮT:** Test Python chứng minh thuật toán degradation của BatteryReport.cs đúng (vì
C# không test được trong container Linux). Dùng đúng số máy MSI thật của người dùng.
LIÊN KẾT: BatteryReport.cs (cùng thuật toán, port sang đây để verify).

═══════════════════════════════════════════════════════════════════════════════
# FILE 16/48 — online/buffer/replay_buffer.py  (92 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  """ docstring """ + import os, numpy
15-16 STATE_DIM=15, ACTION_DIM=7
```
**Dòng 1-16:** Bộ nhớ trải nghiệm của RIÊNG máy người dùng (online learning Phase 3). Mỗi
transition (s, a, r, s'). Rolling buffer giữ N gần nhất, lưu .npz để không mất khi tắt
máy, lấy batch ngẫu nhiên cho fine-tune. Cố ý ngắn gọn.

```
19-30 __init__(capacity=10000, path): mảng s/a/r/s2 (numpy zeros); idx (vòng tròn); size; nếu path tồn tại → load
```
**Dòng 19-30:** Khởi tạo 4 mảng numpy cố định kích thước (s/action/reward/next_state).
idx = vị trí ghi tiếp theo (vòng tròn), size = số phần tử hiện có. Nếu có file cũ → nạp.

```
32-39 add(state, action, reward, next_state): ghi vào idx; idx = (idx+1)%capacity (ghi đè cũ nhất); size tăng tối đa capacity
```
**Dòng 32-39:** Thêm transition. Ghi vào vị trí idx rồi tăng vòng tròn — khi đầy thì ghi
đè cái cũ nhất (rolling). size không vượt capacity.

```
41-46 sample(batch_size, rng): lấy n=min(batch,size) chỉ số ngẫu nhiên; trả s/a/r/s2 tương ứng
```
**Dòng 41-46:** Lấy batch ngẫu nhiên để train. Hỗ trợ cả rng kiểu mới (integers) lẫn cũ
(randint). Trả 4 mảng con theo chỉ số bốc được.

```
48-49 __len__: trả size
51-58 save(path): tạo thư mục; np.savez_compressed lưu s/a/r/s2/idx/size/capacity
60-71 load(path): np.load; nạp tối đa min(cap cũ, cap mới); khôi phục size/idx
```
**Dòng 48-71:** len trả số phần tử. save nén ra .npz (kèm metadata idx/size/capacity).
load nạp lại, xử lý cả khi capacity đổi (nạp tối đa có thể). Đây là cơ chế giữ trải
nghiệm qua các lần tắt/mở máy.

```
74-92 self-test: cap=5 đẩy 8 phần tử → giữ 5 mới nhất {3,4,5,6,7}; sample shape; save/load
```
**Dòng 74-92:** Test: buffer cap 5, đẩy 8 → giữ đúng 5 mới nhất (cái cũ 0,1,2 bị đẩy ra),
kiểm shape sample, kiểm save/load. In PASS.

**TÓM TẮT:** Bộ nhớ trải nghiệm cá nhân hóa của máy (rolling 10k transition, lưu đĩa). Là
nền cho online learning + cho SAC train. LIÊN KẾT: brain_online_adapter (observe → add),
finetuner (sample để train), train_sac (dùng buffer cho SAC).

═══════════════════════════════════════════════════════════════════════════════
# FILE 17/48 — online/safety/constraints.py  (79 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  """ docstring """
```
**Dòng 1-13:** Ràng buộc CỨNG: dù model học gì, action cuối phải qua bộ lọc này. Lớp bảo
vệ độc lập policy. 3 quy tắc: CPU không quá 95°C (nóng → ép throttle), không tắt dGPU khi
game, không tự hạ brightness <20%. Pin <10% tiết kiệm mạnh là mong muốn, không chặn.

```
15-17 MAX_CPU_TEMP_C=95, MIN_BRIGHTNESS=0.20, HOT_THROTTLE_MAX=0.60
```
**Dòng 15-17:** 3 ngưỡng an toàn: nhiệt trần 95°C, sáng tối thiểu 20%, throttle khi nóng
giới hạn 60%.

```
20-42 clamp_action(action, state): copy action; reasons=[]
26-30 (1) nhiệt ≥95°C → ép cpu_throttle_max ≤0.60
33-35 (2) is_game + gpu_switch==0 → ép gpu_switch=1 (không tắt dGPU)
38-40 (3) brightness_act < 0.20 → nâng lên 0.20
42 return (action an toàn, lý do)
```
**Dòng 20-42:** Hàm ép action an toàn. Copy action (không sửa gốc). Quy tắc 1: CPU chạm
trần nhiệt → bóp throttle. Quy tắc 2: đang game mà định tắt dGPU → giữ dGPU. Quy tắc 3:
brightness quá thấp → nâng. Trả kèm danh sách lý do đã chỉnh (để log).

```
45-53 is_state_anomalous(state): nhiệt ≥98°C hoặc discharge >120000mW → anomaly (cân nhắc rollback)
```
**Dòng 45-53:** Phát hiện trạng thái bất thường (để cân nhắc rollback model online): CPU
quá nóng (vượt trần +3) hoặc xả bất thường cao (>120W). Trả (có bất thường, lý do).

```
56-79 self-test: nóng→ép throttle; game→giữ dGPU; brightness thấp→nâng; bình thường→không đổi; anomaly
```
**Dòng 56-79:** Test 4 trường hợp clamp + 1 anomaly. In PASS.

**TÓM TẮT:** Lớp an toàn cứng cho online learning — chặn action nguy hiểm bất kể model
học gì. LIÊN KẾT: brain_online_adapter (gọi clamp_action trước khi áp), finetuner (dùng
is_state_anomalous để rollback). Lưu ý: đây là tầng safety cho Phase 3; rl_brain còn có
guard riêng (game/plugged/pin thấp) ở action_to_command.

═══════════════════════════════════════════════════════════════════════════════
# FILE 18/48 — online/finetune/ewc.py  (92 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-15  """ docstring """ + import torch
```
**Dòng 1-15:** Elastic Weight Consolidation — chống "catastrophic forgetting": khi
fine-tune model trên dữ liệu máy người dùng, không muốn nó QUÊN kiến thức nền (học từ
simulator). Ý tưởng: phạt việc đổi những trọng số QUAN TRỌNG với tác vụ cũ. Công thức:
penalty = Σ F_i × (θ_i − θ*_i)². θ* = trọng số gốc, F = độ quan trọng (Fisher).

```
20-24 class EWC; PARAM_WARN_THRESHOLD=500000 (cảnh báo nếu model lớn, Fisher tốn RAM)
```
**Dòng 20-24:** [DESIGN-05] Fisher matrix to bằng số tham số model. MLP [128,128] ~25K
(~100KB, ổn). Model lớn (LSTM) → cảnh báo vì Fisher tốn RAM trên laptop đang chạy game.

```
26-41 __init__(model, importance=1000): lưu star (trọng số gốc θ*); fisher (khởi 0); cảnh báo nếu nhiều tham số
```
**Dòng 26-41:** Khởi tạo. importance = λ (độ mạnh ràng buộc). star = ảnh chụp trọng số
gốc (clone, detach để không dính graph). fisher khởi 0. Đếm tham số, cảnh báo nếu vượt
ngưỡng (kèm ước lượng RAM).

```
43-54 estimate_fisher(states, actions, loss_fn): eval; backward loss; F_i ≈ grad²
```
**Dòng 43-54:** Ước độ quan trọng F_i từ batch dữ liệu nền. Chạy loss, backward lấy
gradient, F_i ≈ bình phương gradient (xấp xỉ đường chéo ma trận Fisher). Trọng số nào
gradient lớn = quan trọng với tác vụ cũ → phạt nặng nếu đổi.

```
56-62 penalty(): Σ fisher × (p − star)²; nhân importance; trả scalar tensor
```
**Dòng 56-62:** Tính EWC penalty để cộng vào loss fine-tune. Trọng số càng đổi xa gốc +
càng quan trọng → phạt càng lớn. Nhân λ (importance).

```
65-92 self-test: model nhỏ; estimate_fisher; penalty=0 khi chưa đổi; đổi trọng số → penalty>0
```
**Dòng 65-92:** Test: penalty=0 khi trọng số chưa đổi (đang ở θ*), đổi trọng số → penalty
tăng. In PASS.

**TÓM TẮT:** Cơ chế chống quên kiến thức nền khi học online trên máy người dùng. LIÊN KẾT:
finetuner.py (dùng EWC.penalty() trong loss khi fine-tune). Lưu ý: đây là cơ sở hạ tầng
Phase 3; chỉ hoạt động khi bật --online.

───────────────────────────────────────────────────────────────────────────────
HẾT PHẦN 3 (FILE 13-18): BatteryReport, TaskSchedulerReader, test_degradation,
replay_buffer, constraints, ewc. Còn lại nhóm online: checkpoint, finetuner,
pattern_tracker, feedback_store, modes, online_loop, brain_online_adapter,
hrl_integration (8 file) → phần 4+.
───────────────────────────────────────────────────────────────────────────────
