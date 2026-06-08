# BatteryClaw — Review code TỪNG DÒNG (Phần 6: FILE 31-36)

Tiếp nối phần 1-5 (file 1-30). Phần này: 2 file advanced cuối (mpc_planner, lstm_policy)
+ 3 file worldmodel (world_model, wm_env, train_on_wm) + 1 file datacollector
(data_collector).

Định dạng: trích dòng (kèm số dòng) → giải thích ngay dưới.

═══════════════════════════════════════════════════════════════════════════════
# FILE 31/48 — advanced/planning/mpc_planner.py  (120 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-17  """ docstring """ — Model-Based Planning: mô phỏng vài bước "trong đầu" bằng world model rồi chọn chuỗi action tốt nhất
19-31 import; [FIND-03] nạp DISCHARGE_MAX_MW từ commons
```
**Dòng 1-31:** Model-Based Planning: trước khi thực thi, mô phỏng vài bước tới bằng world
model (Phase 2), chọn chuỗi action tổng reward cao nhất. Trả lời "nếu tắt dGPU bây giờ,
vài bước nữa pin/mượt ra sao?". Dùng random-shooting MPC (MCTS đơn giản không cây): sinh
K chuỗi ngẫu nhiên dài H, rollout bằng world model, chọn chuỗi tốt nhất, trả action ĐẦU
TIÊN (receding horizon).

```
34-48 MPCPlanner.__init__(world_model_fn, reward_fn, horizon=5, n_candidates=64): lưu wm, reward, H, K, rng
```
**Dòng 34-48:** Khởi tạo. world_model_fn(s,a)→s' và reward_fn(row)→float truyền vào (không
buộc file cụ thể, dễ test). horizon=5 bước nhìn trước, n_candidates=64 chuỗi thử.

```
50-52 _sample_action(): sinh action thô [-1,1]
54-68 _action_to_reward_row(state, action): dựng row cho reward_fn (workload, discharge, throttle, gpu_switch, is_game...)
```
**Dòng 50-68:** Sinh action ngẫu nhiên. _action_to_reward_row dựng dict đầu vào cho hàm
reward từ state vector + action (decode workload từ obs[3], discharge từ obs[9], throttle/
gpu từ action).

```
70-90 plan(state_vec15): với K chuỗi, mỗi chuỗi H bước: sample action, cộng reward, rollout world model; giữ chuỗi tốt nhất; trả (action đầu, return)
```
**Dòng 70-90:** Hàm lập kế hoạch. Với mỗi chuỗi ứng viên: từ state hiện tại, sinh H action,
cộng reward dự đoán, dùng world model nhảy tới state kế (clip [0,1]). Lưu action đầu của
chuỗi có tổng reward cao nhất. Trả action đầu + return kỳ vọng. Đây là random-shooting:
đơn giản, không cần gradient.

```
93-120 self-test: world model giả (tắt dGPU → discharge giảm); reward thưởng discharge thấp; planner phải chọn action[3]<0 (tắt dGPU)
```
**Dòng 93-120:** Test: world model giả mô phỏng tắt dGPU giảm xả, reward thưởng xả thấp →
planner phải ưu tiên tắt dGPU. In PASS.

**TÓM TẮT:** [4.4] Lập kế hoạch dựa mô hình (MPC random-shooting) — "nghĩ trước vài bước"
bằng world model. LIÊN KẾT: worldmodel/world_model (cung cấp wm fn), datacollector/reward
(reward_fn). Lưu ý: nghiên cứu, chưa nối deploy; cần world model train tốt mới hữu ích.

═══════════════════════════════════════════════════════════════════════════════
# FILE 32/48 — advanced/memory/lstm_policy.py  (96 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-15  """ docstring """ — thêm BỘ NHỚ: policy nhìn chuỗi 30 state thay vì chỉ hiện tại
17-20 import torch/nn; SEQ_LEN=30
```
**Dòng 1-20:** Thêm bộ nhớ cho policy: thay vì policy(s_t)→a_t chỉ nhìn hiện tại, nâng cấp
policy(30 state gần nhất)→a_t để nhận mẫu theo thời gian ("vừa mở IDE → sắp compile",
"pin sắp hết → tiết kiệm khẩn"). LSTM nhẹ (hidden 128). SEQ_LEN=30 (khớp export_lstm_onnx
và OnnxPolicy).

