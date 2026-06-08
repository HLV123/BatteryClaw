# BatteryClaw — Review code TỪNG DÒNG (Phần 5: FILE 25-30)

Tiếp nối phần 1-4 (file 1-24). Phần này: 2 file online cuối (brain_online_adapter,
hrl_integration) + 4 file advanced (sac/networks, sac/sac_trainer, hierarchy/manager,
hierarchy/worker).

Định dạng: trích dòng (kèm số dòng) → giải thích ngay dưới.

═══════════════════════════════════════════════════════════════════════════════
# FILE 25/48 — online/brain_online_adapter.py  (114 dòng — CẦU NỐI)
═══════════════════════════════════════════════════════════════════════════════

```
1-12  """ docstring """ — nối OnlineLearner với rl_brain qua 3 hàm: refine/observe/tick
14-21 import + path; from online_loop import OnlineLearner
```
**Dòng 1-21:** Cầu nối OnlineLearner (Phase 3) với rl_brain mà không làm rl_brain phình.
rl_brain chỉ gọi 3 thứ: refine (command an toàn), observe (tích transition), tick
(fine-tune khi nhàn). Việc chuyển đổi giữa "command JSON" và "action dict schema" gói tại đây.

```
24-35 command_to_action(cmd): command JSON rl_brain → action dict Phase 3 (cpu_max/100, brightness/100, defer, gpu_switch, refresh, wifi, charge)
```
**Dòng 24-35:** Chuyển command JSON (rl_brain) sang action dict (schema Phase 3). Chia 100
đưa % về [0,1]. brightness=-1 → 0.8 mặc định.

```
38-48 action_to_command(cmd_in, action): action dict (đã an toàn) → ghi đè lại command JSON
```
**Dòng 38-48:** Chiều ngược: action dict đã chỉnh an toàn → ghi đè command JSON để gửi
engine. Nhân 100 đổi về %, charge_limit_on>0.5 → 80 (hoặc -1).

```
51-55 BrainOnlineAdapter.__init__(state_dir, policy, model_path): tạo OnlineLearner
57-61 refine(command, state): command→action; finalize_action (mode+constraints); action→command
```
**Dòng 51-61:** Adapter chính. refine: chuyển command→action, áp mode + ràng buộc an toàn,
chuyển ngược. Đây là cái rl_brain.run() gọi trước khi gửi engine.

```
63-75 observe(obs_vec, action_vec, reward, next_obs, state): suy workload từ cpu_load; lấy giờ; learner.observe
```
**Dòng 63-75:** Tích transition. Suy workload từ cpu_load (nếu state không có sẵn), lấy
giờ hiện tại, gọi learner.observe (buffer + pattern + feedback).

```
77-91 tick() = maybe_finetune; mark_activity; feedback(kind); set_mode; save
```
**Dòng 77-91:** Các hàm ủy quyền cho learner: tick (fine-tune khi nhàn), đánh dấu hoạt
động, feedback nút bấm, đặt mode, lưu state.

```
94-114 self-test: refine (game+nóng → an toàn); observe + feedback → buffer 2
```
**Dòng 94-114:** Test: refine khi game+nóng ép gpu_switch=1 + cpu≤60; observe + feedback
→ buffer có 2 transition. In PASS.

**TÓM TẮT:** Cầu nối gọn giữa Phase 3 và rl_brain — dịch qua lại command JSON ↔ action
dict, để 2 bên không phụ thuộc nhau. LIÊN KẾT: rl_brain (gọi refine/observe/tick trong
run()), online_loop (OnlineLearner bên dưới).

═══════════════════════════════════════════════════════════════════════════════
# FILE 26/48 — online/hrl_integration.py  (101 dòng — Tầng 2.3)
═══════════════════════════════════════════════════════════════════════════════

