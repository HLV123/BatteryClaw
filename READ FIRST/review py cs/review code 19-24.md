# BatteryClaw — Review code TỪNG DÒNG (Phần 4: FILE 19-24)

Tiếp nối phần 1-3 (file 1-18). Phần này: 6 file nhóm online (checkpoint, finetuner,
pattern_tracker, feedback_store, modes, online_loop).

Định dạng: trích dòng (kèm số dòng) → giải thích ngay dưới.

═══════════════════════════════════════════════════════════════════════════════
# FILE 19/48 — online/finetune/checkpoint.py  (90 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-15  """ docstring """ + import os, shutil, datetime, glob
17    KEEP_DAYS = 7
```
**Dòng 1-17:** Quản lý checkpoint policy: lưu mỗi ngày, giữ tối đa 7 cái gần nhất (tự xóa
cũ), cho rollback về checkpoint trước nếu model mới tệ. Chỉ thao tác file (chép/đổi tên),
không cần torch.

```
20-27 class CheckpointManager(ckpt_dir, keep=7); tạo thư mục; _stamp() = ngày YYYYMMDD
```
**Dòng 20-27:** Khởi tạo. _stamp dùng ngày làm tên checkpoint (mỗi ngày 1 bản).

```
29-36 save(model_path, tag): copy model thành policy_<tag>.<ext>; _prune; trả đường dẫn
```
**Dòng 29-36:** Sao lưu model thành checkpoint đặt tên theo ngày (hoặc tag). copy2 giữ
metadata. Sau khi lưu thì dọn bớt cũ.

```
38-45 list(): glob policy_* sort ngược (mới nhất trước); latest() = [0]
47-50 previous(): [1] nếu có ≥2 (để rollback)
```
**Dòng 38-50:** Liệt kê checkpoint mới nhất trước. latest = cái mới nhất, previous = cái
trước đó (dùng để rollback khi model mới tệ).

```
52-58 rollback(model_path): copy previous → model_path; trả True nếu có previous
60-66 _prune(): xóa checkpoint thứ keep trở đi (giữ keep cái mới)
```
**Dòng 52-66:** rollback khôi phục model từ checkpoint trước. _prune giữ đúng `keep` cái
mới nhất, xóa phần dư (nuốt lỗi xóa).

```
69-90 self-test: tạo 5 checkpoint keep=3 → giữ 3 mới nhất; rollback v4 → về v3
```
**Dòng 69-90:** Test: 5 checkpoint keep=3 chỉ giữ 3 mới nhất; rollback đưa model về bản
trước. In PASS.

**TÓM TẮT:** Quản lý phiên bản model cho online learning — lưu hàng ngày, rollback khi
model mới kém. LIÊN KẾT: finetuner (lưu checkpoint sau fine-tune, rollback khi anomaly).
Chỉ hoạt động khi bật --online.

═══════════════════════════════════════════════════════════════════════════════
# FILE 20/48 — online/finetune/finetuner.py  (198 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-15  """ docstring """ + import os, numpy
20-22 DEFAULT_LR=1e-5, EPOCHS=3, BATCH=128
```
**Dòng 1-22:** Fine-tune policy bằng dữ liệu thật trong buffer, an toàn: LR rất nhỏ (1e-5)
không phá kiến thức nền, EWC chống quên, validate trên tập giữ lại — tệ hơn thì rollback.
Dùng advantage-weighted regression (nhẹ, ổn định cho continual learning trên laptop) thay
vì RL nặng như PPO.

```
25-33 _awr_targets(rewards): chuẩn hóa reward → trọng số mẫu = exp(advantage); mẫu reward cao học mạnh hơn
```
**Dòng 25-33:** Advantage-weighted: chuẩn hóa reward thành advantage, lấy exp (kẹp [-3,3]
tránh tràn) làm trọng số. Mẫu có reward cao → trọng số lớn → policy học theo mạnh hơn.
std~0 → trọng số đều.

```
36-50 FineTuner.__init__(policy, buffer, checkpoint_mgr, lr, importance): tạo EWC + _init_ewc
52-59 _init_ewc: nếu buffer ≥8, sample 256, estimate_fisher (neo trọng số)
```
**Dòng 36-59:** Khởi tạo. policy là nn.Module obs(15)→action(7). Tạo EWC, ước Fisher trên
dữ liệu hiện có để neo trọng số quan trọng (chống quên).

```
61-67 _validate(S, A, W): MSE có trọng số trên tập validation (eval, no_grad)
```
**Dòng 61-67:** Đánh giá: sai số bình phương có trọng số giữa dự đoán và target trên tập
validation. Dùng để so trước/sau fine-tune.

