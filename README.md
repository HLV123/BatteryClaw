# BatteryClaw

> Phần mềm AI tối ưu thời lượng pin laptop Windows, dùng Reinforcement Learning.
> Engine C#/.NET đọc & điều khiển phần cứng, Brain Python chạy mô hình ONNX.

Một dự án cá nhân, làm trước khi học môn Học tăng cường ở trường. README này được viết
lại cho đúng với **khả năng thực tế hiện tại của code** — phần nào đã chạy thật, phần nào
mới là hạ tầng/thử nghiệm đều ghi rõ, không tô hồng.

---

## 1. BatteryClaw làm gì

Một AI chạy nền trên laptop Windows, quan sát trạng thái máy và tinh chỉnh các thiết lập
để pin dùng được lâu hơn mà ít làm phiền người dùng nhất. Khác với chế độ tiết kiệm pin
mặc định (dùng quy tắc cứng "pin < 20% thì giảm sáng"), BatteryClaw dùng một policy học
được để cân bằng giữa tiết kiệm điện, hiệu năng và sự thoải mái.

Mỗi chu kỳ (10 giây), brain nhận **15 chỉ số** từ engine (pin, CPU, nhiệt độ, ứng dụng
foreground, tốc độ xả, refresh rate...) và xuất **7 nhóm hành động** (throttle CPU, độ
sáng, hoãn tác vụ nền, chuyển GPU, đổi refresh, tiết kiệm wifi, gợi ý giới hạn sạc).
Engine cập nhật trạng thái mỗi giây; AI ra quyết định mỗi 10 giây.

Người dùng chỉ cần mở app, chọn hồ sơ (Tiết kiệm / Cân bằng / Hiệu năng) và bấm **Bắt đầu**.

---

## 2. Trạng thái dự án (trung thực)

**Đã chạy thật end-to-end** trên máy thật (Windows 11, laptop có card rời):

- Engine C#/.NET thu thập 15 chỉ số thật và thực thi lệnh phần cứng thật (độ sáng qua
  WMI, CPU qua powercfg, refresh rate qua user32, GPU preference per-app qua registry,
  ghìm tiến trình nền qua EcoQoS trên Windows 11).
- Brain Python nạp model ONNX, giao tiếp engine qua Named Pipe, ra quyết định mỗi 10s.
- 3 model hồ sơ (battery_saver / balanced / performance) được **huấn luyện thật** trên
  simulator (mỗi model ~5 triệu steps) và chạy được trên máy.
- Giao diện người dùng hoàn chỉnh + dashboard web localhost hiển thị thống kê.
- Quy trình thương mại hóa: license server (FastAPI), khóa kích hoạt theo từng máy,
  trang admin tạo/quản lý key, bộ cài cho khách.

**Đã viết nhưng chưa kiểm chứng / chưa vào luồng deploy chính** (xem mục 5): online
learning trên máy thật, world model, SAC, Hierarchical RL, MPC planning, LSTM policy.
Đây là hạ tầng/thử nghiệm — code có và chạy self-test được, nhưng chưa được train đủ
hoặc chưa chứng minh tốt hơn baseline.

**Không làm được bằng phần mềm** (giới hạn phần cứng): giới hạn sạc 80% trên máy MSI thử
nghiệm không can thiệp được qua phần mềm (không có WMI class tương ứng) — app chỉ **phát
hiện và hướng dẫn** người dùng bật trong tiện ích của hãng (MSI Center), không tự dừng sạc.

---

## 3. Cách bán & kích hoạt (đã vận hành được)

Cơ chế license qua API key:

1. **Người bán** chạy license server (FastAPI) trên VPS hoặc local, vào trang admin bằng
   token bảo mật, nhập số ngày dùng + giá + Zalo khách → hệ thống sinh key dạng
   `BC-XXXX-XXXX-XXXX`.
2. **Khách hàng** tải ZIP, giải nén, chạy `BatteryClaw.exe` với quyền Admin. Màn kích
   hoạt yêu cầu nhập Server URL, Email và API Key.
3. App gửi POST tới `/api/activate` kèm key, email và **hardware ID** (tính từ UUID
   mainboard + serial ổ đĩa). Server kiểm tra key hợp lệ & chưa kích hoạt → khóa key vào
   hardware ID đó và trả về số ngày dùng. Nếu key đã dùng trên máy khác → từ chối.
