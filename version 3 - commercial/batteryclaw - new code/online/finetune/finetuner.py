"""
BatteryClaw — finetune/finetuner.py  (PHASE 3 — mục 3.2)

Fine-tune policy bằng dữ liệu thật trong replay buffer, an toàn:
  • LR rất nhỏ (1e-5) để không phá kiến thức nền.
  • EWC để chống quên (ewc.py).
  • Validate trên tập giữ lại; nếu TỆ HƠN -> rollback (checkpoint.py).

Đây là một bước fine-tune (gọi khi máy nhàn). Vòng lặp lịch trình do
online_loop.py điều phối; file này chỉ lo "một lần fine-tune cho tử tế".

Ghi chú: fine-tune ở đây dùng hồi quy hành vi có trọng số theo reward
(advantage-weighted regression đơn giản) — nhẹ, ổn định, hợp continual learning
trên laptop. Không cần vòng RL nặng như PPO khi chạy nền.
"""

import os
import numpy as np

DEFAULT_LR     = 1e-5
DEFAULT_EPOCHS = 3
DEFAULT_BATCH  = 128


def _awr_targets(rewards):
    """Advantage-weighted: chuẩn hóa reward -> trọng số mẫu (mẫu reward cao học mạnh hơn)."""
    r = rewards.reshape(-1)
    if r.std() < 1e-6:
        w = np.ones_like(r)
    else:
        adv = (r - r.mean()) / (r.std() + 1e-6)
        w = np.exp(np.clip(adv, -3, 3))     # exp(advantage), kẹp tránh tràn
    return (w / (w.mean() + 1e-6)).astype(np.float32)


class FineTuner:
    def __init__(self, policy, buffer, checkpoint_mgr,
                 lr=DEFAULT_LR, importance=1000.0, device="cpu"):
        import torch
        self.torch = torch
        self.policy = policy            # nn.Module: obs(15) -> action(7) (tanh)
        self.buffer = buffer
        self.ckpt   = checkpoint_mgr
        self.lr     = lr
        self.device = device

        from ewc import EWC
        # ước lượng Fisher trên chính dữ liệu hiện có để neo trọng số
        self.ewc = EWC(policy, importance=importance)
        self._init_ewc()

    def _init_ewc(self):
        if len(self.buffer) < 8:
            return
        s, a, r, _ = self.buffer.sample(min(256, len(self.buffer)))
        S = self.torch.tensor(s)
        A = self.torch.tensor(a_to_target(a))
        loss_fn = lambda m, ss, aa: ((m(ss) - aa) ** 2).mean()
        self.ewc.estimate_fisher(S, A, loss_fn)

    def _validate(self, S, A, W):
        """MSE có trọng số trên tập validation."""
        self.policy.eval()
        with self.torch.no_grad():
            pred = self.policy(S)
            mse = (((pred - A) ** 2).mean(dim=1) * W).mean().item()
        return mse

    def step(self, model_path, epochs=DEFAULT_EPOCHS, batch=DEFAULT_BATCH,
             val_frac=0.2):
        """Một lần fine-tune. Trả dict kết quả + có rollback hay không."""
        torch = self.torch
        if len(self.buffer) < 32:
            return {"ok": False, "reason": "buffer quá ít dữ liệu",
                    "n": len(self.buffer)}

        # 1) lưu checkpoint TRƯỚC khi fine-tune (để rollback được)
        self.ckpt.save(model_path)

        # 2) lấy toàn bộ dữ liệu hiện có, chia train/val
        n = len(self.buffer)
        s, a, r, _ = self.buffer.sample(n)
        A_target = a_to_target(a)
        W = _awr_targets(r)

        idx = np.random.permutation(n)
        nval = max(4, int(n * val_frac))
        vi, ti = idx[:nval], idx[nval:]

        to_t = lambda x: torch.tensor(x, dtype=torch.float32, device=self.device)
        S_tr, A_tr, W_tr = to_t(s[ti]), to_t(A_target[ti]), to_t(W[ti])
        S_va, A_va, W_va = to_t(s[vi]), to_t(A_target[vi]), to_t(W[vi])

        val_before = self._validate(S_va, A_va, W_va)

        # 3) fine-tune với LR nhỏ + EWC penalty
        opt = torch.optim.Adam(self.policy.parameters(), lr=self.lr)
        ntr = len(S_tr)
        self.policy.train()
        for ep in range(epochs):
            perm = torch.randperm(ntr)
            for i in range(0, ntr, batch):
                b = perm[i:i+batch]
                pred = self.policy(S_tr[b])
                base = (((pred - A_tr[b]) ** 2).mean(dim=1) * W_tr[b]).mean()
                loss = base + self.ewc.penalty()
                opt.zero_grad(); loss.backward(); opt.step()

        val_after = self._validate(S_va, A_va, W_va)

        # 4) nếu validation TỆ HƠN -> rollback
        improved = val_after <= val_before
        rolled_back = False
        if not improved:
            rolled_back = self.ckpt.rollback(model_path)
            self._reload(model_path)

        return {
            "ok": True,
            "n": n,
            "val_before": round(val_before, 6),
            "val_after":  round(val_after, 6),
            "improved":   bool(improved),
            "rolled_back": bool(rolled_back),
        }

    def _reload(self, model_path):
        """Nạp lại trọng số từ file (sau rollback)."""
        if model_path.endswith(".pt") and os.path.exists(model_path):
            self.policy.load_state_dict(self.torch.load(model_path))

    def export(self, model_path):
        """Lưu policy hiện tại ra .pt (và .onnx nếu được)."""
        torch = self.torch
        if model_path.endswith(".pt"):
            torch.save(self.policy.state_dict(), model_path)
        try:
            onnx_path = os.path.splitext(model_path)[0] + ".onnx"
            dummy = torch.zeros(1, 15)
            torch.onnx.export(self.policy, dummy, onnx_path,
                              input_names=["observation"],
                              output_names=["action"],
                              dynamic_axes={"observation": {0: "batch"},
                                            "action": {0: "batch"}},
                              opset_version=17)
        except Exception:
            pass