```
69-94 step(model_path): nếu buffer <32 → bỏ; lưu checkpoint TRƯỚC; chia train/val; val_before
```
**Dòng 69-94:** Một lần fine-tune. Cần ≥32 mẫu. Lưu checkpoint trước (để rollback được).
Lấy toàn bộ dữ liệu, chia 80/20 train/val. Đo validation trước khi train.

```
96-109 fine-tune: Adam(lr nhỏ); mỗi epoch/batch: loss = MSE_có_trọng_số + EWC.penalty(); val_after
```
**Dòng 96-109:** Vòng fine-tune. Loss = sai số hành vi có trọng số reward + EWC penalty
(chống quên). LR nhỏ. Đo lại validation sau train.

```
111-125 nếu val_after > val_before (tệ hơn) → rollback + reload; trả dict kết quả
```
**Dòng 111-125:** **Cốt lõi an toàn:** nếu fine-tune làm validation tệ hơn → rollback về
checkpoint trước, nạp lại. Trả kết quả (cải thiện không, có rollback không).

```
127-147 _reload: nạp .pt sau rollback; export: lưu .pt + cố export .onnx
```
**Dòng 127-147:** _reload nạp lại trọng số từ file. export lưu policy ra .pt và cố xuất
ONNX (để deploy bản đã fine-tune).

```
150-162 a_to_target(a): map action thang gốc → [-1,1] khớp đầu ra policy tanh
```
**Dòng 150-162:** Chuyển action trong buffer (thang gốc: throttle 0.2-1, brightness 0.3-1,
gpu/refresh 0-2...) về [-1,1] để làm target cho policy (vì policy xuất tanh [-1,1]). Đây
là phép biến đổi ngược của scale trong rl_brain.

```
165-198 self-test: policy nn nhỏ; buffer 300 mẫu; FineTuner.step → kiểm ok + val trước/sau
```
**Dòng 165-198:** Test: policy giả lập, 300 transition, chạy 1 lần fine-tune, kiểm có
val_before/val_after. LR test cao hơn (1e-3) để thấy thay đổi. In PASS.

**TÓM TẮT:** Fine-tune an toàn trên dữ liệu máy người dùng: AWR + EWC + rollback nếu tệ
hơn. Đây là trái tim của online learning. LIÊN KẾT: ewc (penalty), checkpoint (save/
rollback), replay_buffer (dữ liệu), online_loop (lịch gọi), brain_online_adapter.

═══════════════════════════════════════════════════════════════════════════════
# FILE 21/48 — online/personalize/pattern_tracker.py  (113 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-14  """ docstring """ + import json, os
19-20 N_HOURS=24, N_WORKLOAD=5
```
**Dòng 1-20:** Học thói quen RIÊNG người dùng để chủ động (không chỉ phản ứng): "8-17h
hay code → cần CPU cao", "tối xem video → tiết kiệm". Cách nhẹ: thống kê trực tuyến theo
24 khung giờ, mỗi khung giữ phân bố workload + mức xả trung bình. Lưu JSON bền qua phiên.

```
23-32 __init__(path): counts[24][5] đếm (giờ,workload); discharge_ema[24]; ema_alpha=0.05; load nếu có
```
**Dòng 23-32:** Khởi tạo. counts đếm số lần mỗi (giờ, loại workload). discharge_ema = mức
xả trung bình động theo giờ (EMA alpha 0.05 = trung bình trượt mượt). Nạp dữ liệu cũ nếu có.

```
34-43 update(hour, workload_id, discharge_mw): tăng counts[h][w]; cập nhật EMA discharge
```
**Dòng 34-43:** Cập nhật thống kê mỗi bước: tăng đếm (giờ, workload), cập nhật mức xả
trung bình (EMA: lần đầu lấy thẳng, sau trộn 95% cũ + 5% mới).

```
45-53 likely_workload(hour): nếu tổng <5 → None; else workload đếm nhiều nhất + độ tin cậy
```
**Dòng 45-53:** Workload hay gặp nhất ở khung giờ này. Cần ≥5 mẫu mới đoán (tránh đoán
bừa). Trả (workload, độ tin cậy = tỉ lệ).

```
55-64 context_hint(hour): conf<0.5 → neutral; workload 3/4 (compile/game) → perform; else → save
```
**Dòng 55-64:** Gợi ý ngữ cảnh cho vòng chính. Độ tin cậy thấp → trung tính. compile/game
→ gợi ý "perform" (cần hiệu năng). idle/browse/office → "save" (tiết kiệm). Chỉ gợi ý,
không ép — để nhích policy đúng hướng chủ động.

```
66-80 save/load JSON (counts + discharge_ema)
83-113 self-test: 9-10h hay compile → perform; 21h hay browse → save; giờ trống → neutral; save/load
```
**Dòng 66-113:** Lưu/nạp JSON. Test: giả lập 9-10h compile → hint perform, 21h browse →
hint save, giờ chưa có dữ liệu → neutral, kiểm save/load. In PASS.

**TÓM TẮT:** Học thói quen người dùng theo giờ để chủ động nhích policy (proactive). Nhẹ,
không cần ML. LIÊN KẾT: brain_online_adapter (update mỗi bước, dùng context_hint),
online_loop. Tương tự ý tưởng CHARGE_PROFILES + _wl_weights_by_hour trong battery_env
nhưng học từ người dùng thật thay vì giả lập.

═══════════════════════════════════════════════════════════════════════════════
# FILE 22/48 — online/feedback/feedback_store.py  (71 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-13  """ docstring """
```
**Dòng 1-13:** Người dùng dạy model bằng nút bấm: "Nhanh hơn" → hành động vừa làm bị phạt
(đừng tiết kiệm kiểu đó), "Tiết kiệm hơn" → được thưởng. Cơ chế: bấm → lấy transition
gần nhất, chỉnh reward, đẩy lại vào buffer để fine-tune học theo.