```
1-18  """ docstring """ — nối HRL vào deploy ở mức "chọn chiến lược" (opt-in)
20-31 import + path advanced/hierarchy; try import Manager → _HAS_MANAGER
```
**Dòng 1-31:** Nối Hierarchical RL vào deploy mà KHÔNG phá policy phẳng: Manager (tầng
cao) nhìn pin/giờ/sạc → quyết chế độ → map sang PROFILE MODEL (3 model Tầng 1.1) → app
tự đổi model. Dùng HRL mức "chọn chiến lược" (thực dụng, an toàn) thay vì Worker
goal-conditioned từng action (phức tạp). Mặc định tắt. _HAS_MANAGER xử lý khi thiếu module.

```
34-39 _MODE_TO_PROFILE: save_max→battery_saver, balanced→balanced, performance→performance
```
**Dòng 34-39:** Bảng ánh xạ chế độ Manager sang tên profile model (để chọn file onnx
tương ứng).

```
42-52 AutoProfileManager.__init__(stable_count=3): tạo Manager; cur_profile="balanced"; _pending/_pending_n cho hysteresis
```
**Dòng 42-52:** Bọc Manager. Hysteresis: chỉ đổi profile khi chế độ mới ổn định
stable_count lần liên tiếp (tránh đổi model xoành xoạch — mỗi lần đổi phải nạp lại ONNX).

```
54-55 available(): có Manager không
57-79 suggest(battery_pct, hour, plugged, pattern_hint): Manager.decide → mode → profile; hysteresis trước khi đổi cur_profile
```
**Dòng 54-79:** suggest là hàm chính. Manager quyết chế độ theo hoàn cảnh, map sang profile.
Hysteresis (66-78): nếu profile mong muốn khác hiện tại, phải lặp đủ stable_count lần mới
đổi thật; trùng hiện tại thì reset bộ đếm chờ.

```
81-85 last_reason(...): lý do Manager quyết (để hiển thị/giải thích)
88-101 self-test: pin 10% x3 → battery_saver; cắm sạc x3 → performance
```
**Dòng 81-101:** last_reason trả lý do (chuỗi giải thích). Test: pin thấp lặp 2 lần →
battery_saver; cắm sạc lặp 2 lần → performance (stable_count=2). In PASS.

**TÓM TẮT:** [2.3] Dùng HRL Manager để tự đổi profile model theo hoàn cảnh, có hysteresis.
Cách nối HRL thực dụng không phá contract. LIÊN KẾT: advanced/hierarchy/manager (Manager.
decide), app/buy_business (có thể dùng để tự đổi profile). Opt-in — app GUI cần bật.