```
23-33 LSTMPolicy.__init__(state_dim=15, action_dim=7, hidden=128, seq_len=30): LSTM + head (2 lớp → action)
```
**Dòng 23-33:** Mạng LSTM. nn.LSTM xử lý chuỗi (batch_first), head biến hidden cuối thành
action.

```
35-40 forward(seq, hidden_state): LSTM → lấy hidden bước cuối → tanh(head) → (action, hidden)
```
**Dòng 35-40:** Tiến: chuỗi (batch,30,15) qua LSTM, lấy output bước cuối (đã "nhớ" 30
bước), head → action tanh [-1,1]. Trả kèm hidden_state.

```
42-49 act(seq): deploy — eval, no_grad; thêm batch nếu cần; trả action numpy
```
**Dòng 42-49:** Suy luận deploy từ 1 chuỗi (30,15). Đây là cái export_lstm_onnx bọc (bỏ
hidden) để xuất ONNX.

```
52-69 SequenceBuffer.__init__/push/sequence: rolling window 30 state, padding 0 lúc đầu
```
**Dòng 52-69:** Bộ đệm chuỗi cho deploy. push đẩy state mới vào cuối (roll dịch). sequence
trả cả chuỗi (30,15), ô đầu là 0 khi chưa đủ. Tương đương _seq_buf trong OnnxPolicy của
rl_brain — đây là phiên bản torch.

```
72-96 self-test: forward batch → (4,7) trong [-1,1]; rolling window đẩy 40 → giữ 30 mới nhất (10..39); act từ buffer
```
**Dòng 72-96:** Test: forward đúng shape + range, rolling window giữ đúng 30 state mới
nhất, act từ buffer ra (7,). In PASS.

**TÓM TẮT:** [4.2] Policy có bộ nhớ (LSTM nhìn 30 state) + SequenceBuffer rolling window.
Hạ tầng deploy đã thông (qua export_lstm_onnx + OnnxPolicy tự nhận model chuỗi), nhưng
cần TRAIN thật (behavior cloning/RL) để LSTM giỏi — chưa làm. LIÊN KẾT: export_lstm_onnx
(export LSTMPolicy + SEQ_LEN), rl_brain OnnxPolicy (rolling window 30 khi deploy model chuỗi).

