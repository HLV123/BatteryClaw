Thư mục models/ — Phase 1
=========================
Các model ONNX 7-dim CŨ đã bị xóa vì KHÔNG còn tương thích
(observation giờ là 15 chiều, action 7 chiều).

Hãy train lại để tạo model mới:
    cd ../  (vào simulator/)
    python train.py --steps 300000

Sau khi train xong sẽ có:
    batteryclaw_policy.onnx        (input 1x15, output 1x7)
    batteryclaw_ppo_final.zip      (SB3 checkpoint)
    best/                          (best model theo eval)

Lưu ý: số liệu power trong simulator vẫn là ước tính. Giá trị thật của
việc train chỉ đến sau Phase 2 (world-model học từ dữ liệu đo thật).
