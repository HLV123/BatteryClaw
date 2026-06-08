# BatteryClaw — Tổng kết nâng cấp Mô phỏng (Simulator) Đợt 2

Tài liệu này tóm tắt đợt nâng cấp simulator lần 2: trạng thái TRƯỚC đợt 2, những
gì vừa THÊM, và những gì bị TỪ CHỐI kèm lý do. Dùng để bạn đánh giá và đề xuất tiếp.

> Nhắc lại: Simulator là "sân tập" của AI. Mọi tính năng phải tôn trọng **contract
> bất biến 15 observation → 7 action** (khớp cứng giữa simulator, rl_brain, engine C#).
> Đây là tiêu chí lọc quan trọng nhất: muốn AI "nhìn thấy" yếu tố mới thì phải nhét
> vào 15 số đó — mà 15 số đã đầy. Yếu tố nào engine thật KHÔNG đọc được thì train
> vào sẽ phản tác dụng (AI học theo tín hiệu không tồn tại lúc chạy thật).

---

## 1. TRƯỚC đợt 2 (kết quả của đợt 1)

Sau đợt 1, simulator đã khá phong phú:

- **12 workload**: idle, web_light, web_heavy, office, video_call, video_play,
  music, code_ide, compile, render, game_light, game_heavy.
- **6 loại máy** bốc ngẫu nhiên mỗi episode (ultrabook → gaming cao cấp), khác nhau
  pin/dGPU/CPU base/panel Hz.
- **Độ chai pin ngẫu nhiên** 60–100%.
- **Mô hình sạc**: cắm/rút ngẫu nhiên, sạc tăng pin + nóng thêm, charge limit 80%.
- **Nhiệt độ động** theo công suất + nhiệt độ phòng (18–38°C) + thermal throttle >90°C.
- **Mạng/âm thanh/RAM** thật theo workload.
- **Chu kỳ ngày/đêm** ảnh hưởng loại workload hay gặp.
- **Cá tính người dùng**: độ nhạy giật / nhạy màn tối khác nhau mỗi episode.
- **Reward**: tiết kiệm − giật − khó chịu + tuổi thọ; phạt −5 khi pin chết.
- Train: mạng [256,256], 8 env song song, mặc định 2 triệu steps.

**Hạn chế còn lại**: môi trường vẫn "sạch và tuyến tính" — lệnh AI có hiệu lực tức
thì (không thực tế), không có tác vụ ngầm bất ngờ, pin tụt đều tuyến tính, và train
"đổ" hết độ khó vào model ngay từ đầu (dễ ngợp khi train dài).

---

## 2. SAU đợt 2 — Vừa thêm 4 tính năng

Tất cả giữ nguyên contract 15→7, **không thêm observation**, khớp 100% engine thật.

### F1 — Độ trễ thực thi (Action Delay)
- **Vấn đề thật**: AI ra lệnh (tắt dGPU, giảm sáng) nhưng HĐH cần ~1–2s mới áp dụng
  xong; trong lúc đó dòng xả vẫn cao.
- **Đã làm**: lệnh AI đi vào một hàng đợi, trễ **2 step (20s)** mới thực sự có hiệu
  lực. AI học **tính kiên nhẫn**, tránh ra lệnh dao động liên tục (action oscillation).
- Bật ở độ khó cao nhất (difficulty 3).

### F2 — Tác vụ ngầm bất ngờ (Spike Workload)
- **Vấn đề thật**: Windows Update / antivirus / OneDrive đột ngột vọt CPU vài phút.
- **Đã làm**: ~2%/step kích hoạt một "spike" cộng tải CPU (+0.55) kéo 30–120s rồi
  tắt. AI **không tắt được** spike → phải học chịu đựng / bù trừ thay vì hoảng loạn
  hạ hết xung làm máy lag thêm.
- Bật ở difficulty 3.

### F3 — Đường cong xả pin phi tuyến + sập nguồn ảo
- **Vấn đề thật**: pin Li-ion tụt đều từ 100%→20%, nhưng dưới 20% tụt rất nhanh;
  pin chai còn "tụt áp" làm máy sập nguồn sớm (ví dụ ở 5%).
- **Đã làm**: dưới 20% nhân hệ số xả tăng dần (tới ~1.8×, pin càng chai càng dốc);
  pin chai nặng có thể sập nguồn (brownout) trước khi về 0. AI học **"càng cuối càng
  phải chắt chiu"**.
- Bật ở difficulty 3.

### F4 — Curriculum Learning (học theo giáo trình)
- **Vấn đề thật**: ném cả 6 máy + sạc rút + người khó tính + phá bĩnh vào ngay từ
  đầu → model dễ "ngợp", hội tụ chậm, dễ ra chính sách hỗn loạn.
- **Đã làm**: thêm tham số `difficulty` (1=dễ: 1 máy ultrabook, không phá bĩnh;
  2=vừa: 6 máy + 12 workload; 3=full: bật hết F1/F2/F3 + sạc rút ngẫu nhiên).
  `train()` chia **3 phase**: 15% steps ở diff 1 → 35% ở diff 2 → 50% ở diff 3,
  dùng `model.set_env()` đổi độ khó giữa các phase, giữ đếm timestep liên tục.
- Tắt bằng `--no-curriculum` nếu muốn train thẳng độ khó full.
- train.py: mặc định `--steps 3,000,000`, `--envs 8`.

**Kiểm thử**: env_checker PASS ở cả 3 difficulty; obs luôn trong [0,1]; train thử
60k steps qua 3 phase chuyển mượt; ONNX export đúng (15→7); contract 11/11 test PASS.

---

## 3. TỪ CHỐI — và vì sao

Ba đề xuất hay về lý thuyết nhưng bị hoãn vì lệch thực tế hệ thống:

### Ambient Light (độ sáng môi trường) — TỪ CHỐI
- **Ý tưởng**: thêm biến `ambient_lux`, phạt nặng nếu ngoài nắng mà AI giảm độ sáng.
- **Vì sao từ chối**: để AI hành xử theo ánh sáng môi trường, nó phải **nhìn thấy**
  lux → cần thêm một observation. Nhưng (a) 15 số đã đầy, và (b) quan trọng hơn:
  **engine C# trên máy thật không đọc được cảm biến ánh sáng** (đa số laptop không
  expose qua WMI, kể cả máy MSI hiện tại). Train AI dựa trên một chiều mà lúc deploy
  luôn bằng 0/giả → AI học theo **tín hiệu không tồn tại** → quyết định sai trên máy
  thật. Chỉ nên làm nếu xác nhận phần cứng đọc được lux thật.