═══════════════════════════════════════════════════════════════════════════════
# FILE 33/48 — worldmodel/world_model.py  (207 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-23  """ docstring """ — HỌC luật vật lý máy từ dữ liệu thật: f(state,action)→Δstate
25-37 import; nạp STATE/ACTION/NEXT_STATE_COLUMNS từ schema; STATE_DIM=15, ACTION_DIM=7
```
**Dòng 1-37:** [2.2] Thay simulator viết tay bằng HỌC luật vật lý từ dữ liệu thật:
f(state_15, action_7)→Δstate_15, next = state + Δ. Học delta ổn định hơn (phần lớn state
ít đổi giữa 2 bước, mạng chỉ học phần "động"). Dùng cho Model-Based RL: train policy
nhanh + Phase 4 planning.

```
40-73 load_dataset(data_dir): đọc parquet/jsonl; bỏ dòng next_state rỗng; chuẩn hóa workload/4, gpu_switch/2, refresh/2; trả S, A, S_next
```
**Dòng 40-73:** Nạp dữ liệu từ datacollector. Đọc parquet hoặc jsonl, ghép, bỏ transition
thiếu next_state. Chuẩn hóa workload_id/4, action gpu_switch và refresh /2 (đưa về thang
NN). Trả 3 mảng state/action/next_state.

```
76-95 build_model(): WorldModel MLP (state+action → hidden → Δstate); forward: next = state + Δ
```
**Dòng 76-95:** Mạng world model. MLP nhỏ nhận concat(state 15 + action 7) → Δstate 15.
forward cộng delta vào state hiện tại → next_state. Đủ nhẹ chạy trên laptop.

```
98-141 train(data_dir, epochs, lr): chia train/val; Adam + MSE; vòng epoch; log train/val mse định kỳ
```
**Dòng 98-141:** Train world model. Chia 85/15 train/val. Cảnh báo nếu <50 transition.
Vòng epoch chuẩn (forward → MSE loss → backward). Log train/val mse mỗi 10% epoch.

```
143-153 đánh giá riêng chiều discharge (index 9, quan trọng nhất); lưu .pt
```
**Dòng 143-153:** Đánh giá MAE riêng chiều discharge_norm (chiều quan trọng nhất cho tiết
kiệm pin), quy ra mW. Lưu model.

```
155-168 export ONNX: (state15, action7) → next_state15
170 return model
```
**Dòng 155-170:** Export ONNX để engine/planning dùng (2 input state+action → next_state).

```
173-187 evaluate(data_dir, model_path): MSE model vs baseline ngây thơ "next=current"
```
**Dòng 173-187:** Đánh giá: so MSE của world model với baseline ngây thơ (giả định state
không đổi). Model tốt nếu MSE thấp hơn baseline — cách kiểm khách quan model có học được gì.

```
190-207 main: argparse --data/--epochs/--lr/--batch/--out/--eval → train hoặc evaluate
```
**Dòng 190-207:** CLI: train hoặc chỉ đánh giá model có sẵn.

**TÓM TẮT:** [2.2] Học mô hình động lực học của máy từ dữ liệu thật (f: s,a→Δs). Nền cho
Model-Based RL + planning. LIÊN KẾT: datacollector/schema (cột dữ liệu), wm_env (bọc
world model thành Gym env), train_on_wm (train policy trên world model), mpc_planner
(dùng làm wm fn). Lưu ý: cần thu đủ dữ liệu thật mới train tốt; là hạ tầng Phase 2.

═══════════════════════════════════════════════════════════════════════════════
# FILE 34/48 — worldmodel/wm_env.py  (164 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-14  """ docstring """ — Gym env BỌC world model học được thay simulator viết tay
16-39 import; nạp schema + reward + DISCHARGE_MAX_MW; STATE_DIM=15, ACTION_DIM=7
```
**Dòng 1-39:** Gym env dùng world model (đã học) làm hàm chuyển trạng thái thay simulator
viết tay. Khác battery_env: next_state = WorldModel(s,a) (học từ data thật) + reward =
compute_reward (công thức thật 2.3). Là "Simulator Thực" Phase 2 hướng tới — policy train
trên động học thật của máy.

```
42-76 WorldModelEnv.__init__(model_path, weights, episode_steps=360): nạp world model; observation/action space (giống Phase 1)
```
**Dòng 42-76:** Khởi tạo env. Nạp world model từ .pt (eval mode). observation 15 chiều
[0,1], action 7 chiều với sàn an toàn (giống battery_env). RewardWeights cho công thức reward.

```
78-85 reset: state ngẫu nhiên [0,1], battery 0.4-0.9; step_count=0
```
**Dòng 78-85:** Reset: khởi tạo state ngẫu nhiên hợp lý (pin 40-90%).

```
87-96 _action_for_model(action): rời rạc hóa gpu_switch/refresh, chuẩn hóa /2 (khớp lúc train world model)
```
**Dòng 87-96:** Chuẩn hóa action giống lúc train world model: rời rạc hóa gpu_switch (ngưỡng
0.5) và refresh (3 mức), chia 2. Đảm bảo input khớp model.