═══════════════════════════════════════════════════════════════════════════════
# FILE 27/48 — advanced/sac/networks.py  (97 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-15  """ docstring """ — vì sao SAC: off-policy (học từ buffer), tối ưu entropy (explore), hợp continuous
17-22 import torch/nn/F; LOG_STD_MIN=-20, LOG_STD_MAX=2
```
**Dòng 1-22:** Mạng cho SAC. Lý do SAC thay PPO: off-policy (học từ experience replay),
tối ưu entropy (explore tốt, ổn định khi fine-tune liên tục), hợp continuous action.
File chỉ định nghĩa MẠNG (vòng train ở sac_trainer). LOG_STD kẹp [-20,2] tránh std quá
nhỏ/lớn.

```
25-35 GaussianActor.__init__: body 2 lớp ReLU; mean_head + log_std_head
```
**Dòng 25-35:** Actor xuất phân phối Gaussian. body chung (state→hidden), 2 đầu riêng:
mean (trung bình action) và log_std (độ lệch chuẩn dạng log).

```
37-41 forward(state): h=body; mean; log_std clamp [-20,2]
```
**Dòng 37-41:** Tiến: state → hidden → mean + log_std (kẹp an toàn).

```
43-53 sample(state): rsample (reparameterization); tanh squash → [-1,1]; log_prob có hiệu chỉnh tanh
```
**Dòng 43-53:** Lấy mẫu action lúc train. Reparameterization trick (rsample) cho phép
backprop qua phép lấy mẫu. tanh squash về [-1,1]. log_prob hiệu chỉnh do tanh (công thức
SAC chuẩn: trừ log(1−tanh²)). Đây là phần toán cốt lõi của SAC.

```
55-58 act(state, deterministic): suy luận deploy → tanh(mean) (bỏ ngẫu nhiên)
```
**Dòng 55-58:** Lúc deploy: chỉ lấy tanh(mean) — action tất định, không lấy mẫu ngẫu
nhiên. Đây là cái export ra ONNX (train_sac dùng).

```
61-77 TwinCritic.__init__: 2 mạng Q (q1, q2) giống nhau; forward: cat(state,action) → Q1, Q2
```
**Dòng 61-77:** Twin Critic — 2 mạng Q độc lập đánh giá (state, action). Dùng min(Q1,Q2)
khi train để giảm overestimation (lỗi phổ biến của Q-learning đánh giá quá cao). Mỗi mạng
nhận concat(state 15 + action 7) → 1 giá trị.

```
80-97 self-test: actor.sample shape (8,7)+logp (8,1), action trong [-1,1]; act tất định; critic Q shape
```
**Dòng 80-97:** Test shape + range. action trong [-1,1], log_prob đúng shape, critic ra
2 giá trị Q. In PASS.

**TÓM TẮT:** Định nghĩa mạng actor (Gaussian + tanh) và twin critic cho SAC. act() là cái
deploy. LIÊN KẾT: sac_trainer (dùng các mạng này train), train_sac (export actor.act ra
ONNX). Lưu ý: SAC là lựa chọn nghiên cứu, chưa kiểm chứng tốt hơn PPO.

═══════════════════════════════════════════════════════════════════════════════
# FILE 28/48 — advanced/sac/sac_trainer.py  (155 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-18  """ docstring """ + import copy/torch/F; from networks import GaussianActor, TwinCritic
```
**Dòng 1-18:** Vòng train SAC (offline từ buffer hoặc online). Gồm twin critic + target
critic (soft update), auto-temperature α, update() chạy 1 bước gradient. Tách khỏi
networks.py để gọn. Export deploy chỉ cần actor (15→7 tanh, khớp rl_brain).

```
22-40 __init__(state/action_dim, gamma=0.99, tau=0.005, lr=3e-4, device): actor, critic, critic_target (deepcopy, freeze); 3 optimizer; auto-temp (target_entropy=-action_dim, log_alpha)
```
**Dòng 22-40:** Khởi tạo SAC. gamma chiết khấu, tau soft update target. critic_target là
bản sao đóng băng của critic (cập nhật chậm). 3 optimizer riêng (actor/critic/alpha).
Auto-temperature: học log_alpha để đạt target entropy (-action_dim = heuristic chuẩn).

```
42-44 alpha property = exp(log_alpha)
```
**Dòng 42-44:** α = exp(log_alpha) — hệ số entropy, luôn dương.

```
46-64 update(batch): nhận (s,a,r,s2[,done]); chuyển tensor; done mask (terminal không bootstrap)
```
**Dòng 46-64:** [P4-01] Hỗ trợ done mask: target = r + γ·q_next·(1−done) — pin hết
(terminal) thì không bootstrap. Buffer hiện trả 4 phần tử → done=0 (tương thích ngược).

```
66-75 critic update: target = r + γ·(min(Q1t,Q2t) − α·logp2)·(1−done); MSE loss; backward
```
**Dòng 66-75:** Cập nhật critic. Tính target Q dùng target network + entropy bonus
(−α·logp). min(Q1t,Q2t) giảm overestimation. Loss = MSE của cả 2 critic so với target.

```
77-82 actor update: actor_loss = (α·logp − min(Q1,Q2)).mean(); backward
```
**Dòng 77-82:** Cập nhật actor. Tối đa hóa Q − α·logp (cân bằng reward và entropy). Đây
là điểm SAC khác PPO: explicit entropy maximization.

```
84-86 temperature update: alpha_loss = -(log_alpha·(logp + target_entropy)).mean()
```
**Dòng 84-86:** Tự điều chỉnh α: nếu entropy thấp hơn target → tăng α (khuyến khích
explore), ngược lại giảm. Tự động cân bằng explore/exploit.