### Fan Noise (tiếng ồn quạt) — HOÃN (ưu tiên thấp)
- **Ý tưởng**: thêm biến `fan_speed` theo nhiệt + độ mỏng máy, đưa vào hàm phạt.
- **Vì sao hoãn**: phần *phạt* thì làm được mà không cần thêm observation (AI suy ra
  từ nhiệt độ đã có ở obs[2]). NHƯNG giá trị thực tế thấp hơn F1–F3, và engine thật
  không đọc tốc độ quạt để xác nhận/đối chiếu. Làm được nhưng để sau.

### LSTM / Bộ nhớ cho Policy — HOÃN (rủi ro cao)
- **Ý tưởng**: nâng policy từ MLP phẳng lên RNN/LSTM để có "trí nhớ ngắn hạn".
- **Vì sao hoãn**: policy hiện xuất ONNX dạng `(batch,15)→(batch,7)` **không trạng
  thái**. LSTM cần truyền hidden state qua các bước → **ONNX export phức tạp hơn
  nhiều, và rl_brain + engine WinML hiện KHÔNG xử lý hidden state**. Project có sẵn
  LSTM ở Phase 4 nhưng cố ý không bật vào luồng deploy chính vì lý do này. Nếu làm
  phải sửa cả rl_brain lẫn cách load ONNX — thay đổi lớn, rủi ro cao. Để cuối cùng,
  sau khi F1–F4 đã ổn và thấy AI thật sự cần trí nhớ.

---

## 4. Bảng tổng hợp đợt 2

| Tính năng | Trạng thái | Cần thêm observation? | Khớp engine thật? |
|---|---|---|---|
| F1 Action Delay | ✅ Đã làm | Không | Có |
| F2 Spike Workload | ✅ Đã làm | Không | Có |
| F3 Pin phi tuyến | ✅ Đã làm | Không | Có |
| F4 Curriculum Learning | ✅ Đã làm | Không (đổi cách train) | Có |
| Ambient Light | ❌ Từ chối | Có (lux) | KHÔNG (cảm biến không đọc được) |
| Fan Noise | ⏸ Hoãn | Không (chỉ phạt) | Một phần |
| LSTM Policy | ⏸ Hoãn | Không (đổi kiến trúc) | Cần sửa rl_brain + ONNX |

---

## 5. Gợi ý hướng đợt 3 (để bạn cân nhắc)

Các ý vẫn tôn trọng "không thêm observation lệch phần cứng":

- **Reward theo trải nghiệm mượt** (proxy độ mượt thay vì chỉ throttle): phạt khi
  throttle thấp lúc workload tương tác cao (game/cuộn trang), thưởng khi mượt + tiết kiệm.
- **Mô phỏng người dùng dài hạn**: cùng một người qua nhiều "ngày" (giữ cá tính ổn
  định qua episode) để chuẩn bị cho online learning cá nhân hóa.
- **Hành vi sạc theo thói quen**: người dùng có lịch cắm sạc lặp lại (sáng cắm ở công
  ty, tối cắm ở nhà) thay vì cắm/rút thuần ngẫu nhiên.
- **Đa dạng nhiệt theo dòng máy**: máy mỏng nóng nhanh + throttle sớm hơn máy dày.
- **Tinh chỉnh trọng số reward (A/B/C/D)** theo profile người dùng (đã có hạ tầng
  profiles ở Phase 6) để cùng một model phục vụ nhiều kiểu người.

---

## 6. Trạng thái hiện tại

- Simulator + curriculum: env_checker PASS (3 difficulty), obs trong [0,1], train
  thử 3 phase chuyển mượt, ONNX export 15→7 OK, contract 11/11 test PASS.
- Việc tiếp theo: `python simulator\train.py --steps 3000000` (tự chạy curriculum
  3 phase) → ra model mạnh → đóng gói bằng build_business.ps1.