```
15-16 FASTER_PENALTY=-1.0, SAVE_BONUS=+1.0
```
**Dòng 15-16:** Reward gán khi user bấm: "Nhanh hơn" phạt −1, "Tiết kiệm hơn" thưởng +1.

```
19-26 FeedbackStore: last_transition; events; remember(s,a,r,s2) lưu transition gần nhất
```
**Dòng 19-26:** Lưu transition gần nhất (vòng chính gọi remember mỗi bước) + lịch sử
feedback để thống kê.

```
28-40 feedback(kind): nếu chưa có transition → None; "faster" → reward -1; "save" → reward +1; trả transition đã chỉnh
```
**Dòng 28-40:** Khi user bấm: lấy transition gần nhất, thay reward theo loại feedback,
ghi sự kiện, trả transition mới (để online_loop đẩy vào buffer). kind lạ → None.

```
42-45 stats(): đếm số lần faster/save/total
48-71 self-test: chưa có transition → None; remember rồi feedback faster/save → reward đúng; stats
```
**Dòng 42-71:** Thống kê số lần mỗi loại. Test: feedback khi rỗng → None; sau remember,
faster → −1, save → +1, stats đếm đúng. In PASS.

**TÓM TẮT:** Cho người dùng dạy model trực tiếp qua nút bấm (reinforcement từ con người).
LIÊN KẾT: online_loop (đẩy transition đã chỉnh vào buffer), app/buy_business (nút bấm
trên GUI gọi feedback). Lưu ý: app GUI hiện tại có thể chưa lộ nút này — đây là hạ tầng sẵn.

═══════════════════════════════════════════════════════════════════════════════
# FILE 23/48 — online/feedback/modes.py  (98 dòng)
═══════════════════════════════════════════════════════════════════════════════

```
1-11  """ docstring """ + import time
15-19 MEETING, SAVE_MAX, NONE; DEFAULT_MINUTES=30
```
**Dòng 1-19:** Chế độ tạm thời do người dùng bật, GHI ĐÈ policy trong N phút: "Họp quan
trọng" (tắt tiết kiệm, giữ hiệu năng) / "Pin yếu cần lâu" (tiết kiệm tối đa). Tự hết hạn
quay về bình thường. Mặc định 30 phút.

```
22-33 ModeManager: mode, until (epoch giây); set_mode(mode, minutes) đặt until; clear() reset
```
**Dòng 22-33:** Quản lý mode. set_mode đặt mode + thời điểm hết hạn (now + phút×60).
clear về NONE.

```
35-42 active(): nếu quá until → tự clear; trả mode hiện tại. remaining_sec() = giây còn lại
```
**Dòng 35-42:** active tự động hết hạn (quá giờ → clear) rồi trả mode đang hiệu lực.
remaining_sec cho biết còn bao lâu (hiển thị trên GUI).

```
44-64 apply(action, state): ghi đè action theo mode
50-55 MEETING: throttle≥0.95, brightness≥0.80, dGPU, refresh max, không defer
56-63 SAVE_MAX: throttle≤0.40, brightness≤0.35, tắt dGPU (nếu không game), 60Hz, wifi save, defer
```
**Dòng 44-64:** Ghi đè action theo mode đang hiệu lực. MEETING ép hiệu năng cao (không
để AI tiết kiệm lúc họp). SAVE_MAX ép tiết kiệm tối đa, nhưng tắt dGPU chỉ khi KHÔNG game
(constraints sẽ chặn lần nữa nếu game). NONE → giữ nguyên action.

```
67-98 self-test: không mode→giữ nguyên; meeting→hiệu năng+dGPU; save_max→tiết kiệm; save_max+game→giữ dGPU; hết hạn→none
```
**Dòng 67-98:** Test đủ các trường hợp: meeting nâng hiệu năng, save_max tiết kiệm,
save_max khi game vẫn giữ dGPU, mode hết hạn tự về none. In PASS.