4. Mỗi lần mở app, BatteryClaw gọi `/api/verify` kiểm tra hạn. Mất mạng vẫn chạy nhờ
   **offline grace period** cho đến khi hết hạn.

Cơ chế khóa-1-key-1-máy giúp hạn chế dùng lậu (không tuyệt đối, nhưng đủ tốt cho quy mô
nhỏ). Chi phí biên gần như bằng 0, phù hợp khởi nghiệp vốn nhỏ.

Định giá tham khảo (logic phân quyền tính năng có trong code): Free (CPU cơ bản) /
Basic 29k (+ GPU, dashboard, sức khỏe pin) / Pro 59k (+ tự học, hồ sơ tùy chỉnh) /
Lifetime 499k. Server hiện cấp key theo thời hạn (ngày) + giá tùy chọn, nên bán linh
hoạt được cả theo gói lẫn theo thuê bao.

---

## 4. Bảo vệ sức khỏe pin

Pin lithium-ion chai nhanh vì ba nguyên nhân chính: sạc đầy 100% rồi cắm tiếp, xả kiệt
0%, và nhiệt cao khi vừa sạc vừa dùng nặng. BatteryClaw xử lý ở các mức độ khác nhau:

- **Sạc đầy:** AI được huấn luyện để thưởng việc giữ pin quanh 80% khi cắm sạc và phạt
  việc giữ pin đầy 100% liên tục. Trên thực tế, việc *dừng sạc* ở 80% phụ thuộc phần
  cứng — máy nào không cho phần mềm can thiệp thì app hướng dẫn bật qua tiện ích hãng.
- **Xả kiệt:** trong simulator, reward phạt nặng nếu để pin chết; trên máy thật, khi pin
  yếu app ép tiết kiệm tối đa để ưu tiên giữ máy sống.
- **Nhiệt:** AI quan sát nhiệt độ và trạng thái cắm sạc, điều tiết CPU/GPU để tránh
  thermal throttle (>90°C).
- **Theo dõi chai pin:** engine C# đọc battery report thật (FullChargeCapacity vs
  DesignCapacity) qua `powercfg`, dự đoán độ chai và hiển thị trên dashboard. (Máy thử
  nghiệm: pin ~63.5% sức khỏe.)

---

## 5. Bên trong: 6 phase phát triển

Code được tổ chức qua 6 phase. Cần nói rõ **cái gì đang chạy** và **cái gì là thử nghiệm**:

**Đang chạy ở bản deploy:**
- **PPO** (Proximal Policy Optimization) train trên simulator, curriculum 4 độ khó (dễ →
  khó dần), xuất ONNX (15 observation → 7 action). Đây là model thực tế đang dùng.
- **Engine C#** thay hoàn toàn engine C++ cũ: WMI (đọc trạng thái), powercfg/user32/
  registry (điều khiển), EcoQoS (ghìm tiến trình nền, chỉ Windows 11), Task Scheduler
  Reader (cảnh báo tác vụ nặng sắp chạy → gợi ý cắm sạc).
- Suy luận ONNX nhẹ, chạy trên CPU, không cần CUDA hay GPU mạnh.

**Đã viết, là hạ tầng/thử nghiệm, chưa vào luồng chính:**
- **Online learning** (`--online`): fine-tune policy ngay trên máy khách. Cơ chế đã đầy
  đủ — replay buffer vòng tròn 10.000 mẫu, fine-tune khi máy rảnh >5 phút với learning
  rate nhỏ (1e-5), **EWC** chống quên kiến thức cũ, tự rollback nếu bản mới tệ hơn,
  `PatternTracker` học thói quen theo 24 khung giờ, chế độ tạm "Họp"/"Pin yếu" tự hết
  hạn. Cần dữ liệu sử dụng thật để chứng minh hiệu quả.
- **World model + MPC planning:** học động lực học máy từ dữ liệu thật rồi mô phỏng vài
  bước trước khi quyết định. Cần thu đủ dữ liệu mới train tốt.
- **SAC** (off-policy, tối ưu entropy) và **Hierarchical RL** (Manager chọn chiến lược
  mỗi 5 phút, Worker thực thi mỗi 10 giây): đã có code + self-test, nhưng **chưa chứng
  minh tốt hơn PPO** cho bài toán này; SAC chạy chậm trên CPU.