```
98-135 step(action): world model → next_state (clip); dựng row → compute_reward; terminated nếu pin≤2%; info
```
**Dòng 98-135:** Bước env. Chạy world model ra next_state, clip [0,1]. Dựng row (workload
từ obs[3], discharge từ obs[9]×80000...) rồi tính reward thật. terminated khi gần hết pin
(≤2%), truncated khi hết giờ. info kèm discharge/gpu/reward parts. render in trạng thái.

```
137-141 render: in trạng thái nếu human mode
144-164 self-test: cần world_model.pt; check_env; chạy 15 bước random
```
**Dòng 137-164:** render in pin + discharge. Test: cần model .pt tồn tại (chưa có thì bỏ
qua), env_checker, chạy 15 bước random.

**TÓM TẮT:** [2.2+2.3] Gym env dùng world model học được + reward thật → "simulator thực".
LIÊN KẾT: world_model (build_model + .pt), datacollector/reward (compute_reward, file 37),
datacollector/schema, train_on_wm (train policy trên env này). Lưu ý: cần world model
train tốt; hạ tầng Phase 2.

═══════════════════════════════════════════════════════════════════════════════
# FILE 35/48 — worldmodel/train_on_wm.py  (87 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  """ docstring """ — train PPO trên WorldModelEnv rồi export ONNX khớp rl_brain
15-28 import; nạp WorldModelEnv + STATE/ACTION_DIM; RewardWeights
```
**Dòng 1-28:** Train policy PPO trên WorldModelEnv (động học học từ data thật + reward
thật) rồi export ONNX (1,15)→(1,7) đúng contract rl_brain. Khác simulator/train.py: môi
trường là world model học được (2.2) + reward công thức thật (2.3).

```
31-44 main: argparse --wm/--steps/--out/--alpha/--beta/--gamma/--delta; kiểm world model tồn tại
```
**Dòng 31-44:** CLI. Tham số α/β/γ/δ cho công thức reward. Kiểm file world model tồn tại
trước (chưa có thì báo chạy world_model.py).

```
46-59 tạo RewardWeights; DummyVecEnv 2 env; PPO MlpPolicy [128,128]; learn(steps)
```
**Dòng 46-59:** Tạo 2 env song song bọc world model. Train PPO (mạng [128,128], batch
256, n_steps 512). Đây là PPO chuẩn nhưng chạy trên world model thay simulator.

```
62-71 PolicyWrapper: extract_features → mlp_extractor → action_net → tanh (deterministic mean)
73-83 export ONNX (batch,15)→(batch,7); in hướng dẫn deploy
```
**Dòng 62-83:** Wrapper lấy mean action tanh (giống train.py Phase 1) rồi export ONNX
khớp rl_brain. In lệnh deploy. Cùng cơ chế export như simulator/train.py.

**TÓM TẮT:** Train policy trên world model (Phase 2) thay vì simulator viết tay, export
ONNX deploy được. LIÊN KẾT: wm_env (môi trường), datacollector/reward (RewardWeights),
rl_brain (dùng ONNX). Lưu ý: cần world model train tốt từ dữ liệu thật; hạ tầng Phase 2,
bản deploy chính hiện dùng model PPO từ simulator (Phase 1) đã cá nhân hóa.

═══════════════════════════════════════════════════════════════════════════════
# FILE 36/48 — datacollector/data_collector.py  (317 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-25  """ docstring """ — thu thập THỤ ĐỘNG: quan sát engine, ghi transition, không can thiệp
27-56 import; nạp schema (cột + helper); [MINOR-A] GPU_POWER_MAX/DISCHARGE_MAX từ commons; logging
58-60 PIPE_NAME; DEFAULT_DIR; FLUSH_EVERY=60
```
**Dòng 1-60:** [2.1] Thu thập dữ liệu thụ động: nối engine qua pipe (như rl_brain) NHƯNG
không gửi action — chỉ quan sát + ghi. Mỗi chu kỳ ghi 1 transition (state, action,
next_state) + trường thô để train world model + tính reward. Lưu parquet, flush mỗi 60 dòng.

