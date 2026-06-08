"""
BatteryClaw — advanced/sac/sac_trainer.py  (PHASE 4 — mục 4.1)

Vòng train SAC, dùng được cả offline (từ replay buffer Phase 3) lẫn online.
Gồm:
  • Twin critic + target critic (soft update τ)
  • Auto-temperature α (tự điều chỉnh hệ số entropy theo target_entropy)
  • update() chạy một bước gradient từ một batch (s, a, r, s')

Tách khỏi networks.py để file ngắn, dễ đọc: đây thuần là "thuật toán cập nhật".
Export deploy: chỉ cần actor (xem export_actor_onnx) -> khớp rl_brain (15->7 tanh).
"""

import copy
import torch
import torch.nn.functional as F

from networks import GaussianActor, TwinCritic


class SAC:
    def __init__(self, state_dim=15, action_dim=7, hidden=128,
                 gamma=0.99, tau=0.005, lr=3e-4, device="cpu"):
        self.device = device
        self.gamma = gamma
        self.tau = tau

        self.actor  = GaussianActor(state_dim, action_dim, hidden).to(device)
        self.critic = TwinCritic(state_dim, action_dim, hidden).to(device)
        self.critic_target = copy.deepcopy(self.critic).to(device)
        for p in self.critic_target.parameters():
            p.requires_grad = False

        self.actor_opt  = torch.optim.Adam(self.actor.parameters(),  lr=lr)
        self.critic_opt = torch.optim.Adam(self.critic.parameters(), lr=lr)

        # auto-temperature: học log_alpha để đạt target entropy
        self.target_entropy = -float(action_dim)     # heuristic chuẩn SAC
        self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
        self.alpha_opt = torch.optim.Adam([self.log_alpha], lr=lr)

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def update(self, batch):
        """batch: (s, a, r, s2) hoac (s, a, r, s2, done) numpy. Tra dict loss.
        [P4-01] Ho tro done mask: target = r + gamma*q_next*(1-done).
        Buffer hien tai tra 4 phan tu -> done=0 (khong terminal), tuong thich nguoc."""
        if len(batch) == 5:
            s, a, r, s2, done = batch
        else:
            s, a, r, s2 = batch
            done = None
        s, a, r, s2 = (torch.as_tensor(x, dtype=torch.float32, device=self.device)
                       for x in (s, a, r, s2))
        if r.dim() == 1:
            r = r.unsqueeze(-1)
        if done is None:
            done_t = torch.zeros_like(r)
        else:
            done_t = torch.as_tensor(done, dtype=torch.float32, device=self.device)
            if done_t.dim() == 1:
                done_t = done_t.unsqueeze(-1)

        # ── critic update ──────────────────────────────────────
        with torch.no_grad():
            a2, logp2 = self.actor.sample(s2)
            q1t, q2t = self.critic_target(s2, a2)
            q_next = torch.min(q1t, q2t) - self.alpha * logp2
            # [P4-01] khong bootstrap qua trang thai terminal (pin het = done)
            target = r + self.gamma * q_next * (1.0 - done_t)
        q1, q2 = self.critic(s, a)
        critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
        self.critic_opt.zero_grad(); critic_loss.backward(); self.critic_opt.step()

        # ── actor update ───────────────────────────────────────
        a_new, logp = self.actor.sample(s)
        q1n, q2n = self.critic(s, a_new)
        q_new = torch.min(q1n, q2n)
        actor_loss = (self.alpha.detach() * logp - q_new).mean()
        self.actor_opt.zero_grad(); actor_loss.backward(); self.actor_opt.step()

        # ── temperature update ─────────────────────────────────
        alpha_loss = -(self.log_alpha * (logp + self.target_entropy).detach()).mean()
        self.alpha_opt.zero_grad(); alpha_loss.backward(); self.alpha_opt.step()

        # ── soft update target ─────────────────────────────────
        with torch.no_grad():
            for p, pt in zip(self.critic.parameters(),
                             self.critic_target.parameters()):
                pt.mul_(1 - self.tau).add_(self.tau * p)

        return {"critic_loss": float(critic_loss.detach()),
                "actor_loss": float(actor_loss.detach()),
                "alpha": float(self.alpha.detach())}

    def train_from_buffer(self, buffer, steps=1000, batch_size=256, log_every=200):
        import numpy as np
        rng = np.random.default_rng(0)
        for i in range(1, steps + 1):
            batch = buffer.sample(batch_size, rng=rng)
            info = self.update(batch)
            if i % log_every == 0:
                print(f"  step {i:5d} | critic={info['critic_loss']:.3f} "
                      f"actor={info['actor_loss']:.3f} alpha={info['alpha']:.3f}")
        return info

    def export_actor_onnx(self, path):
        """Export CHỈ actor (deterministic) -> ONNX (1,15)->(1,7) cho rl_brain."""
        self.actor.eval()
        dummy = torch.zeros(1, 15, device=self.device)

        class Det(torch.nn.Module):
            def __init__(self, actor): super().__init__(); self.actor = actor
            def forward(self, s): return self.actor.act(s)

        det = Det(self.actor).eval()
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        torch.onnx.export(det, dummy, path,
                          input_names=["observation"], output_names=["action"],
                          dynamic_axes={"observation": {0: "batch"},
                                        "action": {0: "batch"}},
                          opset_version=17)


if __name__ == "__main__":
    import os, sys
    import numpy as np
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                    "online", "buffer"))
    from replay_buffer import ReplayBuffer

    print("BatteryClaw 4.1 — SAC trainer self-test")
    buf = ReplayBuffer(capacity=2000)
    rng = np.random.default_rng(1)
    for _ in range(1500):
        s  = rng.random(15).astype(np.float32)
        a  = (rng.random(7).astype(np.float32) * 2 - 1)   # [-1,1]
        # reward giả: thưởng khi action[3] (gpu) âm = tắt dGPU
        r  = float(-a[3] * 0.5 + rng.normal() * 0.1)
        s2 = rng.random(15).astype(np.float32)
        buf.add(s, a, r, s2)

    sac = SAC()
    first = sac.update(buf.sample(256))
    info  = sac.train_from_buffer(buf, steps=600, log_every=200)
    print("  critic loss:", round(first["critic_loss"], 3), "->",
          round(info["critic_loss"], 3))
    assert info["critic_loss"] < first["critic_loss"] * 2  # không phân kỳ
    # action vẫn trong [-1,1]
    a = sac.actor.act(torch.zeros(1, 15))
    assert a.min() >= -1.0001 and a.max() <= 1.0001
    print("PASS ✓")