- **LSTM policy** (bộ nhớ ngắn hạn nhận diện mẫu thời gian): hạ tầng deploy đã thông qua
  ONNX dạng chuỗi, nhưng chưa được train riêng nên chưa hữu ích.
- **WinML + DirectML:** engine có thể chạy ONNX trên GPU (chế độ standalone), nhưng bản
  deploy chính vẫn dùng brain Python để dễ bật online learning.
- **ETW** đọc điện năng theo mili giây: có code, nhưng trên máy thử nghiệm ETW trả giá
  trị rất thấp (~1mW) nên thực tế discharge được lấy từ WMI; ETW giữ làm dự phòng.

Tất cả phần thử nghiệm nằm trong repo để học tiếp sau này, không phải để khoe là "đã xong".

---

## 6. Simulator (môi trường huấn luyện)

Không train trên pin thật (sẽ hỏng pin và quá chậm). Thay vào đó là một môi trường giả
lập mô phỏng vật lý pin/nhiệt/công suất + thói quen người dùng, để AI thử rất nhiều lần.
Mỗi episode bốc ngẫu nhiên: loại máy (ultrabook mỏng 60Hz không card rời → gaming có card
rời, panel tối đa 144Hz → máy cũ pin chai), độ chai pin, nhiệt phòng, thói quen sạc, và
12 loại workload (idle, web nhẹ/nặng, office, họp video, xem phim, nghe nhạc, code,
compile, render, game nhẹ/nặng).

Một số chi tiết mô phỏng cho sát thực tế:

- Sạc/rút theo thói quen có quy luật; cắm sạc làm pin tăng và máy nóng thêm.
- Spike workload (Windows Update/antivirus) vọt CPU bất chợt mà AI không tắt được → học
  cách chịu đựng và bù trừ.
- Dưới 20% pin xả nhanh hơn (tới ~1.8 lần, càng chai càng dốc) → AI học chắt chiu về cuối.
- Lệnh AI không có hiệu lực tức thì (mô phỏng độ trễ của HĐH) → AI học tính kiên nhẫn.
- Mỗi hồ sơ gắn với một "người ảo" có độ nhạy giật / nhạy màn tối khác nhau → 3 model
  phân hóa rõ (kết quả eval cho thấy hồ sơ performance mượt hơn hẳn battery_saver).
- Curriculum từ dễ đến khó: phase đầu máy dễ, không nhiễu; phase cuối nhiễu kịch khung
  (lệnh trễ 2 bước, spike gấp đôi, pin chai nặng).

**Kỳ vọng** (chưa đo trên đủ máy thật): policy có thể kéo dài thời lượng pin thêm khoảng
20–35% so với mặc định Windows, tùy máy và thói quen. Đây là mục tiêu, không phải số đo
đã kiểm chứng rộng rãi.

---

## 7. Lời kết — dừng dự án

Trong buổi chọn ý tưởng của nhóm, BatteryClaw đã **vote thua một ý tưởng khác**, nên dự
án này sẽ không được triển khai tiếp. Mình hoàn toàn vui vẻ với kết quả đó và sẽ hợp
tác hết mình với ý tưởng được chọn.

Dự án này mình xin phép **dừng lại ở đây**. Mình đã ghi lại đầy đủ tài liệu review từng
dòng code (cả Python lẫn C#) để dành cho sau này: vài tháng nữa, khi học môn Học tăng
cường (RL) ở trường, mình sẽ đọc lại project mà không bị hụt hẫng hay quên mất mình đã
nghĩ gì.

Có lẽ bây giờ, khi nhiều người đọc những dòng code này, sẽ thấy nó chưa ổn lắm, còn nhiều
lỗ hổng. Mình hoàn toàn tôn trọng điều đó — vì đây là phần làm **đi trước**: chưa được học
về học tăng cường, chưa được dìu dắt về điều khiển học với C#/.NET, và cũng thật khó khi
phải bơi trong hệ điều hành Windows chỉ với một cố vấn AI bên cạnh. Những thiếu sót là
điều dễ hiểu, và mình ghi nhận chúng như một phần của quá trình học.

Chân thành cảm ơn mọi đóng góp — kể cả reward thu về là **dương (benefits)** hay **âm
(issues)**. Tất cả đều có giá trị.

— Kết thúc dự án BatteryClaw.