```
64-107 state_json_to_obs_and_raw(s): dựng 15 obs + raw dict; [DESIGN-06] classify_workload (CPU+GPU)
```
**Dòng 64-107:** Chuyển JSON state engine thành 15 obs + raw (discharge/gpu_power/temp...).
Dùng classify_workload (CPU+GPU, khác rl_brain dùng CPU-only) vì đây là dữ liệu để train
world model + reward, không phải input model đã train.
⚠ **Dòng 88:** chuẩn hóa refresh dùng `(165 - 60)` — KHÁC rl_brain và battery_env dùng
`(144 - 60)`. Đây là điểm KHÔNG ĐỒNG NHẤT: dữ liệu thu refresh_norm sẽ lệch scale so với
lúc train/deploy. Nếu sau này train world model từ dữ liệu này thì refresh_norm sai một
chút. Nên sửa 165→144 cho khớp PANEL_MAX_HZ (cùng họ với hằng số chết REFRESH_MAX_HZ=165).

```
110-126 observed_action_from_state(s): action "quan sát" = cấu hình điều khiển hiện tại (throttle/brightness/refresh/gpu đang đặt)
```
**Dòng 110-126:** Khi thu thụ động, action = trạng thái điều khiển hiện tại của máy
(không phải lệnh AI). refresh_mode/gpu_switch suy từ trạng thái thật. defer/wifi/charge
mặc định 0 (không quan sát được trực tiếp).

```
129-169 ParquetWriter: ghi transition ra parquet theo session; flush mỗi 60 dòng; fallback JSONL nếu thiếu pandas
```
**Dòng 129-169:** Ghi dữ liệu ra parquet (tên kèm timestamp + session). Flush gộp với
file cũ. Nếu thiếu pandas/pyarrow → fallback ghi JSONL để không mất dữ liệu.

```
172-217 run_with_engine(args, writer): nối pipe; đọc state từng dòng; ghép transition (_record); thu theo --minutes
```
**Dòng 172-217:** Thu từ engine thật. Nối pipe (retry), đọc state theo dòng JSON, mỗi
state ghép với state trước thành transition. Dừng khi hết --minutes.

```
220-276 run_simulated(args, writer): sinh dữ liệu giả từ battery_env (test pipeline không cần Windows)
```
**Dòng 220-276:** Chế độ --simulate: sinh transition từ battery_env (để test pipeline
Phase 2 trên Linux không cần engine Windows). Map vector env → dict schema, có reward sẵn.

```
279-291 _record(...): ghép (prev_obs, prev_action) với cur_obs làm next_state → 1 transition; reward để trống
```
**Dòng 279-291:** Ghép transition: state trước + action trước + state hiện tại làm
next_state. reward để trống (0), tính sau bằng reward.py khi build dataset (vì máy thật
chưa biết reward lúc thu).

```
294-317 main: argparse --session/--minutes/--interval/--out/--simulate/--steps/--seed → run_with_engine hoặc run_simulated
```
**Dòng 294-317:** CLI. Thu thật hoặc giả lập. Ctrl+C → flush trước khi thoát.

**TÓM TẮT:** [2.1] Thu thập dữ liệu thật từ máy người dùng (thụ động, không can thiệp) để
train world model + tính reward. Có chế độ simulate để test. CHỨA 1 điểm lệch chuẩn hóa
refresh (dòng 88: 165 thay vì 144). LIÊN KẾT: schema (cột + classify_workload), reward
(tính sau), world_model (dùng dữ liệu này train), constants.

───────────────────────────────────────────────────────────────────────────────
HẾT PHẦN 6 (FILE 31-36): mpc_planner, lstm_policy, world_model, wm_env, train_on_wm,
data_collector. Còn datacollector: schema, reward, dataset_uploader (3) + commercial
(4) + app (2) + server + dashboard + tests → phần 7+.
───────────────────────────────────────────────────────────────────────────────