```
88-96 soft update target: pt = (1−tau)·pt + tau·p; trả dict loss (detach để hết warning)
```
**Dòng 88-96:** Soft update target critic (trộn chậm: 99.5% cũ + 0.5% mới). detach() ở
return là fix cảnh báo requires_grad đã gặp lúc train.

```
98-107 train_from_buffer(buffer, steps, batch_size): lặp sample + update; log định kỳ
```
**Dòng 98-107:** Train nhiều bước từ buffer (off-policy). Mỗi bước sample batch + update.

```
109-125 export_actor_onnx(path): wrapper Det chỉ trả actor.act (tanh mean); export ONNX (1,15)→(1,7)
```
**Dòng 109-125:** Export CHỈ actor (deterministic) sang ONNX khớp rl_brain. Wrapper Det
gọi actor.act (tanh(mean), bỏ ngẫu nhiên). Đây là cái train_sac.py gọi để xuất model.

```
128-155 self-test: buffer 1500, reward thưởng tắt dGPU; train 600 bước → critic loss không phân kỳ; action [-1,1]
```
**Dòng 128-155:** Test: buffer giả với reward thưởng tắt dGPU, train 600 bước, kiểm critic
loss không phân kỳ + action trong [-1,1]. In PASS.

**TÓM TẮT:** Thuật toán SAC đầy đủ (critic/actor/temperature update + soft target). Lựa
chọn train thay PPO. LIÊN KẾT: networks (mạng), train_sac (train trên simulator + export),
replay_buffer (dữ liệu). Lưu ý: SAC trên CPU chậm-đều (đã gặp), chưa kiểm chứng tốt hơn PPO.

═══════════════════════════════════════════════════════════════════════════════
# FILE 29/48 — advanced/hierarchy/manager.py  (92 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  """ docstring """ — tầng CAO của HRL, quyết định mỗi ~5 phút: chế độ + mục tiêu discharge
15-26 SAVE_MAX/BALANCED/PERFORMANCE; TARGET_DISCHARGE_MW {9000/18000/40000}; DECISION_PERIOD_SEC=300
```
**Dòng 1-26:** Tầng cao Hierarchical RL. Quyết định mỗi 5 phút: chế độ chiến lược + mục
tiêu discharge (mW) cho worker bám theo. Manager nhìn bức tranh lớn (pin/giờ/pattern),
KHÔNG chọn throttle cụ thể (việc của worker). Rule-based có tham số — minh bạch, dễ giải
thích, có thể thay bằng RL sau. Mục tiêu xả: save_max 9W, balanced 18W, performance 40W.

```
29-32 Manager.__init__: mode=BALANCED, target_discharge_mw
34-58 decide(battery_pct, hour, pattern_hint, plugged): chọn mode theo ưu tiên; trả dict mode/target/reason
```
**Dòng 29-58:** decide chọn chế độ theo thứ tự ưu tiên: (1) pin ≤15% → save_max bất kể
gì, (2) cắm sạc → performance, (3) theo pattern_hint (thói quen giờ), (4) còn lại →
balanced. Trả mode + mục tiêu discharge + lý do.

```
60-67 _reason(...): tạo chuỗi giải thích quyết định (pin thấp/cắm sạc/thói quen/cân bằng)
```
**Dòng 60-67:** Sinh lý do dạng chữ cho người dùng hiểu vì sao chọn chế độ này.

```
70-92 self-test: pin 10%→save_max; cắm sạc→performance; pattern perform→performance; pattern save→save_max; bình thường→balanced
```
**Dòng 70-92:** Test các nhánh quyết định. In PASS.

**TÓM TẮT:** Tầng cao HRL — chọn chiến lược (chế độ + mục tiêu xả) theo bức tranh lớn,
rule-based minh bạch. LIÊN KẾT: hrl_integration (AutoProfileManager bọc Manager để đổi
profile), worker (nhận target_discharge để chọn action cụ thể). Lưu ý: nghiên cứu; nối
deploy qua hrl_integration ở mức chọn profile.

═══════════════════════════════════════════════════════════════════════════════
# FILE 30/48 — advanced/hierarchy/worker.py  (116 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-14  """ docstring """ — tầng THẤP HRL, quyết định mỗi ~10s: action cụ thể để đạt mục tiêu discharge
16-28 import; [FIND-02] nạp DISCHARGE_MAX_MW từ commons (fallback 80000)
```
**Dòng 1-28:** Tầng thấp HRL. Chọn action cụ thể (throttle/gpu/brightness/refresh) để đạt
M��C TIÊU discharge mà manager đề ra. Worker ghép target_discharge_norm vào state 15→16
chiều (goal-conditioned: cùng 1 worker phục vụ mọi chế độ). Có policy thì dùng, chưa có
thì dùng controller rule-based.