**TÓM TẮT:** Chế độ tạm thời người dùng bật để ghi đè policy (họp/tiết kiệm tối đa), tự
hết hạn. LIÊN KẾT: brain_online_adapter (apply mode lên action), app/buy_business (nút
bật mode), constraints (chặn tắt dGPU khi game). Hạ tầng Phase 3 — app GUI cần nút để
dùng đầy đủ.

═══════════════════════════════════════════════════════════════════════════════
# FILE 24/48 — online/online_loop.py  (178 dòng — ĐIỀU PHỐI PHASE 3)
═══════════════════════════════════════════════════════════════════════════════

```
1-20  """ docstring """ — sơ đồ ghép các mảnh Phase 3
22-39 import + path; nạp ReplayBuffer, clamp_action, PatternTracker, FeedbackStore, ModeManager
41-42 IDLE_MINUTES_FOR_FINETUNE=5, FINETUNE_EVERY_SEC=600
```
**Dòng 1-42:** Điều phối toàn bộ Phase 3. Sơ đồ: transition đến → remember (3.4) + pattern.
update (3.3) + buffer.add (3.1); khi máy nhàn >5 phút → finetuner.step (3.2+3.5). Quyết
định action: policy → modes.apply → constraints.clamp. File không tự đọc pipe — nhận dữ
liệu từ ngoài (dễ test). Fine-tune tối thiểu cách nhau 10 phút.

```
45-67 OnlineLearner.__init__(state_dir, policy, model_path): tạo buffer/pattern/feedback/modes; nếu có policy+model → tạo FineTuner + CheckpointManager
```
**Dòng 45-67:** Khởi tạo. Gom 5 thành phần Phase 3, mỗi cái lưu state vào state_dir
(replay.npz, pattern.json, ckpt/). FineTuner chỉ bật nếu có policy + model_path.

```
70-74 observe(s,a,r,s2,hour,workload,discharge): feedback.remember + buffer.add + pattern.update
```
**Dòng 70-74:** Mỗi bước: nhớ transition (cho feedback), tích vào buffer, cập nhật thói
quen theo giờ. Đây là điểm rl_brain gọi mỗi vòng.

```
77-80 finalize_action(action, state): modes.apply (3.4) → clamp_action (3.5); trả action an toàn + lý do
```
**Dòng 77-80:** Hoàn thiện action: áp mode tạm thời (nếu bật) rồi qua ràng buộc cứng an
toàn. Đây là refine() mà brain_online_adapter gọi.

```
83-90 user_feedback(kind): feedback.feedback → đẩy transition đã chỉnh vào buffer. set_mode
93-97 mark_activity / idle_seconds (biết khi nào máy nhàn)
```
**Dòng 83-97:** user_feedback xử lý nút bấm → đẩy transition đã chỉnh reward vào buffer.
set_mode bật chế độ tạm. mark_activity/idle_seconds theo dõi máy nhàn.

```
100-114 maybe_finetune(): nếu chưa idle đủ 5 phút / chưa qua 10 phút / buffer <32 → None; else finetuner.step; nếu cải thiện → export deploy
```
**Dòng 100-114:** Fine-tune khi đủ điều kiện (máy nhàn ≥5 phút, cách lần trước ≥10 phút,
đủ dữ liệu). Nếu fine-tune cải thiện → export bản mới để deploy. Điều kiện chặt để không
fine-tune lúc người dùng đang làm việc.

```
117-119 save(): lưu buffer + pattern
122-178 self-test: 200 transition; finalize_action (nóng+game bị ép); mode họp; feedback; fine-tune chỉ chạy khi idle đủ
```
**Dòng 117-178:** save lưu trạng thái khi thoát. Test đầy đủ vòng: nạp 200 transition,
action an toàn bị ép khi nóng+game, mode họp ghi đè, feedback đẩy buffer, fine-tune chỉ
chạy khi idle đủ lâu. In PASS.

**TÓM TẮT:** Nhạc trưởng của online learning — ghép buffer/pattern/feedback/modes/finetuner
thành 1 vòng. observe() tích dữ liệu, finalize_action() ra action an toàn, maybe_finetune()
học khi máy nhàn. LIÊN KẾT: tất cả file online khác + brain_online_adapter (cầu nối tới
rl_brain). Lưu ý: brain dùng BrainOnlineAdapter (file 25) bọc lớp này, không gọi trực tiếp.

───────────────────────────────────────────────────────────────────────────────
HẾT PHẦN 4 (FILE 19-24): checkpoint, finetuner, pattern_tracker, feedback_store,
modes, online_loop. Còn online: brain_online_adapter, hrl_integration (2 file) →
phần 5, rồi sang advanced.
───────────────────────────────────────────────────────────────────────────────
