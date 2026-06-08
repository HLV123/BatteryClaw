# BatteryClaw — Tổng kết nâng cấp phần Mô phỏng (Simulator)

Tài liệu này tóm tắt: (1) dự án là gì, (2) simulator TRƯỚC kia có gì, (3) SAU khi
nâng cấp thêm những gì. Dùng để bạn đánh giá và đề xuất bổ sung tiếp.

---

## 0. Dự án này là gì (nhắc lại bối cảnh)

BatteryClaw là phần mềm AI tối ưu pin laptop Windows. AI (một "policy") nhận **15
con số** mô tả tình trạng máy (observation) và xuất **7 hành động** (action) như
chỉnh CPU, độ sáng, tắt card rời... Policy này được **huấn luyện trong Simulator**
trước khi đem ra máy thật.

Simulator chính là "sân tập" của AI: một mô hình giả lập pin laptop, nơi AI thử
hàng triệu lần "làm X → pin thay đổi thế nào → được thưởng/phạt bao nhiêu". Chất
lượng AI **phụ thuộc trực tiếp** vào việc simulator giống thực tế tới đâu và phong
phú tới đâu. Simulator nghèo nàn → AI chỉ giỏi trong vài tình huống hẹp. Simulator
phong phú → AI tổng quát, xử lý được nhiều hoàn cảnh.

> Vì sao không "fake data" mà phải dùng simulator: trong Reinforcement Learning,
> AI học từ *hệ quả* của hành động. Simulator tạo ra hệ quả **nhất quán về vật lý**
> (tải cao thì xả nhanh, tắt GPU thì đỡ tốn...). Dữ liệu bịa ngẫu nhiên thì mâu
> thuẫn vật lý, khiến AI học loạn. Nên ta làm giàu simulator, không bịa số.

---

## 1. TRƯỚC kia — Simulator có gì (bản gốc)

Bản gốc đã chạy được và đủ để train model demo, nhưng khá đơn giản:

### Workload (kiểu dùng máy)
- **Chỉ 5 loại**: `idle`, `browse`, `office`, `compile`, `game`.

### Phần cứng
- **Chỉ MỘT máy cố định** (đúng cấu hình máy MSI: pin 33026 mWh, health ~64%,
  panel 144Hz). Mọi lần train đều trên đúng máy đó.

### Mô hình điện
- Công suất CPU tra **bảng tĩnh** (POWER_PROFILE), chia 3 mức throttle (100/70/50%).
- GPU, màn hình, wifi tính đơn giản; wifi coi như luôn bật, mức cố định.

### Pin & nhiệt
- **Chỉ xả pin**, không có mô hình sạc thật sự (có biến `_plugged` nhưng gần như
  không dùng).
- Nhiệt độ cập nhật đơn giản theo công suất, **không có nhiệt độ phòng**, không có
  thermal throttle (quá nóng vẫn chạy như thường).

### Người dùng & thời gian
- **Không mô phỏng cá tính người dùng** (ai cũng như ai).
- Thời điểm trong ngày có tính nhưng **không ảnh hưởng** loại việc đang làm.

### Reward (điểm thưởng)
- Tiết kiệm − giật − khó chịu + chút thưởng tuổi thọ.
- Kết thúc: chỉ cộng điểm theo % pin còn lại; **không phạt mạnh khi pin chết**.

**Tóm lại**: AI train trên bản này chỉ "quen" đúng 5 việc, đúng 1 máy, không bao
giờ thấy cảnh sạc, máy nóng, hay người dùng khó tính → ra thực tế dễ lúng túng.

---

## 2. SAU khi nâng cấp — Thêm những gì

Giữ nguyên contract 15→7 (không phá tương thích), nhưng làm giàu rất nhiều:

### Workload: 5 → **12 loại**
`idle`, `web_light`, `web_heavy` (nhiều tab), `office`, `video_call`, `video_play`
(xem phim), `music`, `code_ide`, `compile`, `render` (3D/video), `game_light`,
`game_heavy`. Mỗi loại có hồ sơ riêng: tải CPU, tải GPU, có cần card rời không,
ngưỡng chịu giật, mức dùng mạng, có âm thanh không, áp lực RAM.

### Phần cứng: 1 máy → **6 loại máy bốc ngẫu nhiên mỗi lượt train**
Ultrabook (không card rời, 60Hz), laptop văn phòng, laptop có MX (120Hz), gaming
RTX 3050 (144Hz, giống máy thật), gaming cao cấp (165Hz, pin lớn), máy cũ pin chai.
→ AI buộc phải học cách tối ưu cho **mọi loại máy**, không chỉ một.

### Độ chai pin ngẫu nhiên
Mỗi episode pin có độ chai khác nhau (60–100%) → AI quen cả máy pin tốt lẫn pin yếu.

### Mô hình SẠC thật
- Cắm/rút sạc **ngẫu nhiên** giữa chừng (sự kiện bất ngờ).
- Đang sạc thì pin **tăng** (không chỉ xả), và máy **nóng thêm**.
- `charge_limit` dừng sạc ở 80% để bảo vệ tuổi thọ pin → AI học bật đúng lúc.