def a_to_target(a):
    """Action trong buffer -> target cho policy (đưa về [-1,1] kiểu tanh).
    Buffer lưu action ở thang gốc; map về [-1,1] để khớp đầu ra policy."""
    a = np.asarray(a, dtype=np.float32).copy()
    out = np.zeros_like(a)
    out[:, 0] = (a[:, 0] - 0.2) / 0.8 * 2 - 1     # throttle 0.2..1 -> -1..1
    out[:, 1] = (a[:, 1] - 0.3) / 0.7 * 2 - 1     # brightness 0.3..1
    out[:, 2] = a[:, 2] * 2 - 1                    # defer 0/1
    out[:, 3] = (a[:, 3] / 2.0) * 2 - 1            # gpu_switch 0..2
    out[:, 4] = (a[:, 4] / 2.0) * 2 - 1            # refresh 0..2
    out[:, 5] = a[:, 5] * 2 - 1                    # wifi 0/1
    out[:, 6] = a[:, 6] * 2 - 1                    # charge_limit 0/1
    return np.clip(out, -1, 1).astype(np.float32)


if __name__ == "__main__":
    import sys, torch
    import torch.nn as nn
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "buffer"))
    from replay_buffer import ReplayBuffer
    from checkpoint import CheckpointManager
    import tempfile

    print("BatteryClaw 3.2 — FineTuner self-test")

    policy = nn.Sequential(nn.Linear(15, 32), nn.ReLU(), nn.Linear(32, 7), nn.Tanh())

    buf = ReplayBuffer(capacity=500)
    rng = np.random.default_rng(0)
    for _ in range(300):
        s  = rng.random(15).astype(np.float32)
        a  = rng.random(7).astype(np.float32)
        a[0] = 0.2 + a[0] * 0.8; a[1] = 0.3 + a[1] * 0.7
        a[3] = rng.integers(0, 3); a[4] = rng.integers(0, 3)
        r  = float(rng.normal())
        s2 = rng.random(15).astype(np.float32)
        buf.add(s, a, r, s2)

    d = tempfile.mkdtemp()
    mp = os.path.join(d, "policy.pt")
    torch.save(policy.state_dict(), mp)
    cm = CheckpointManager(os.path.join(d, "ckpt"))

    ft = FineTuner(policy, buf, cm, lr=1e-3)   # LR cao hơn để thấy thay đổi trong test
    res = ft.step(mp, epochs=3)
    print("  kết quả fine-tune:", res)
    assert res["ok"] and res["n"] == 300
    assert "val_before" in res and "val_after" in res
    print("PASS ✓")