```
31-34 Worker.__init__(policy=None): policy callable obs(16)→action(7) hoặc None (rule-based)
```
**Dòng 31-34:** Khởi tạo. policy nhận obs 16 chiều (15 + mục tiêu), trả action [-1,1].
None → dùng luật.

```
36-43 act(state_vec15, target_discharge_mw, cur_discharge_mw): có policy → augment + raw_to_action; else → rule_based
```
**Dòng 36-43:** Hàm chính. Có policy: ghép mục tiêu vào obs, chạy policy, decode. Không
policy: bộ điều khiển theo luật bám mục tiêu (chạy được ngay).

```
45-49 _augment(state15, target_mw): ghép target_norm (target/DISCHARGE_MAX) vào cuối → 16 chiều
```
**Dòng 45-49:** Ghép mục tiêu đã chuẩn hóa vào cuối state → 16 chiều. Đây là cốt lõi
goal-conditioned: policy biết phải bám mục tiêu nào.

```
51-63 _raw_to_action(raw): tanh [-1,1] → action thực (giống decode rl_brain): throttle/brightness/defer/gpu/refresh/wifi/charge
```
**Dòng 51-63:** Decode tanh→thực, giống action_to_command của rl_brain (throttle [0.2,1],
brightness [0.3,1], refresh 3 mức...). Đảm bảo worker xuất action cùng định dạng.

```
65-86 _rule_based(target_mw, cur_mw): gap = cur - target
68-71 target ≤10000 → save_max action (throttle 0.35, tắt dGPU, 60Hz, wifi save)
72-75 target ≥35000 → performance action (throttle 0.95, dGPU, 144Hz)
77-86 cân bằng: throttle theo gap (xả cao hơn mục tiêu → siết mạnh)
```
**Dòng 65-86:** Controller rule-based bám mục tiêu. gap>0 = đang tốn hơn mục tiêu → cần
tiết kiệm. target thấp → action tiết kiệm tối đa, target cao → hiệu năng, giữa → điều
chỉnh throttle theo khoảng cách (gap>8000 siết mạnh 0.5, gap>0 vừa 0.65, đạt mục tiêu nới 0.8).

```
89-116 self-test: save_max (tắt dGPU, throttle thấp); performance (throttle cao, dGPU); balanced xả cao → siết + defer; policy giả → obs 16 chiều
```
**Dòng 89-116:** Test rule-based 3 chế độ + kiểm augment ra đúng 16 chiều khi có policy.
In PASS.

**TÓM TẮT:** Tầng thấp HRL — chọn action cụ thể để bám mục tiêu discharge của manager,
goal-conditioned (obs 16 chiều). Có fallback rule-based chạy ngay. LIÊN KẾT: manager
(cung cấp target_discharge), constants (DISCHARGE_MAX_MW), rl_brain (decode action giống
nhau). Lưu ý: nghiên cứu; worker goal-conditioned chưa nối vào deploy (deploy dùng HRL ở
mức chọn profile qua hrl_integration).

───────────────────────────────────────────────────────────────────────────────
HẾT PHẦN 5 (FILE 25-30): brain_online_adapter, hrl_integration, sac/networks,
sac/sac_trainer, hierarchy/manager, hierarchy/worker. Còn advanced: mpc_planner,
lstm_policy (2 file) → phần 6, rồi worldmodel.
───────────────────────────────────────────────────────────────────────────────