### Nhiệt độ động + Thermal throttle
- Nhiệt phụ thuộc công suất **+ nhiệt độ phòng** (bốc ngẫu nhiên 18–38°C).
- Quá nóng (>90°C) thì **hiệu năng tụt** (thermal throttle) → AI học tránh để máy quá nóng.

### Mạng, âm thanh, RAM thật theo workload
- Video call / tải file dùng mạng nặng → tốn điện hơn; `wifi_save` giảm tải.
- Âm thanh (xem phim/nhạc/game) tiêu thụ thêm.
- RAM pressure khác nhau theo việc.

### Chu kỳ Ngày/Đêm ảnh hưởng hành vi
- Giờ hành chính: hay gặp office/code/compile/họp.
- Buổi tối: hay game/xem phim/nghe nhạc.
- Khuya: chủ yếu việc nhẹ.
→ AI học được "ngữ cảnh thời gian", chủ động hơn.

### Cá tính người dùng (mỗi episode khác nhau)
- Độ **nhạy cảm với giật** (người khó tính ghét máy lag).
- Độ **nhạy cảm với màn tối** (người ghét giảm sáng).
→ AI học cân bằng linh hoạt thay vì áp một công thức cứng cho mọi người.

### Reward tinh hơn
- Tiết kiệm so với **baseline "không tối ưu"** (tính theo từng máy).
- Phạt giật có nhân với độ nhạy người dùng + phạt khi máy quá nóng + phạt ép tắt
  card rời khi đang cần.
- Thưởng tuổi thọ khi sạc + giữ pin <80%; **phạt** khi cắm sạc mà để pin đầy 95%+ (hại pin).
- **Phạt nặng (−5) khi để pin chết**; thưởng theo % pin còn sống tới cuối phiên.

### Train mạnh hơn (train.py)
- Mạng neuron: [128,128] → **[256,256]** (gấp đôi sức chứa).
- Số môi trường song song: 4 → **8**; batch 256 → **512**; entropy 0.01 → **0.02**
  (khám phá tốt hơn với simulator đa dạng).
- Mặc định: 500k → **2.000.000 steps** (khuyến nghị chạy 3–5 triệu để mạnh thật).

---

## 3. Bảng so sánh nhanh

| Hạng mục | TRƯỚC | SAU |
|---|---|---|
| Số workload | 5 | **12** |
| Số loại máy | 1 (cố định) | **6** (ngẫu nhiên) |
| Độ chai pin | cố định | **ngẫu nhiên 60–100%** |
| Sạc pin | gần như không | **có: cắm/rút, sạc tăng pin, charge limit 80%** |
| Nhiệt độ phòng | không | **có (18–38°C)** |
| Thermal throttle | không | **có (>90°C giảm hiệu năng)** |
| Mạng/âm thanh/RAM | đơn giản/cố định | **theo từng workload** |
| Ngày/đêm ảnh hưởng việc | không | **có** |
| Cá tính người dùng | không | **có (nhạy giật / nhạy màn tối)** |
| Phạt pin chết | không | **−5** |
| Mạng neuron | [128,128] | **[256,256]** |
| Steps mặc định | 500k | **2 triệu (khuyến nghị 3–5 triệu)** |

---

## 4. Còn có thể thêm gì nữa (gợi ý để bạn cân nhắc)

Những thứ CHƯA có, có thể làm giàu thêm nếu muốn AI khôn hơn nữa:

- **Độ sáng môi trường** (trong nhà/ngoài trời) ảnh hưởng nhu cầu độ sáng màn hình.
- **Pin nhiều cell / đường cong xả phi tuyến** (pin tụt nhanh hơn ở mức thấp).
- **Nhiều màn hình ngoài / cắm dock** (tốn điện thêm).
- **Tác vụ nền định kỳ** (Windows Update, antivirus quét) như cú "spike" bất ngờ.
- **Thói quen cá nhân dài hạn** (người này hay cắm sạc lúc nào, dùng app gì) —
  hiện cá tính chỉ trong 1 episode, có thể mô phỏng "cùng một người qua nhiều ngày".
- **Tiếng ồn quạt / giới hạn nhiệt theo dòng máy** (máy mỏng nóng nhanh hơn).
- **Chế độ tiết kiệm của Windows** tương tác với hành động của AI.
- **Độ trễ thực thi** (lệnh AI gửi không có hiệu lực tức thì mà sau vài giây).
- **Phần thưởng theo "trải nghiệm mượt"** đo bằng FPS game / độ trễ thao tác, không
  chỉ throttle.

---

## 5. Trạng thái hiện tại

- Simulator nâng cấp: **env_checker PASS**, observation luôn trong [0,1], chạy nhanh
  (~7500 steps/giây).
- Pipeline train: **đã test** train + đánh giá + xuất ONNX (15→7) chạy thông.
- Contract dữ liệu: **11/11 unit test PASS** (không phá tương thích với rl_brain/engine).
- Việc tiếp theo: train dài (3–5 triệu steps) trên máy để ra model mạnh, rồi đóng gói.
